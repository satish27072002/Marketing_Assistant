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
    {"query": "social events stockholm", "subreddit": "stockholm", "priority": 2, "source": "reddit"},
    {"query": "meet new people stockholm", "subreddit": "StockholmSocialClub", "priority": 2, "source": "reddit"},
    {"query": "events activities newcomer sweden", "subreddit": "TillSverige", "priority": 1, "source": "reddit"},
]
DEFAULT_FACEBOOK_QUERY_TEXTS = [
    "new to stockholm looking for friends",
    "would love to join social events",
    "looking for group activities stockholm",
]


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _clamp_query(query: str) -> str:
    words = query.strip().split()
    return " ".join(words[:MAX_QUERY_WORDS])


def validate_and_clamp_plan_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    run_cfg = state.get("run_config", {})
    sources_cfg = config.get("sources") or {}
    enabled_sources_cfg = sources_cfg.get("enabled") or ["reddit"]
    enabled_sources = {
        str(src).strip().lower()
        for src in run_cfg.get("sources", enabled_sources_cfg)
        if str(src).strip()
    }
    if not enabled_sources:
        enabled_sources = {"reddit"}

    allowed_subreddits = set(config.get("subreddits") or [])
    facebook_cfg = config.get("facebook") or {}
    allowed_facebook_groups = set(facebook_cfg.get("groups") or [])
    budget_cfg = config.get("budget", {})
    max_queries = int(run_cfg.get("max_queries", budget_cfg.get("max_queries_per_run", MAX_QUERIES)))

    scrape_plan = state.get("scrape_plan", {})
    queries = scrape_plan.get("queries", []) if isinstance(scrape_plan, dict) else []

    if not queries:
        logger.warning("ValidateAndClampPlanNode: empty plan — using safe default")
        queries = DEFAULT_QUERIES

    normalized: list[dict] = []
    removed = 0
    for q in queries:
        source = str(q.get("source", "reddit")).strip().lower() or "reddit"
        if source not in enabled_sources:
            removed += 1
            continue
        community = str(q.get("subreddit", "")).strip()
        if source == "reddit" and community not in allowed_subreddits:
            removed += 1
            continue
        if source == "facebook" and community not in allowed_facebook_groups:
            removed += 1
            continue
        normalized.append({
            "query": q.get("query", ""),
            "subreddit": community,
            "priority": int(q.get("priority", 0)),
            "source": source,
        })
    queries = normalized
    if removed:
        logger.info("Removed %d queries by source/community allowlist", removed)

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
        if "reddit" in enabled_sources:
            queries.extend([q for q in DEFAULT_QUERIES if q["subreddit"] in allowed_subreddits])

    # If facebook is enabled, synthesize group queries from best reddit query texts.
    if "facebook" in enabled_sources and allowed_facebook_groups:
        fb_existing = [q for q in queries if q.get("source") == "facebook"]
        if not fb_existing:
            reddit_texts = []
            seen_texts = set()
            for q in sorted(
                [x for x in queries if x.get("source") == "reddit"],
                key=lambda x: x.get("priority", 0),
                reverse=True,
            ):
                text = str(q.get("query", "")).strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                reddit_texts.append(text)
            if not reddit_texts:
                reddit_texts = list(DEFAULT_FACEBOOK_QUERY_TEXTS)

            queries_per_group = int(facebook_cfg.get("queries_per_group", 2))
            for group in allowed_facebook_groups:
                for text in reddit_texts[:max(1, queries_per_group)]:
                    queries.append(
                        {
                            "query": text,
                            "subreddit": group,
                            "priority": 1,
                            "source": "facebook",
                        }
                    )

    # Deduplicate by (source, subreddit, query)
    deduped = []
    seen = set()
    for q in queries:
        key = (q.get("source", "reddit"), q.get("subreddit", ""), q.get("query", "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    queries = deduped

    reddit_queries = sorted(
        [q for q in queries if q.get("source") == "reddit"],
        key=lambda x: x.get("priority", 0),
        reverse=True,
    )
    facebook_queries = sorted(
        [q for q in queries if q.get("source") == "facebook"],
        key=lambda x: x.get("priority", 0),
        reverse=True,
    )

    if reddit_queries and facebook_queries:
        fb_cap = int(facebook_cfg.get("max_queries_per_run", max(1, max_queries // 2)))
        fb_target = min(len(facebook_queries), max(1, max_queries // 3), max(1, fb_cap))
        rd_target = max(0, max_queries - fb_target)
        selected = reddit_queries[:rd_target] + facebook_queries[:fb_target]
        if len(selected) < max_queries:
            selected.extend(reddit_queries[rd_target: max_queries - len(selected)])
        if len(selected) < max_queries:
            selected.extend(facebook_queries[fb_target: max_queries - len(selected)])
        queries = selected[:max_queries]
    else:
        queries = (reddit_queries + facebook_queries)[:max_queries]

    logger.info("ValidateAndClampPlanNode: %d validated queries", len(queries))
    return {**state, "validated_plan": {"queries": queries}}
