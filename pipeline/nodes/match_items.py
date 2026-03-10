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
import re
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem, Run, UserEventAffinity
from embeddings.embedder import embed_single
from embeddings.faiss_store import FaissStore
from llm.client import LLMClient, extract_tagged_json
from llm.prompts import (
    MATCHER_PROMPT_V,
    MATCHER_PROMPT_TEMPLATE,
    MATCHER_PROMPT_STRICT_TEMPLATE,
    format_event_list,
    format_items_list,
    matcher_few_shots,
)
from llm.schemas import BatchMatchResult
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
DEGRADED_COST_THRESHOLD = 0.50
DEFAULT_EXPLICIT_INTENT_PATTERNS = [
    r"\blooking for\b",
    r"\bwould love to join\b",
    r"\bnew to stockholm\b",
    r"\bmeet new people\b",
    r"\bi am interested\b",
    r"\bi'?d like to join\b",
    r"\bjag är intresserad\b",
    r"\bhänger gärna på\b",
    r"\bskicka(r)? (ett )?dm\b",
]
DEFAULT_AMBIGUOUS_INTENT_PATTERNS = [
    r"\bmaybe\b",
    r"\bopen to ideas\b",
    r"\bany suggestions\b",
    r"\bsounds (fun|nice|interesting)\b",
    r"\bnice initiative\b",
    r"\btentative\b",
]
DEFAULT_FUTURE_INTENT_PATTERNS = [
    r"\bcan('|no)?t join\b",
    r"\bcannot join\b",
    r"\bcan't make it\b",
    r"\bnot this (week|time)\b",
    r"\bnext week\b",
    r"\bnext time\b",
    r"\bin future dates\b",
    r"\bkan inte denna gång\b",
    r"\bnästa gång\b",
]
DEFAULT_HARD_NEGATIVE_PATTERNS = [
    r"\bbest coffee\b",
    r"\bhousing queue\b",
    r"\bapartment\b",
    r"\bgrammar\b",
    r"\bweather\b",
    r"\bvisa\b",
    r"\bresidence permit\b",
]
DEFAULT_SOCIAL_FALLBACK_PATTERNS = [
    r"\blooking for (new )?friends?\b",
    r"\bmake friends?\b",
    r"\bnew to stockholm\b",
    r"\bmeet(ing)? new people\b",
    r"\bhang out\b",
    r"\bwant to meet people\b",
]
SOCIAL_FALLBACK_EVENT_TAGS = {"social", "nightlife", "pub-crawl", "trivia"}


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


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            compiled.append(re.compile(re.escape(pattern), re.IGNORECASE))
    return compiled


def _contains_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _social_terms(config: dict) -> set[str]:
    tag_keywords = config.get("tag_keywords", {})
    terms = {"social", "meet", "friends", "group", "join", "event", "activities", "newcomer"}
    for keywords in tag_keywords.values():
        for kw in keywords:
            terms.add(str(kw).lower())
    return terms


def _has_social_signal(text: str, social_terms: set[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in social_terms)


def _is_hard_negative(text: str, hard_negative_patterns: list[re.Pattern[str]], social_terms: set[str]) -> bool:
    if _has_social_signal(text, social_terms):
        return False
    return _contains_any(text, hard_negative_patterns)


def _rerank_matches(
    item_text: str,
    matches: list[dict],
    explicit_patterns: list[re.Pattern[str]],
    ambiguous_patterns: list[re.Pattern[str]],
    future_patterns: list[re.Pattern[str]],
    explicit_bonus: float,
    ambiguous_penalty: float,
    future_penalty: float,
) -> list[dict]:
    explicit = _contains_any(item_text, explicit_patterns)
    ambiguous = _contains_any(item_text, ambiguous_patterns)
    future = _contains_any(item_text, future_patterns)
    reranked: list[dict] = []
    for match in matches:
        score = float(match.get("match_confidence", 0.0))
        if explicit:
            score += explicit_bonus
        if ambiguous:
            score -= ambiguous_penalty
        if future:
            score -= future_penalty
        score = max(0.0, min(1.0, score))
        reranked.append({**match, "match_confidence": score})
    reranked.sort(key=lambda m: m.get("match_confidence", 0.0), reverse=True)
    return reranked[:3]


def _fallback_social_matches(
    item_text: str,
    candidate_events: list[dict],
    social_fallback_patterns: list[re.Pattern[str]],
) -> list[dict]:
    """Return one conservative fallback match for explicit friend-seeking posts."""
    if not _contains_any(item_text, social_fallback_patterns):
        return []
    for event in candidate_events:
        tags = {str(t).lower() for t in event.get("tags", [])}
        if tags.intersection(SOCIAL_FALLBACK_EVENT_TAGS):
            return [
                {
                    "event_id": event["event_id"],
                    "match_confidence": 0.52,
                    "match_reason": "Explicit friend-seeking intent aligns with social event.",
                    "evidence_excerpt": item_text[:150],
                }
            ]
    return []


def _parse_and_validate(raw_response: str) -> BatchMatchResult | None:
    raw_json = extract_tagged_json(raw_response, "matches")
    if not raw_json:
        return None
    try:
        return BatchMatchResult(**raw_json)
    except ValidationError as e:
        logger.warning("BatchMatchResult validation failed: %s", e)
        return None


def _infer_source_from_raw_item(item_id: str, raw_item: RawItem | None) -> str:
    if raw_item:
        query_used = str(raw_item.query_used or "")
        if query_used.startswith("facebook|"):
            return "facebook"
        permalink = str(raw_item.permalink or "").lower()
        if "facebook.com" in permalink:
            return "facebook"
    if str(item_id).startswith("fb_"):
        return "facebook"
    return "reddit"


def _write_affinities(
    db: Session,
    item_matches: list[dict],
    default_min_confidence_threshold: float,
    event_thresholds: dict[str, float] | None = None,
    prompt_version: int = MATCHER_PROMPT_V,
) -> int:
    written = 0
    for item_result in item_matches:
        item_id = item_result["item_id"]
        # Get author profile_url from raw_items
        raw = db.query(RawItem).filter(RawItem.item_id == item_id).first()
        source = _infer_source_from_raw_item(item_id, raw)
        username = "unknown"
        profile_url = None
        if raw:
            username = raw.author
            if source == "reddit":
                profile_url = f"https://www.reddit.com/user/{raw.author}"

        for match in item_result.get("matches", []):
            # Skip if confidence below threshold
            threshold = default_min_confidence_threshold
            if event_thresholds:
                threshold = float(event_thresholds.get(match["event_id"], threshold))
            if match["match_confidence"] < threshold:
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


def _stop_requested(db: Session, run_id: str, budget) -> bool:
    if budget and getattr(budget, "stop_requested", False):
        return True
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if run and run.stop_requested:
        if budget:
            budget.stop_requested = True
        return True
    return False


def match_items_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    run_cfg = state.get("run_config", {})
    mock_mode = bool(
        run_cfg.get(
            "mock_mode",
            os.environ.get("MOCK_MODE", "false").lower() == "true",
        )
    )
    run_id = state.get("run_id", "dev-run")
    budget = state.get("budget")
    errors: list[str] = state.get("errors", [])

    match_config = config.get("match", {})
    precision_cfg = config.get("precision", {})
    batch_size = match_config.get("batch_size", 5)
    min_text_length = match_config.get("min_text_length", 30)
    min_confidence_threshold = float(match_config.get("min_confidence_threshold", 0.4))
    per_tag_thresholds = precision_cfg.get("per_tag_confidence_thresholds", {}) or {}
    tag_keywords = config.get("tag_keywords", {})
    explicit_patterns = _compile_patterns(
        precision_cfg.get("explicit_intent_patterns", DEFAULT_EXPLICIT_INTENT_PATTERNS)
    )
    ambiguous_patterns = _compile_patterns(
        precision_cfg.get("ambiguous_intent_patterns", DEFAULT_AMBIGUOUS_INTENT_PATTERNS)
    )
    future_patterns = _compile_patterns(
        precision_cfg.get("future_intent_patterns", DEFAULT_FUTURE_INTENT_PATTERNS)
    )
    hard_negative_patterns = _compile_patterns(
        precision_cfg.get("hard_negative_patterns", DEFAULT_HARD_NEGATIVE_PATTERNS)
    )
    social_fallback_patterns = _compile_patterns(
        precision_cfg.get("social_fallback_patterns", DEFAULT_SOCIAL_FALLBACK_PATTERNS)
    )
    social_terms = _social_terms(config)
    explicit_bonus = float(precision_cfg.get("explicit_intent_bonus", 0.06))
    ambiguous_penalty = float(precision_cfg.get("ambiguous_intent_penalty", 0.08))
    future_penalty = float(precision_cfg.get("future_intent_penalty", 0.14))
    event_map = {e.event_id: e for e in state.get("events", [])}
    event_thresholds: dict[str, float] = {}
    for event_id, event in event_map.items():
        threshold = min_confidence_threshold
        for tag in event.tags:
            threshold = max(threshold, float(per_tag_thresholds.get(tag, threshold)))
        event_thresholds[event_id] = threshold

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

        eligible = []
        for raw in raw_items:
            text = raw.text.strip()
            if len(text) < min_text_length:
                continue
            if _is_hard_negative(text, hard_negative_patterns, social_terms):
                _mark_queue(db, raw.item_id, "SKIPPED", detail="hard_negative")
                _set_raw_item_status(db, raw.item_id, "SKIPPED")
                continue
            eligible.append(raw)
        db.commit()
        logger.info(
            "MatchItemsNode: %d eligible items from %d pending", len(eligible), len(pending)
        )

        # Process in batches
        for batch_start in range(0, len(eligible), batch_size):
            # Check kill switch
            if _stop_requested(db, run_id, budget):
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
                    "tags": event_map.get(eid).tags if event_map.get(eid) else [],
                }
                for eid in candidate_event_ids
            ]
            candidate_event_ids_list = list(candidate_event_ids)

            if not candidate_events:
                logger.debug("No candidate events for batch — skipping")
                for item_id in batch_item_ids:
                    _mark_queue(db, item_id, "DONE")
                    _mark_raw_item(db, item_id)
                db.commit()
                continue

            # --- Matching ---
            if degraded:
                # Keyword-only fallback
                results_list = []
                for item in batch_items:
                    kw_matches = _keyword_match(item["text"], candidate_events, tag_keywords)
                    kw_matches = _rerank_matches(
                        item["text"],
                        kw_matches,
                        explicit_patterns=explicit_patterns,
                        ambiguous_patterns=ambiguous_patterns,
                        future_patterns=future_patterns,
                        explicit_bonus=explicit_bonus,
                        ambiguous_penalty=ambiguous_penalty,
                        future_penalty=future_penalty,
                    )
                    if not kw_matches:
                        kw_matches = _fallback_social_matches(
                            item["text"],
                            candidate_events,
                            social_fallback_patterns=social_fallback_patterns,
                        )
                    results_list.append({"item_id": item["item_id"], "matches": kw_matches})
                affinities_written += _write_affinities(
                    db,
                    results_list,
                    default_min_confidence_threshold=min_confidence_threshold,
                    event_thresholds=event_thresholds,
                )
            else:
                # LLM matching
                prompt = MATCHER_PROMPT_TEMPLATE.format(
                    event_list=format_event_list(candidate_events),
                    items_list=format_items_list(batch_items),
                    matcher_few_shots=matcher_few_shots(),
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

                results_list = []
                item_text_map = {item["item_id"]: item["text"] for item in batch_items}
                for row in result.results:
                    item_text = item_text_map.get(row.item_id, "")
                    reranked = _rerank_matches(
                        item_text,
                        [m.model_dump() for m in row.matches],
                        explicit_patterns=explicit_patterns,
                        ambiguous_patterns=ambiguous_patterns,
                        future_patterns=future_patterns,
                        explicit_bonus=explicit_bonus,
                        ambiguous_penalty=ambiguous_penalty,
                        future_penalty=future_penalty,
                    )
                    if not reranked:
                        reranked = _fallback_social_matches(
                            item_text,
                            candidate_events,
                            social_fallback_patterns=social_fallback_patterns,
                        )
                    results_list.append({"item_id": row.item_id, "matches": reranked})
                affinities_written += _write_affinities(
                    db,
                    results_list,
                    default_min_confidence_threshold=min_confidence_threshold,
                    event_thresholds=event_thresholds,
                )

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


def _set_raw_item_status(db: Session, item_id: str, status: str) -> None:
    item = db.query(RawItem).filter(RawItem.item_id == item_id).first()
    if item:
        item.processing_status = status
