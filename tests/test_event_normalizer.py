"""Tests for Node A — LoadEventsNode / event normalizer logic."""
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
import pytz

from pipeline.nodes.load_events import (
    _normalize_event,
    _derive_tags,
    _to_stockholm_time,
    load_events_node,
)

STOCKHOLM_TZ = pytz.timezone("Europe/Stockholm")

TAG_KEYWORDS = {
    "nightlife": ["pub", "bar", "beer", "drinks"],
    "trivia": ["quiz", "trivia"],
    "pub-crawl": ["crawl"],
    "social": ["social", "meet", "friends", "strangers"],
    "outdoors": ["hike", "trail", "walk", "nature"],
    "climbing": ["climb", "climbing", "klättring"],
    "dance": ["dance", "bachata", "salsa", "kizomba"],
    "coding": ["code", "python", "developer", "programming"],
}

FUTURE = (datetime.now(tz=timezone.utc) + timedelta(days=30)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
PAST = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def make_raw(overrides: dict = {}) -> dict:
    base = {
        "id": "evt_test_001",
        "title": "Test Event",
        "location": {"city": "Stockholm"},
        "startingAt": FUTURE,
        "endingAt": FUTURE,
        "capacity": 50,
        "languages": ["en"],
        "description": "A fun social event for friends.",
        "parentInterestIds": [],
        "isCancelled": False,
        "isDeleted": False,
    }
    base.update(overrides)
    return base


# --- _to_stockholm_time ---

def test_utc_z_suffix_converts():
    dt = _to_stockholm_time("2026-06-15T18:00:00Z")
    assert dt.tzinfo is not None
    assert dt.tzname() in ("CEST", "CET")


def test_utc_offset_suffix_converts():
    dt = _to_stockholm_time("2026-06-15T18:00:00+00:00")
    assert dt.tzinfo is not None


# --- _derive_tags ---

def test_derive_tags_nightlife():
    tags = _derive_tags("Come for drinks and beer!", TAG_KEYWORDS)
    assert "nightlife" in tags


def test_derive_tags_multiple():
    tags = _derive_tags("A quiz night at the pub with friends.", TAG_KEYWORDS)
    assert "trivia" in tags
    assert "nightlife" in tags
    assert "social" in tags


def test_derive_tags_no_match():
    tags = _derive_tags("Completely unrelated content.", TAG_KEYWORDS)
    assert tags == []


def test_derive_tags_case_insensitive():
    tags = _derive_tags("Great CLIMBING wall event with Klättring course.", TAG_KEYWORDS)
    assert "climbing" in tags


# --- _normalize_event ---

def test_normalize_valid_event():
    event = _normalize_event(make_raw(), TAG_KEYWORDS)
    assert event is not None
    assert event.event_id == "evt_test_001"
    assert event.title == "Test Event"
    assert event.city == "Stockholm"
    assert "social" in event.tags


def test_skip_cancelled():
    event = _normalize_event(make_raw({"isCancelled": True}), TAG_KEYWORDS)
    assert event is None


def test_skip_deleted():
    event = _normalize_event(make_raw({"isDeleted": True}), TAG_KEYWORDS)
    assert event is None


def test_skip_past_event():
    event = _normalize_event(make_raw({"startingAt": PAST}), TAG_KEYWORDS)
    assert event is None


def test_tags_from_parent_interest_ids():
    event = _normalize_event(
        make_raw({"parentInterestIds": ["nightlife", "dance"], "description": ""}),
        TAG_KEYWORDS,
    )
    assert event is not None
    assert event.tags == ["nightlife", "dance"]


def test_tags_auto_derived_when_parent_ids_empty():
    event = _normalize_event(
        make_raw({"parentInterestIds": [], "description": "Join us for a pub quiz!"}),
        TAG_KEYWORDS,
    )
    assert event is not None
    assert "trivia" in event.tags
    assert "nightlife" in event.tags


def test_languages_extracted():
    event = _normalize_event(make_raw({"languages": ["sv", "en"]}), TAG_KEYWORDS)
    assert event is not None
    assert event.languages == ["sv", "en"]


def test_capacity_extracted():
    event = _normalize_event(make_raw({"capacity": 100}), TAG_KEYWORDS)
    assert event is not None
    assert event.capacity == 100


def test_missing_location_city_defaults_empty():
    event = _normalize_event(make_raw({"location": {}}), TAG_KEYWORDS)
    assert event is not None
    assert event.city == ""


def test_null_location_defaults_empty():
    event = _normalize_event(make_raw({"location": None}), TAG_KEYWORDS)
    assert event is not None
    assert event.city == ""


# --- load_events_node (integration) ---

def test_load_events_node_reads_json(tmp_path, monkeypatch):
    event_data = make_raw()
    event_file = tmp_path / "evt_001.json"
    event_file.write_text(json.dumps(event_data))

    monkeypatch.setattr(
        "pipeline.nodes.load_events.EVENTS_DIR", str(tmp_path)
    )

    result = load_events_node({})
    assert len(result["events"]) == 1
    assert result["events"][0].event_id == "evt_test_001"


def test_load_events_node_skips_cancelled(tmp_path, monkeypatch):
    event_file = tmp_path / "evt_cancelled.json"
    event_file.write_text(json.dumps(make_raw({"isCancelled": True})))

    monkeypatch.setattr(
        "pipeline.nodes.load_events.EVENTS_DIR", str(tmp_path)
    )

    result = load_events_node({})
    assert result["events"] == []


def test_load_events_node_skips_past(tmp_path, monkeypatch):
    event_file = tmp_path / "evt_past.json"
    event_file.write_text(json.dumps(make_raw({"startingAt": PAST})))

    monkeypatch.setattr(
        "pipeline.nodes.load_events.EVENTS_DIR", str(tmp_path)
    )

    result = load_events_node({})
    assert result["events"] == []


def test_load_events_node_skips_malformed_json(tmp_path, monkeypatch):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {{{")
    good_file = tmp_path / "good.json"
    good_file.write_text(json.dumps(make_raw()))

    monkeypatch.setattr(
        "pipeline.nodes.load_events.EVENTS_DIR", str(tmp_path)
    )

    result = load_events_node({})
    assert len(result["events"]) == 1


def test_load_events_node_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.nodes.load_events.EVENTS_DIR", str(tmp_path)
    )

    result = load_events_node({})
    assert result["events"] == []
