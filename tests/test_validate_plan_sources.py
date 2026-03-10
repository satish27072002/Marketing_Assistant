from pipeline.nodes.validate_plan import validate_and_clamp_plan_node


def test_validate_plan_adds_facebook_queries_when_enabled(monkeypatch):
    cfg = {
        "subreddits": ["stockholm"],
        "budget": {"max_queries_per_run": 6},
        "sources": {"enabled": ["reddit", "facebook"]},
        "facebook": {
            "groups": ["Stockholm Expats"],
            "queries_per_group": 1,
            "max_queries_per_run": 2,
        },
    }
    monkeypatch.setattr("pipeline.nodes.validate_plan._load_config", lambda: cfg)

    state = {
        "run_config": {"sources": ["reddit", "facebook"], "max_queries": 6},
        "scrape_plan": {
            "queries": [
                {"query": "new to stockholm looking for friends", "subreddit": "stockholm", "priority": 3},
            ]
        },
    }

    out = validate_and_clamp_plan_node(state)
    queries = out["validated_plan"]["queries"]
    assert any(q.get("source") == "reddit" for q in queries)
    assert any(q.get("source") == "facebook" for q in queries)
    fb = [q for q in queries if q.get("source") == "facebook"]
    assert all(q["subreddit"] == "Stockholm Expats" for q in fb)


def test_validate_plan_filters_disallowed_source_community(monkeypatch):
    cfg = {
        "subreddits": ["stockholm"],
        "budget": {"max_queries_per_run": 5},
        "sources": {"enabled": ["reddit", "facebook"]},
        "facebook": {"groups": ["Group A"], "queries_per_group": 1},
    }
    monkeypatch.setattr("pipeline.nodes.validate_plan._load_config", lambda: cfg)

    state = {
        "run_config": {"sources": ["reddit", "facebook"], "max_queries": 5},
        "scrape_plan": {
            "queries": [
                {"query": "hello", "subreddit": "not-allowed", "priority": 1, "source": "reddit"},
                {"query": "hej", "subreddit": "Group B", "priority": 1, "source": "facebook"},
            ]
        },
    }
    out = validate_and_clamp_plan_node(state)
    queries = out["validated_plan"]["queries"]
    assert all(
        (q["source"] == "reddit" and q["subreddit"] == "stockholm")
        or (q["source"] == "facebook" and q["subreddit"] == "Group A")
        for q in queries
    )
