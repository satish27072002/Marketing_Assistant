import pytest

from quality.dataset import normalize_rows


def test_normalize_rows_with_aliases_and_event_lookup():
    rows = [
        {
            "id": "t3_1",
            "author": "alice",
            "community": "stockholm",
            "body": "Looking for pub quiz friends.",
            "primary_event_id": "evt_1",
            "confidence": "0.82",
            "url": "https://reddit.com/r/stockholm/comments/1",
            "created_utc": 1_710_000_000,
            "reviewer_feedback": "good_match",
        }
    ]
    event_lookup = {"evt_1": {"event_title": "Friday Pub Quiz"}}
    out = normalize_rows(rows, event_lookup=event_lookup)
    assert len(out) == 1
    row = out[0]
    assert row["item_id"] == "t3_1"
    assert row["username"] == "alice"
    assert row["event_title"] == "Friday Pub Quiz"
    assert row["label"] == "GOOD_MATCH"
    assert row["current_confidence"] == pytest.approx(0.82)


def test_normalize_rows_missing_required_fields_raises():
    rows = [
        {
            "id": "t3_2",
            "author": "alice",
            # missing subreddit/text/event/link/timestamp
        }
    ]
    with pytest.raises(ValueError):
        normalize_rows(rows)


def test_normalize_rows_deduplicates_item_event_key():
    rows = [
        {
            "item_id": "t3_dup",
            "username": "u1",
            "subreddit": "stockholm",
            "text": "Looking for meetup",
            "event_id": "evt_3",
            "event_title": "Meetup",
            "current_confidence": 0.7,
            "source_link": "https://x",
            "timestamp": "2025-01-01T12:00:00Z",
        },
        {
            "item_id": "t3_dup",
            "username": "u1",
            "subreddit": "stockholm",
            "text": "Looking for meetup",
            "event_id": "evt_3",
            "event_title": "Meetup",
            "current_confidence": 0.6,
            "source_link": "https://x",
            "timestamp": "2025-01-01T12:00:00Z",
        },
    ]
    out = normalize_rows(rows)
    assert len(out) == 1

