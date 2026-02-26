"""Node E — CollectRedditNode

For each query in the validated scrape plan:
  - Runs the query against the target subreddit via RedditCollector
  - Time-filters to the run window
  - Deduplicates against raw_items already in the DB
  - Marks deleted/removed content as SKIPPED_DELETED
  - Writes new items to raw_items and processing_queue
  - Checks stop_requested between queries — run never crashes on a failed query

Output: list of new item_ids written this run
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import yaml
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from collectors.reddit import RedditCollector
from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
DELETED_MARKERS = {"[deleted]", "[removed]"}


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _is_deleted(item: dict) -> bool:
    author = item.get("author", "")
    text = item.get("text", "").strip()
    return author in DELETED_MARKERS or text in DELETED_MARKERS


def _already_collected(db: Session, item_id: str) -> bool:
    return db.query(RawItem).filter(RawItem.item_id == item_id).first() is not None


def _write_item(db: Session, item: dict, run_id: str, query: str) -> None:
    processing_status = "SKIPPED_DELETED" if _is_deleted(item) else "PENDING"
    raw = RawItem(
        item_id=item["item_id"],
        type=item["type"],
        subreddit=item["subreddit"],
        author=item["author"],
        permalink=item["permalink"],
        text=item["text"],
        created_utc=datetime.fromtimestamp(item["created_utc"], tz=timezone.utc),
        query_used=query,
        run_id=run_id,
        processed=False,
        processing_status=processing_status,
    )
    db.add(raw)

    if processing_status == "PENDING":
        queue_entry = ProcessingQueue(
            item_id=item["item_id"],
            run_id=run_id,
            status="PENDING",
            retry_count=0,
        )
        db.add(queue_entry)


def _build_default_plan(config: dict, time_window_hours: int) -> list[dict]:
    """Fallback plan used when Nodes C/D haven't run yet (e.g. step-by-step testing)."""
    subreddits = config.get("subreddits", [])
    queries = ["social events", "meetup", "pub quiz", "strangers", "new to stockholm"]
    plan = []
    for i, query in enumerate(queries):
        for subreddit in subreddits:
            plan.append({
                "query": query,
                "subreddit": subreddit,
                "priority": i,
            })
    return plan


def collect_reddit_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    mock_mode = os.environ.get("MOCK_MODE", "false").lower() == "true"
    run_id = state.get("run_id", "dev-run")

    # Use validated plan from Node D, or fall back to a default
    plan_entries: list[dict] = state.get("validated_plan", {}).get(
        "queries", _build_default_plan(config, int(os.environ.get("TIME_WINDOW_HOURS", 48)))
    )

    time_window_hours = int(os.environ.get("TIME_WINDOW_HOURS", 48))
    now = datetime.now(tz=timezone.utc)
    time_window_start = now - timedelta(hours=time_window_hours)
    time_window_end = now

    collector = RedditCollector(mock_mode=mock_mode)
    new_item_ids: list[str] = []
    errors: list[str] = state.get("errors", [])

    db: Session = SessionLocal()
    try:
        for entry in plan_entries:
            # Check kill switch between queries
            budget = state.get("budget")
            if budget and getattr(budget, "stop_requested", False):
                logger.info("Stop requested — halting collection after current query")
                break

            query: str = entry.get("query", "")
            subreddit: str = entry.get("subreddit", "")
            if not query or not subreddit:
                continue

            logger.info("Collecting: query=%r subreddit=%s", query, subreddit)

            try:
                items = collector.collect(query, subreddit, time_window_start, time_window_end)
            except Exception as e:
                msg = f"Collection failed query={query!r} subreddit={subreddit}: {e}"
                logger.error(msg)
                errors.append(msg)
                continue  # skip — never crash the run

            written = 0
            for item in items:
                if _already_collected(db, item["item_id"]):
                    logger.debug("Duplicate skipped: %s", item["item_id"])
                    continue
                try:
                    _write_item(db, item, run_id, query)
                    new_item_ids.append(item["item_id"])
                    written += 1
                except Exception as e:
                    logger.warning("Failed to write item %s: %s", item["item_id"], e)
                    db.rollback()
                    continue

            db.commit()
            logger.info(
                "query=%r subreddit=%s: wrote %d new items", query, subreddit, written
            )

    finally:
        db.close()

    logger.info(
        "CollectRedditNode complete — %d new items written across all queries",
        len(new_item_ids),
    )
    return {**state, "collected_item_ids": new_item_ids, "errors": errors}
