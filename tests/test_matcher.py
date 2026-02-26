"""Tests for Step 5 — LLM schemas, client mock mode, and matcher logic."""
import json
import pytest
from pydantic import ValidationError

from llm.schemas import (
    BatchMatchResult,
    EventMatch,
    ItemMatch,
    ScrapePlan,
    ScrapeQuery,
    UserSummary,
)
from llm.client import LLMClient, extract_tagged_json
from llm.prompts import format_event_list, format_items_list


# ---------------------------------------------------------------------------
# Schema tests — ScrapeQuery / ScrapePlan
# ---------------------------------------------------------------------------

def test_scrape_query_valid():
    q = ScrapeQuery(query="pub quiz stockholm", subreddit="stockholm", priority=3)
    assert q.query == "pub quiz stockholm"


def test_scrape_query_too_many_words():
    with pytest.raises(ValidationError):
        ScrapeQuery(
            query="one two three four five six seven eight nine ten eleven",
            subreddit="stockholm",
            priority=1,
        )


def test_scrape_query_invalid_priority():
    with pytest.raises(ValidationError):
        ScrapeQuery(query="social events", subreddit="stockholm", priority=5)


def test_scrape_plan_valid():
    plan = ScrapePlan(queries=[
        {"query": "pub quiz night", "subreddit": "stockholm", "priority": 3},
        {"query": "climbing group", "subreddit": "StockholmSocialClub", "priority": 2},
    ])
    assert len(plan.queries) == 2


def test_scrape_plan_empty_queries():
    with pytest.raises(ValidationError):
        ScrapePlan(queries=[])


# ---------------------------------------------------------------------------
# Schema tests — EventMatch / ItemMatch / BatchMatchResult
# ---------------------------------------------------------------------------

def test_event_match_valid():
    m = EventMatch(
        event_id="evt_001",
        match_confidence=0.85,
        match_reason="User asks about pub quiz",
        evidence_excerpt="Anyone know good pub quiz spots?",
    )
    assert m.match_confidence == 0.85


def test_event_match_confidence_out_of_range():
    with pytest.raises(ValidationError):
        EventMatch(
            event_id="evt_001",
            match_confidence=1.5,
            match_reason="Test",
            evidence_excerpt="Test",
        )


def test_event_match_reason_too_long():
    with pytest.raises(ValidationError):
        EventMatch(
            event_id="evt_001",
            match_confidence=0.8,
            match_reason="x" * 101,
            evidence_excerpt="Test",
        )


def test_event_match_excerpt_too_long():
    with pytest.raises(ValidationError):
        EventMatch(
            event_id="evt_001",
            match_confidence=0.8,
            match_reason="Short reason",
            evidence_excerpt="x" * 151,
        )


def test_item_match_max_three_matches():
    with pytest.raises(ValidationError):
        ItemMatch(
            item_id="t3_001",
            matches=[
                {"event_id": f"evt_{i}", "match_confidence": 0.5,
                 "match_reason": "reason", "evidence_excerpt": "excerpt"}
                for i in range(4)
            ],
        )


def test_batch_match_result_valid():
    result = BatchMatchResult(results=[
        {
            "item_id": "t3_mock001",
            "matches": [
                {
                    "event_id": "evt_001",
                    "match_confidence": 0.88,
                    "match_reason": "Asks about pub quiz",
                    "evidence_excerpt": "Anyone know good pub quiz spots?",
                }
            ],
        },
        {"item_id": "t3_mock002", "matches": []},
    ])
    assert len(result.results) == 2
    assert result.results[0].matches[0].match_confidence == 0.88


# ---------------------------------------------------------------------------
# Schema tests — UserSummary
# ---------------------------------------------------------------------------

def test_user_summary_valid():
    s = UserSummary(
        username="quiz_lover",
        summary="Frequently looks for pub quiz nights in Stockholm.",
    )
    assert s.summary.endswith(".")


def test_user_summary_multi_sentence_trimmed():
    s = UserSummary(
        username="quiz_lover",
        summary="Frequently looks for quiz nights. Also likes climbing.",
    )
    # Should be trimmed to first sentence
    assert s.summary == "Frequently looks for quiz nights."


def test_user_summary_too_long():
    with pytest.raises(ValidationError):
        UserSummary(username="user", summary="x" * 201)


# ---------------------------------------------------------------------------
# LLMClient mock mode tests
# ---------------------------------------------------------------------------

def test_mock_client_plan_scrape_returns_valid_json():
    client = LLMClient(mock_mode=True)
    response = client.plan_scrape("any prompt")
    data = extract_tagged_json(response, "plan")
    assert data is not None
    plan = ScrapePlan(**data)
    assert len(plan.queries) > 0


def test_mock_client_match_batch_returns_valid_json():
    client = LLMClient(mock_mode=True)
    item_ids = ["t3_mock001", "t3_mock002", "t3_mock003", "t3_mock004", "t3_mock005"]
    event_ids = ["evt_sample_001"]
    response = client.match_batch("any prompt", item_ids=item_ids, event_ids=event_ids)
    data = extract_tagged_json(response, "matches")
    assert data is not None
    result = BatchMatchResult(**data)
    assert len(result.results) > 0


def test_mock_client_match_batch_uses_real_item_ids():
    client = LLMClient(mock_mode=True)
    item_ids = ["t3_real_001", "t3_real_002", "t3_real_003"]
    event_ids = ["evt_real_001"]
    response = client.match_batch("prompt", item_ids=item_ids, event_ids=event_ids)
    data = extract_tagged_json(response, "matches")
    result = BatchMatchResult(**data)
    returned_ids = {r.item_id for r in result.results}
    assert "t3_real_001" in returned_ids


def test_mock_client_summarise_user_returns_string():
    client = LLMClient(mock_mode=True)
    summary = client.summarise_user("any prompt", username="test_user")
    assert isinstance(summary, str)
    assert len(summary) > 0


def test_mock_client_no_api_calls():
    """Mock mode should never call the API — no key needed."""
    import os
    original = os.environ.pop("GROQ_API_KEY", None)
    try:
        client = LLMClient(mock_mode=True)
        response = client.complete("hello")
        assert response == ""  # mock complete returns empty string
    finally:
        if original:
            os.environ["GROQ_API_KEY"] = original


# ---------------------------------------------------------------------------
# extract_tagged_json tests
# ---------------------------------------------------------------------------

def test_extract_tagged_json_success():
    text = 'Some text <plan>{"queries": []}</plan> more text'
    result = extract_tagged_json(text, "plan")
    assert result == {"queries": []}


def test_extract_tagged_json_missing_tag():
    result = extract_tagged_json("no tags here", "plan")
    assert result is None


def test_extract_tagged_json_invalid_json():
    result = extract_tagged_json("<plan>not json</plan>", "plan")
    assert result is None


def test_extract_tagged_json_multiline():
    payload = json.dumps({"queries": [{"query": "test", "subreddit": "stockholm", "priority": 1}]})
    text = f"<plan>\n{payload}\n</plan>"
    result = extract_tagged_json(text, "plan")
    assert result is not None
    assert len(result["queries"]) == 1


# ---------------------------------------------------------------------------
# Prompt helper tests
# ---------------------------------------------------------------------------

def test_format_event_list():
    events = [{"event_id": "evt_001", "title": "Pub Quiz", "tags": ["trivia", "nightlife"]}]
    output = format_event_list(events)
    assert "evt_001" in output
    assert "Pub Quiz" in output
    assert "trivia" in output


def test_format_items_list():
    items = [{"item_id": "t3_001", "subreddit": "stockholm", "text": "Looking for pub quiz"}]
    output = format_items_list(items)
    assert "t3_001" in output
    assert "stockholm" in output
