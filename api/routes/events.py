"""Events router — list active events from disk.

Routes:
    GET /events — list all active (non-past, non-cancelled) events
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

from fastapi import APIRouter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytz
import yaml

from api.schemas import EventResponse

logger = logging.getLogger(__name__)
router = APIRouter()

EVENTS_DIR = os.path.join(_PROJECT_ROOT, "data", "events")
CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")
STOCKHOLM_TZ = pytz.timezone("Europe/Stockholm")


def _load_tag_keywords() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f).get("tag_keywords", {})
    except Exception:
        return {}


def _derive_tags(description: str, tag_keywords: dict) -> list[str]:
    text = description.lower()
    return [tag for tag, kws in tag_keywords.items() if any(kw in text for kw in kws)]


def _to_stockholm(iso_string: str) -> datetime:
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(STOCKHOLM_TZ)


def _normalize(raw: dict, tag_keywords: dict) -> EventResponse | None:
    if raw.get("isCancelled") or raw.get("isDeleted"):
        return None

    try:
        start_time = _to_stockholm(raw["startingAt"])
    except (KeyError, ValueError):
        return None

    if start_time < datetime.now(tz=STOCKHOLM_TZ):
        return None  # past event

    try:
        end_time = _to_stockholm(raw["endingAt"])
    except (KeyError, ValueError):
        end_time = start_time

    parent_interest_ids = raw.get("parentInterestIds") or []
    tags = [str(t) for t in parent_interest_ids] if parent_interest_ids else \
           _derive_tags(raw.get("description", ""), tag_keywords)

    city = ""
    loc = raw.get("location")
    if isinstance(loc, dict):
        city = loc.get("city", "")

    return EventResponse(
        event_id=str(raw["id"]),
        title=raw.get("title", ""),
        city=city,
        tags=tags,
        start_time=start_time,
        end_time=end_time,
        capacity=raw.get("capacity"),
    )


@router.get("", response_model=list[EventResponse])
def list_events():
    """List all active upcoming events from data/events/."""
    tag_keywords = _load_tag_keywords()
    results: list[EventResponse] = []

    if not os.path.isdir(EVENTS_DIR):
        logger.warning("Events directory not found: %s", EVENTS_DIR)
        return []

    for filename in os.listdir(EVENTS_DIR):
        if not filename.endswith(".json") or filename.startswith("."):
            continue
        path = os.path.join(EVENTS_DIR, filename)
        try:
            with open(path) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read event file %s: %s", filename, e)
            continue

        # Unwrap files exported as {"event": {...}, "stats": ..., "exportedAt": ...}
        if isinstance(raw, dict) and "event" in raw and isinstance(raw["event"], dict):
            raw = raw["event"]

        # Derive id from filename stem when absent
        if not raw.get("id"):
            raw = {**raw, "id": os.path.splitext(filename)[0]}

        event = _normalize(raw, tag_keywords)
        if event:
            results.append(event)

    results.sort(key=lambda e: e.start_time)
    return results
