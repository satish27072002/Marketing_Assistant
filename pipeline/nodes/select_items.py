"""Node F — SelectItemsForMatchingNode (deterministic, no LLM cost)

Cheap filters applied before any LLM cost:
  - Minimum 30 character text length
  - Language check: keep English and Swedish only (langdetect)
  - Duplicate author filter: deprioritise if same author appears 5+ times in run
  - Priority scoring 0–3 based on keyword match with event tags
  - Hard cap: max 100 items per run
  - Items that don't qualify are marked SKIPPED in processing_queue

Output: selected items sorted by priority (highest first)
"""
import logging
import os

import yaml
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")

VALID_LANGUAGES = {"en", "sv", "unknown"}
MAX_AUTHOR_OCCURRENCES = 5


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "unknown"


def _priority_score(text: str, tag_keywords: dict[str, list[str]]) -> int:
    """Score 0–3 based on exact keyword matches with event tags."""
    text_lower = text.lower()
    matched_tags = 0
    for tag, keywords in tag_keywords.items():
        if any(kw in text_lower for kw in keywords):
            matched_tags += 1
    if matched_tags >= 3:
        return 3
    if matched_tags == 2:
        return 2
    if matched_tags == 1:
        return 1
    return 0


def select_items_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    run_id = state.get("run_id", "dev-run")
    run_cfg = state.get("run_config", {})
    match_config = config.get("match", {})
    budget_cfg = config.get("budget", {})
    min_text_length = match_config.get("min_text_length", 30)
    max_items = int(
        run_cfg.get(
            "max_items",
            os.environ.get("MAX_ITEMS_PER_RUN", budget_cfg.get("max_items_per_run", 100)),
        )
    )
    max_author_occ = match_config.get("max_author_occurrences_per_run", MAX_AUTHOR_OCCURRENCES)
    tag_keywords = config.get("tag_keywords", {})

    db: Session = SessionLocal()
    selected_items = []

    try:
        pending_queue = (
            db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.run_id == run_id,
                ProcessingQueue.status == "PENDING",
            )
            .all()
        )

        if not pending_queue:
            logger.info("SelectItemsNode: no pending items for run %s", run_id)
            return {**state, "selected_items": []}

        item_ids = [p.item_id for p in pending_queue]
        raw_items = (
            db.query(RawItem)
            .filter(RawItem.item_id.in_(item_ids))
            .all()
        )
        raw_map = {r.item_id: r for r in raw_items}

        author_counts: dict[str, int] = {}
        scored: list[tuple[int, dict]] = []

        for queue_entry in pending_queue:
            raw = raw_map.get(queue_entry.item_id)
            if not raw:
                continue

            # Skip deleted/removed
            if raw.processing_status == "SKIPPED_DELETED":
                _mark_skipped(db, queue_entry.item_id)
                continue

            # Text length filter
            text = raw.text.strip()
            if len(text) < min_text_length:
                logger.debug("Skipping short item %s (%d chars)", raw.item_id, len(text))
                _mark_skipped(db, queue_entry.item_id)
                continue

            # Language filter
            lang = _detect_language(text)
            if lang not in VALID_LANGUAGES:
                logger.debug("Skipping non-en/sv item %s (lang=%s)", raw.item_id, lang)
                _mark_skipped(db, queue_entry.item_id)
                continue

            # Author frequency — deprioritise but don't skip
            author_counts[raw.author] = author_counts.get(raw.author, 0) + 1
            is_frequent_author = author_counts[raw.author] > max_author_occ

            # Priority score
            priority = _priority_score(text, tag_keywords)
            if is_frequent_author:
                priority = max(0, priority - 1)

            item_dict = {
                "item_id": raw.item_id,
                "type": raw.type,
                "subreddit": raw.subreddit,
                "author": raw.author,
                "permalink": raw.permalink,
                "text": text,
                "priority": priority,
            }
            scored.append((priority, item_dict))

        # Sort by priority descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Enforce max items cap
        selected = [item for _, item in scored[:max_items]]
        skipped_over_cap = [item for _, item in scored[max_items:]]

        for item in skipped_over_cap:
            _mark_skipped(db, item["item_id"])

        db.commit()
        selected_items = selected

        logger.info(
            "SelectItemsNode: %d selected, %d skipped (cap=%d)",
            len(selected), len(skipped_over_cap) + (len(pending_queue) - len(scored)),
            max_items,
        )

    finally:
        db.close()

    return {**state, "selected_items": selected_items}


def _mark_skipped(db: Session, item_id: str) -> None:
    entry = db.query(ProcessingQueue).filter(ProcessingQueue.item_id == item_id).first()
    if entry:
        entry.status = "SKIPPED"
