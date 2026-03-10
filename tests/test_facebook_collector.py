import json
from datetime import datetime, timedelta, timezone

import pytest

from collectors.facebook import FacebookCollector, _detect_access_wall


def test_facebook_collector_manual_json_filters_group_and_query(tmp_path):
    path = tmp_path / "facebook.json"
    rows = [
        {
            "item_id": "a1",
            "group": "Stockholm Expats",
            "author": "alice",
            "permalink": "https://facebook.com/groups/x/posts/1",
            "text": "I am new to Stockholm and looking for friends",
            "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        },
        {
            "item_id": "a2",
            "group": "Other Group",
            "author": "bob",
            "permalink": "https://facebook.com/groups/y/posts/2",
            "text": "looking for friends in stockholm",
            "created_utc": datetime.now(tz=timezone.utc).isoformat(),
        },
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")

    collector = FacebookCollector(
        mode="manual_json",
        mock_mode=False,
        manual_input_path=str(path),
    )
    now = datetime.now(tz=timezone.utc)
    items = collector.collect(
        "looking for friends stockholm",
        "Stockholm Expats",
        now - timedelta(days=2),
        now + timedelta(days=1),
    )
    assert len(items) == 1
    assert items[0]["subreddit"] == "Stockholm Expats"
    assert items[0]["item_id"] == "a1"


def test_detect_access_wall_patterns():
    blocked, reason = _detect_access_wall("Please log in or sign up to continue.")
    assert blocked is True
    assert reason == "login_wall"

    blocked, reason = _detect_access_wall("Everything is fine on this page.")
    assert blocked is False
    assert reason == ""


def test_selenium_requires_acknowledgement(monkeypatch):
    monkeypatch.delenv("FACEBOOK_SCRAPE_ACKNOWLEDGED", raising=False)
    collector = FacebookCollector(
        mode="selenium",
        mock_mode=False,
        selenium_group_urls={"Stockholm Expats": "https://www.facebook.com/groups/stockholmexpats/"},
    )
    now = datetime.now(tz=timezone.utc)
    with pytest.raises(RuntimeError, match="FACEBOOK_SCRAPE_ACKNOWLEDGED=true"):
        collector.collect(
            "looking for friends stockholm",
            "Stockholm Expats",
            now - timedelta(days=2),
            now + timedelta(days=1),
        )
