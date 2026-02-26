"""Node G — MatchItemsNode (RAG + LLM)

Processes PENDING items from processing_queue in batches of 5.
For each batch:
  1. Query FAISS for top 5 candidate events per item
  2. Send one LLM call covering all 5 items
  3. Validate output with Pydantic — retry once with strict prompt on failure
  4. Write matches to user_event_affinity
  5. Update processing_queue status
  6. Check budget between batches — degrade to keyword-only at $0.50 remaining

Output: user_event_affinity rows written
"""
import logging
import os
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem, UserEventAffinity
from embeddings.embedder import embed_single
from embeddings.faiss_store import FaissStore
from llm.client import LLMClient, extract_tagged_json
from llm.prompts import (
    MATCHER_PROMPT_V,
    MATCHER_PROMPT_TEMPLATE,
    MATCHER_PROMPT_STRICT_TEMPLATE,
    format_event_list,
    format_items_list,
)
from llm.schemas import BatchMatchResult
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
DEGRADED_COST_THRESHOLD = 0.50


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _keyword_match(item_text: str, events: list[dict], keywords_map: dict) -> list[dict]:
    """Fallback keyword-only matching when budget is exhausted."""
    text = item_text.lower()
    matches = []
    for event in events:
        score = sum(
            1 for tag in event.get("tags", [])
            for kw in keywords_map.get(tag, [])
            if kw in text
        )
        if score > 0:
            matches.append({
                "event_id": event["event_id"],
                "match_confidence": min(0.3 + score * 0.05, 0.49),
                "match_reason": "Keyword match (degraded mode)",
                "evidence_excerpt": item_text[:150],
            })
    return sorted(matches, key=lambda x: x["match_confidence"], reverse=True)[:3]


def _parse_and_validate(raw_response: str) -> BatchMatchResult | None:
    raw_json = extract_tagged_json(raw_response, "matches")
    if not raw_json:
        return None
    try:
        return BatchMatchResult(**raw_json)
    except ValidationError as e:
        logger.warning("BatchMatchResult validation failed: %s", e)
        return None


def _write_affinities(
    db: Session,
    item_matches: list[dict],
    source: str = "reddit",
    prompt_version: int = MATCHER_PROMPT_V,
) -> int:
    written = 0
    for item_result in item_matches:
        item_id = item_result["item_id"]
        # Get author profile_url from raw_items
        raw = db.query(RawItem).filter(RawItem.item_id == item_id).first()
        profile_url = None
        username = "unknown"
        if raw:
            username = raw.author
            profile_url = f"https://www.reddit.com/user/{raw.author}"

        for match in item_result.get("matches", []):
            # Skip if confidence below threshold
            if match["match_confidence"] < 0.3:
                continue
            # Dedup check
            existing = db.query(UserEventAffinity).filter(
                UserEventAffinity.source == source,
                UserEventAffinity.username == username,
                UserEventAffinity.event_id == match["event_id"],
                UserEventAffinity.evidence_item_id == item_id,
            ).first()
            if existing:
                continue

            affinity = UserEventAffinity(
                source=source,
                username=username,
                profile_url=profile_url,
                event_id=match["event_id"],
                evidence_item_id=item_id,
                evidence_excerpt=match.get("evidence_excerpt", "")[:150],
                match_confidence=match["match_confidence"],
                match_reason=match.get("match_reason", "")[:100],
                prompt_version=prompt_version,
            )
            db.add(affinity)
            written += 1

    db.commit()
    return written


def match_items_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    mock_mode = os.environ.get("MOCK_MODE", "false").lower() == "true"
    run_id = state.get("run_id", "dev-run")
    budget = state.get("budget")
    errors: list[str] = state.get("errors", [])

    match_config = config.get("match", {})
    batch_size = match_config.get("batch_size", 5)
    min_text_length = match_config.get("min_text_length", 30)
    tag_keywords = config.get("tag_keywords", {})

    client = LLMClient(mock_mode=mock_mode)
    store = FaissStore()
    store.load()

    db: Session = SessionLocal()
    affinities_written = 0

    try:
        # Load all PENDING items for this run
        pending = (
            db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.run_id == run_id,
                ProcessingQueue.status == "PENDING",
            )
            .all()
        )

        if not pending:
            logger.info("MatchItemsNode: no pending items for run %s", run_id)
            return {**state, "affinities_written": 0}

        # Load corresponding raw_items (skip deleted/too short)
        item_ids = [p.item_id for p in pending]
        raw_items = (
            db.query(RawItem)
            .filter(
                RawItem.item_id.in_(item_ids),
                RawItem.processing_status == "PENDING",
            )
            .all()
        )

        eligible = [
            r for r in raw_items
            if len(r.text.strip()) >= min_text_length
        ]
        logger.info(
            "MatchItemsNode: %d eligible items from %d pending", len(eligible), len(pending)
        )

        # Process in batches
        for batch_start in range(0, len(eligible), batch_size):
            # Check kill switch
            if budget and getattr(budget, "stop_requested", False):
                logger.info("Stop requested — halting matching")
                break

            # Check degraded mode threshold
            degraded = False
            if budget and (budget.max_cost_usd - budget.estimated_cost_usd) <= DEGRADED_COST_THRESHOLD:
                degraded = True
                if not getattr(budget, "degraded_mode", False):
                    logger.warning("Budget low — switching to keyword-only matching")
                    if budget:
                        budget.degraded_mode = True

            batch = eligible[batch_start: batch_start + batch_size]
            batch_items = [
                {
                    "item_id": r.item_id,
                    "subreddit": r.subreddit,
                    "text": r.text,
                }
                for r in batch
            ]
            batch_item_ids = [r.item_id for r in batch]

            # FAISS: get candidate events for this batch
            candidate_event_ids: set[str] = set()
            for raw in batch:
                results = store.search(embed_single(raw.text[:400]), k=5)
                for r in results:
                    candidate_event_ids.add(r["event_id"])

            candidate_events = [
                {
                    "event_id": eid,
                    "title": store._meta.get(eid, {}).get("title", eid),
                    "tags": [],
                }
                for eid in candidate_event_ids
            ]
            candidate_event_ids_list = list(candidate_event_ids)

            if not candidate_events:
                logger.debug("No candidate events for batch — skipping")
                for item_id in batch_item_ids:
                    _mark_queue(db, item_id, "DONE")
                db.commit()
                continue

            # --- Matching ---
            if degraded:
                # Keyword-only fallback
                results_list = []
                for item in batch_items:
                    kw_matches = _keyword_match(item["text"], candidate_events, tag_keywords)
                    results_list.append({"item_id": item["item_id"], "matches": kw_matches})
                affinities_written += _write_affinities(db, results_list)
            else:
                # LLM matching
                prompt = MATCHER_PROMPT_TEMPLATE.format(
                    event_list=format_event_list(candidate_events),
                    items_list=format_items_list(batch_items),
                )
                raw_response = client.match_batch(
                    prompt, item_ids=batch_item_ids, event_ids=candidate_event_ids_list
                )
                result = _parse_and_validate(raw_response)

                if result is None:
                    # Retry with strict prompt
                    logger.warning("Batch parse failed — retrying with strict prompt")
                    strict_prompt = MATCHER_PROMPT_STRICT_TEMPLATE.format(
                        event_list=format_event_list(candidate_events),
                        items_list=format_items_list(batch_items),
                    )
                    raw_response = client.match_batch(
                        strict_prompt,
                        item_ids=batch_item_ids,
                        event_ids=candidate_event_ids_list,
                    )
                    result = _parse_and_validate(raw_response)

                if result is None:
                    # Skip batch — log and continue
                    msg = f"Batch failed after retry: {batch_item_ids}"
                    logger.error(msg)
                    errors.append(msg)
                    for item_id in batch_item_ids:
                        _mark_queue(db, item_id, "FAILED", detail=raw_response[:500])
                    db.commit()
                    continue

                results_list = [r.model_dump() for r in result.results]
                affinities_written += _write_affinities(db, results_list)

                # Update budget
                if budget:
                    budget.estimated_cost_usd += client.total_estimated_cost
                    budget.llm_calls_made += client.total_calls
                    client.total_estimated_cost = 0.0
                    client.total_calls = 0

            # Mark items as done
            for item_id in batch_item_ids:
                _mark_queue(db, item_id, "DONE")
                _mark_raw_item(db, item_id)
            db.commit()

            logger.info(
                "Batch %d-%d: wrote %d affinities (degraded=%s)",
                batch_start, batch_start + len(batch), affinities_written, degraded,
            )

    finally:
        db.close()

    logger.info(
        "MatchItemsNode complete — %d affinity rows written", affinities_written
    )
    return {**state, "affinities_written": affinities_written, "errors": errors}


def _mark_queue(db: Session, item_id: str, status: str, detail: str = None) -> None:
    entry = db.query(ProcessingQueue).filter(ProcessingQueue.item_id == item_id).first()
    if entry:
        entry.status = status
        if detail:
            entry.error_detail = detail


def _mark_raw_item(db: Session, item_id: str) -> None:
    item = db.query(RawItem).filter(RawItem.item_id == item_id).first()
    if item:
        item.processed = True
        item.processing_status = "DONE"
