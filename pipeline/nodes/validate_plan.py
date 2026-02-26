"""Node D — ValidateAndClampPlanNode (deterministic, no LLM)

Hard-coded safety rules applied to the raw scrape plan from Node C:
  - Subreddits must be in the config.yaml allowlist (others silently removed)
  - Max 20 queries (sorted by priority, extras truncated)
  - Each query clamped to 10 words max
  - If plan is empty or malformed: falls back to a safe default plan
  - Never crashes

Output: validated plan dict
"""
import logging
import os

import yaml

from pipeline.state import PipelineState

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")

MAX_QUERIES = 20
MAX_QUERY_WORDS = 10

DEFAULT_QUERIES = [
    {"query": "social events stockholm", "subreddit": "stockholm", "priority": 2},
    {"query": "meet new people stockholm", "subreddit": "StockholmSocialClub", "priority": 2},
    {"query": "events activities newcomer sweden", "subreddit": "TillSverige", "priority": 1},
]


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _clamp_query(query: str) -> str:
    words = query.strip().split()
    return " ".join(words[:MAX_QUERY_WORDS])


def validate_and_clamp_plan_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    allowed_subreddits = set(config.get("subreddits", []))
    budget_cfg = config.get("budget", {})
    max_queries = budget_cfg.get("max_queries_per_run", MAX_QUERIES)

    scrape_plan = state.get("scrape_plan", {})
    queries = scrape_plan.get("queries", []) if isinstance(scrape_plan, dict) else []

    if not queries:
        logger.warning("ValidateAndClampPlanNode: empty plan — using safe default")
        queries = DEFAULT_QUERIES

    # Filter: only allowed subreddits
    before = len(queries)
    queries = [q for q in queries if q.get("subreddit") in allowed_subreddits]
    removed = before - len(queries)
    if removed:
        logger.info("Removed %d queries with disallowed subreddits", removed)

    # Clamp: max words per query
    for q in queries:
        original = q.get("query", "")
        clamped = _clamp_query(original)
        if clamped != original:
            logger.debug("Clamped query %r → %r", original, clamped)
            q["query"] = clamped

    # Remove any queries with empty text after clamping
    queries = [q for q in queries if q.get("query", "").strip()]

    # Fallback if everything was filtered out
    if not queries:
        logger.warning("All queries filtered — using safe default plan")
        queries = [q for q in DEFAULT_QUERIES if q["subreddit"] in allowed_subreddits]

    # Sort by priority descending, truncate to max
    queries = sorted(queries, key=lambda x: x.get("priority", 0), reverse=True)
    queries = queries[:max_queries]

    logger.info("ValidateAndClampPlanNode: %d validated queries", len(queries))
    return {**state, "validated_plan": {"queries": queries}}
