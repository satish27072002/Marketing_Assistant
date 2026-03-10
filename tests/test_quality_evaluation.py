from quality.evaluation import evaluate_rows, recommend_thresholds_by_tag, sweep_thresholds


def _row(item_id: str, confidence: float, label: str, text: str, event_id: str = "evt1"):
    return {
        "item_id": item_id,
        "username": f"user_{item_id}",
        "subreddit": "stockholm",
        "text": text,
        "event_id": event_id,
        "event_title": "Event",
        "current_confidence": confidence,
        "source_link": f"https://x/{item_id}",
        "timestamp": "2025-01-01T12:00:00+00:00",
        "label": label,
        "label_reason": "",
        "reviewer": "r1",
        "reviewed_at": "2025-01-02T12:00:00+00:00",
        "age_hours": 12.0,
    }


def test_evaluate_rows_outputs_precision_and_confusion():
    rows = [
        _row("a", 0.9, "GOOD_MATCH", "Looking for people to join coding meetup", event_id="evt_code"),
        _row("b", 0.8, "BAD_MATCH", "Best coffee in sodermalm?", event_id="evt_social"),
        _row("c", 0.4, "GOOD_MATCH", "New to Stockholm and want to meet people", event_id="evt_social"),
    ]
    events = {
        "evt_code": {"tags": ["coding"], "event_title": "Coding"},
        "evt_social": {"tags": ["social"], "event_title": "Social"},
    }
    summary = evaluate_rows(rows, event_lookup=events, ks=[1, 2])
    assert summary["overall"]["rows_labeled"] == 3
    assert 0.0 <= summary["overall"]["precision"] <= 1.0
    assert "by_subreddit" in summary["confusion"]
    assert "error_buckets" in summary


def test_threshold_sweep_and_tag_recommendations():
    rows = [
        _row("a", 0.9, "GOOD_MATCH", "Looking for join", event_id="evt_code"),
        _row("b", 0.7, "BAD_MATCH", "Vague maybe", event_id="evt_code"),
        _row("c", 0.6, "GOOD_MATCH", "Looking for join", event_id="evt_social"),
        _row("d", 0.5, "BAD_MATCH", "Open to ideas", event_id="evt_social"),
    ]
    for row in rows:
        row["event_tag"] = "coding" if row["event_id"] == "evt_code" else "social"

    sweep = sweep_thresholds(rows, [0.5, 0.6, 0.7])
    assert len(sweep) == 3
    rec = recommend_thresholds_by_tag(rows, [0.5, 0.6, 0.7])
    assert "coding" in rec
    assert "social" in rec

