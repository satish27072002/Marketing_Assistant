from pipeline.nodes.match_items import (
    _fallback_social_matches,
    _compile_patterns,
    _infer_source_from_raw_item,
    _is_hard_negative,
    _rerank_matches,
    _social_terms,
)


def test_hard_negative_skips_non_social_text():
    patterns = _compile_patterns([r"\bbest coffee\b"])
    social_terms = _social_terms({"tag_keywords": {"social": ["meet", "friends"]}})
    assert _is_hard_negative("Best coffee spots in Stockholm?", patterns, social_terms)


def test_hard_negative_does_not_skip_if_social_signal_present():
    patterns = _compile_patterns([r"\bbest coffee\b"])
    social_terms = _social_terms({"tag_keywords": {"social": ["meet", "friends"]}})
    assert not _is_hard_negative(
        "Best coffee places to meet new friends in Stockholm",
        patterns,
        social_terms,
    )


def test_rerank_matches_boosts_explicit_and_penalizes_ambiguous():
    matches = [
        {"event_id": "evt1", "match_confidence": 0.6, "match_reason": "x", "evidence_excerpt": "x"},
        {"event_id": "evt2", "match_confidence": 0.58, "match_reason": "x", "evidence_excerpt": "x"},
    ]
    explicit_patterns = _compile_patterns([r"\blooking for\b"])
    ambiguous_patterns = _compile_patterns([r"\bmaybe\b"])
    reranked = _rerank_matches(
        "I am looking for social events, maybe pub quiz",
        matches,
        explicit_patterns=explicit_patterns,
        ambiguous_patterns=ambiguous_patterns,
        future_patterns=_compile_patterns([r"\bnext week\b"]),
        explicit_bonus=0.1,
        ambiguous_penalty=0.05,
        future_penalty=0.1,
    )
    assert len(reranked) == 2
    assert reranked[0]["match_confidence"] >= reranked[1]["match_confidence"]
    assert reranked[0]["match_confidence"] > 0.6


def test_social_fallback_matches_explicit_friend_seeking_text():
    fallback_patterns = _compile_patterns([r"\blooking for (new )?friends?\b"])
    candidate_events = [
        {"event_id": "evt-social", "tags": ["social", "trivia"]},
        {"event_id": "evt-coding", "tags": ["coding"]},
    ]
    matches = _fallback_social_matches(
        "I am new to Stockholm and looking for friends to hang out with",
        candidate_events=candidate_events,
        social_fallback_patterns=fallback_patterns,
    )
    assert len(matches) == 1
    assert matches[0]["event_id"] == "evt-social"
    assert matches[0]["match_confidence"] >= 0.5


def test_social_fallback_does_not_match_without_explicit_social_intent():
    fallback_patterns = _compile_patterns([r"\blooking for (new )?friends?\b"])
    candidate_events = [{"event_id": "evt-social", "tags": ["social"]}]
    matches = _fallback_social_matches(
        "What is the weather like in Stockholm this week?",
        candidate_events=candidate_events,
        social_fallback_patterns=fallback_patterns,
    )
    assert matches == []


def test_future_intent_penalty_reduces_score_for_not_now_text():
    matches = [
        {"event_id": "evt1", "match_confidence": 0.72, "match_reason": "x", "evidence_excerpt": "x"},
    ]
    reranked = _rerank_matches(
        "I am interested but cannot join this week, maybe next week",
        matches,
        explicit_patterns=_compile_patterns([r"\bi am interested\b"]),
        ambiguous_patterns=_compile_patterns([r"\bmaybe\b"]),
        future_patterns=_compile_patterns([r"\bcannot join\b", r"\bnext week\b"]),
        explicit_bonus=0.08,
        ambiguous_penalty=0.05,
        future_penalty=0.15,
    )
    assert len(reranked) == 1
    assert reranked[0]["match_confidence"] < 0.72


def test_infer_source_from_raw_item():
    class Raw:
        def __init__(self, query_used: str, permalink: str):
            self.query_used = query_used
            self.permalink = permalink

    assert _infer_source_from_raw_item("fb_123", None) == "facebook"
    assert _infer_source_from_raw_item("t3_x", Raw("facebook|query", "https://x")) == "facebook"
    assert _infer_source_from_raw_item("t3_y", Raw("reddit|query", "https://www.facebook.com/groups/z")) == "facebook"
    assert _infer_source_from_raw_item("t3_z", Raw("reddit|query", "https://www.reddit.com/r/stockholm")) == "reddit"
