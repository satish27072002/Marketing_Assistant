"""Node A — LoadEventsNode

Reads all JSON files from data/events/. Skips cancelled, deleted, or past events.
Extracts normalized Event objects. Auto-derives tags from description when
parentInterestIds is empty. Runs a FAISS sync check to mark removed events inactive.
"""
import json
import logging
import os
from datetime import datetime, timezone

import pytz
import yaml

from pipeline.state import Event, PipelineState

logger = logging.getLogger(__name__)

STOCKHOLM_TZ = pytz.timezone("Europe/Stockholm")
EVENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "events")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
FAISS_META_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "faiss_index", "index_meta.json"
)


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _to_stockholm_time(iso_string: str) -> datetime:
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(STOCKHOLM_TZ)


def _derive_tags(description: str, tag_keywords: dict[str, list[str]]) -> list[str]:
    text = description.lower()
    tags = []
    for tag, keywords in tag_keywords.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    return tags


def _normalize_event(raw: dict, tag_keywords: dict[str, list[str]], filename: str = "") -> Event | None:
    if raw.get("isCancelled") or raw.get("isDeleted"):
        logger.debug("Skipping cancelled/deleted event: %s", raw.get("id"))
        return None

    # Derive id from filename stem when the event object has no id field
    event_id = raw.get("id") or os.path.splitext(filename)[0]

    try:
        start_time = _to_stockholm_time(raw["startingAt"])
    except (KeyError, ValueError) as e:
        logger.warning("Could not parse startingAt for event %s: %s", event_id, e)
        return None

    now = datetime.now(tz=STOCKHOLM_TZ)
    if start_time < now:
        logger.debug("Skipping past event: %s (started %s)", event_id, start_time)
        return None

    try:
        end_time = _to_stockholm_time(raw["endingAt"])
    except (KeyError, ValueError) as e:
        logger.warning("Could not parse endingAt for event %s: %s", event_id, e)
        end_time = start_time

    parent_interest_ids = raw.get("parentInterestIds") or []
    if parent_interest_ids:
        tags = [str(t) for t in parent_interest_ids]
    else:
        tags = _derive_tags(raw.get("description", ""), tag_keywords)

    city = ""
    location = raw.get("location")
    if isinstance(location, dict):
        city = location.get("city", "")

    return Event(
        event_id=str(event_id),
        title=raw.get("title", ""),
        city=city,
        start_time=start_time,
        end_time=end_time,
        description=raw.get("description", ""),
        tags=tags,
        languages=raw.get("languages") or [],
        capacity=raw.get("capacity"),
    )


def _get_known_faiss_ids() -> set[str]:
    if not os.path.exists(FAISS_META_PATH):
        return set()
    try:
        with open(FAISS_META_PATH, "r") as f:
            meta = json.load(f)
        return set(meta.keys())
    except (json.JSONDecodeError, OSError):
        return set()


def _mark_inactive_in_faiss(inactive_ids: set[str]) -> None:
    if not inactive_ids or not os.path.exists(FAISS_META_PATH):
        return
    try:
        with open(FAISS_META_PATH, "r") as f:
            meta = json.load(f)
        for event_id in inactive_ids:
            if event_id in meta:
                meta[event_id]["active"] = False
        with open(FAISS_META_PATH, "w") as f:
            json.dump(meta, f, indent=2)
        logger.info("Marked %d events inactive in FAISS index", len(inactive_ids))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not update FAISS meta for inactive events: %s", e)


def load_events_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    tag_keywords: dict[str, list[str]] = config.get("tag_keywords", {})

    events_dir = os.path.abspath(EVENTS_DIR)
    if not os.path.isdir(events_dir):
        logger.warning("Events directory not found: %s", events_dir)
        return {**state, "events": []}

    json_files = [
        f for f in os.listdir(events_dir)
        if f.endswith(".json") and not f.startswith(".")
    ]

    events: list[Event] = []
    loaded_ids: set[str] = set()

    for filename in json_files:
        path = os.path.join(events_dir, filename)
        try:
            with open(path, "r") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read event file %s: %s", filename, e)
            continue

        # Unwrap files exported as {"event": {...}, "stats": ..., "exportedAt": ...}
        if isinstance(raw, dict) and "event" in raw and isinstance(raw["event"], dict):
            raw = raw["event"]

        event = _normalize_event(raw, tag_keywords, filename)
        if event:
            events.append(event)
            loaded_ids.add(event.event_id)
            logger.debug("Loaded event: %s — %s", event.event_id, event.title)

    # FAISS sync check: mark events removed from disk as inactive
    known_faiss_ids = _get_known_faiss_ids()
    inactive_ids = known_faiss_ids - loaded_ids
    if inactive_ids:
        logger.info("Events no longer on disk, marking inactive: %s", inactive_ids)
        _mark_inactive_in_faiss(inactive_ids)

    logger.info(
        "LoadEventsNode: loaded %d active events from %d files",
        len(events), len(json_files)
    )
    return {**state, "events": events}
