"""Node E — CollectSourcesNode (kept as collect_reddit node for compatibility)

For each query in the validated scrape plan:
  - Runs the query against the target source community via source collector
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
import hashlib

import yaml
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from collectors.facebook import FacebookCollector
from collectors.reddit import RedditCollector
from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem, Run
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


def _ensure_item_id(item: dict, source: str) -> str:
    raw_id = str(item.get("item_id", "")).strip()
    if raw_id:
        if source == "facebook" and not raw_id.startswith("fb_"):
            return f"fb_{raw_id}"
        return raw_id
    payload = "|".join(
        [
            source,
            str(item.get("author", "unknown")),
            str(item.get("subreddit", "")),
            str(item.get("permalink", "")),
            str(item.get("text", ""))[:180],
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{'fb' if source == 'facebook' else 'raw'}_{digest}"


def _write_item(db: Session, item: dict, run_id: str, query: str, source: str) -> None:
    processing_status = "SKIPPED_DELETED" if _is_deleted(item) else "PENDING"
    item_id = _ensure_item_id(item, source)
    created_utc = float(item.get("created_utc", datetime.now(tz=timezone.utc).timestamp()))
    permalink = str(item.get("permalink", "")).strip()
    if not permalink:
        if source == "facebook":
            permalink = "https://www.facebook.com/"
        else:
            permalink = "https://www.reddit.com/"

    raw = RawItem(
        item_id=item_id,
        type=item.get("type", "post"),
        subreddit=str(item.get("subreddit", "")).strip() or "unknown",
        author=str(item.get("author", "")).strip() or "unknown",
        permalink=permalink,
        text=str(item.get("text", "")).strip(),
        created_utc=datetime.fromtimestamp(created_utc, tz=timezone.utc),
        query_used=f"{source}|{query}",
        run_id=run_id,
        processed=False,
        processing_status=processing_status,
    )
    db.add(raw)

    if processing_status == "PENDING":
        queue_entry = ProcessingQueue(
            item_id=item_id,
            run_id=run_id,
            status="PENDING",
            retry_count=0,
        )
        db.add(queue_entry)


def _stop_requested(db: Session, run_id: str, budget) -> bool:
    if budget and getattr(budget, "stop_requested", False):
        return True
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if run and run.stop_requested:
        if budget:
            budget.stop_requested = True
        return True
    return False


def _build_default_plan(config: dict, time_window_hours: int) -> list[dict]:
    """Fallback plan used when Nodes C/D haven't run yet (e.g. step-by-step testing)."""
    enabled_sources = {
        str(src).strip().lower() for src in (config.get("sources", {}) or {}).get("enabled", ["reddit"])
    }
    subreddits = config.get("subreddits") or []
    facebook_groups = (config.get("facebook") or {}).get("groups") or []
    queries = ["social events", "meetup", "pub quiz", "strangers", "new to stockholm"]
    plan = []
    if "reddit" in enabled_sources:
        for i, query in enumerate(queries):
            for subreddit in subreddits:
                plan.append({
                    "query": query,
                    "subreddit": subreddit,
                    "priority": i,
                    "source": "reddit",
                })
    if "facebook" in enabled_sources:
        for group in facebook_groups:
            for query in queries[:2]:
                plan.append(
                    {
                        "query": query,
                        "subreddit": group,
                        "priority": 1,
                        "source": "facebook",
                    }
                )
    return plan


def collect_reddit_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    run_cfg = state.get("run_config", {})
    mock_mode = bool(
        run_cfg.get(
            "mock_mode",
            os.environ.get("MOCK_MODE", "false").lower() == "true",
        )
    )
    run_id = state.get("run_id", "dev-run")
    fallback_time_window_hours = int(
        run_cfg.get(
            "time_window_hours",
            os.environ.get("TIME_WINDOW_HOURS", config.get("budget", {}).get("time_window_hours", 48)),
        )
    )
    budget = state.get("budget")

    # Use validated plan from Node D, or fall back to a default
    plan_entries: list[dict] = state.get("validated_plan", {}).get(
        "queries", _build_default_plan(config, fallback_time_window_hours)
    )

    if budget and getattr(budget, "time_window_start", None) and getattr(budget, "time_window_end", None):
        time_window_start = budget.time_window_start
        time_window_end = budget.time_window_end
    else:
        now = datetime.now(tz=timezone.utc)
        time_window_start = now - timedelta(hours=fallback_time_window_hours)
        time_window_end = now

    collect_comments = config.get("collector", {}).get("collect_comments", True)
    enabled_sources = {
        str(src).strip().lower()
        for src in run_cfg.get("sources", ((config.get("sources") or {}).get("enabled", ["reddit"])))
        if str(src).strip()
    }
    if not enabled_sources:
        enabled_sources = {"reddit"}

    collectors: dict[str, object] = {}
    if "reddit" in enabled_sources:
        collectors["reddit"] = RedditCollector(mock_mode=mock_mode, collect_comments=collect_comments)
    if "facebook" in enabled_sources:
        fb_cfg = config.get("facebook") or {}
        selenium_cfg = fb_cfg.get("selenium") or {}
        collectors["facebook"] = FacebookCollector(
            mode=str(fb_cfg.get("mode", "manual_json")),
            mock_mode=mock_mode,
            manual_input_path=str(fb_cfg.get("manual_input_path", "")) or os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "import", "facebook_posts.json"
            ),
            selenium_headless=bool(selenium_cfg.get("headless", True)),
            selenium_max_scrolls=int(selenium_cfg.get("max_scrolls", 3)),
            selenium_scroll_pause_seconds=float(selenium_cfg.get("scroll_pause_seconds", 1.5)),
            selenium_group_urls=selenium_cfg.get("group_urls", {}) or {},
        )
    new_item_ids: list[str] = []
    errors: list[str] = state.get("errors", [])

    db: Session = SessionLocal()
    try:
        for entry in plan_entries:
            # Check kill switch between queries
            if _stop_requested(db, run_id, budget):
                logger.info("Stop requested — halting collection after current query")
                break

            query: str = entry.get("query", "")
            subreddit: str = entry.get("subreddit", "")
            source: str = str(entry.get("source", "reddit")).strip().lower() or "reddit"
            if not query or not subreddit or source not in collectors:
                continue

            logger.info("Collecting: source=%s query=%r community=%s", source, query, subreddit)

            try:
                items = collectors[source].collect(query, subreddit, time_window_start, time_window_end)
            except Exception as e:
                msg = f"Collection failed source={source} query={query!r} community={subreddit}: {e}"
                logger.error(msg)
                errors.append(msg)
                continue  # skip — never crash the run

            written = 0
            for item in items:
                item_id = _ensure_item_id(item, source)
                if _already_collected(db, item_id):
                    logger.debug("Duplicate skipped: %s", item_id)
                    continue
                try:
                    with db.begin_nested():
                        _write_item(db, item, run_id, query, source=source)
                        db.flush()
                    new_item_ids.append(item_id)
                    written += 1
                except IntegrityError:
                    logger.debug("Duplicate skipped (race/in-batch): %s", item_id)
                except Exception as e:
                    logger.warning("Failed to write item %s: %s", item_id, e)
                    continue

            db.commit()
            logger.info(
                "source=%s query=%r community=%s: wrote %d new items",
                source, query, subreddit, written,
            )

    finally:
        db.close()

    logger.info(
        "CollectRedditNode complete — %d new items written across all queries",
        len(new_item_ids),
    )
    return {**state, "collected_item_ids": new_item_ids, "errors": errors}
