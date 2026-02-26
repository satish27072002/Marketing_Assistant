"""Node C — PlanScrapeNode

Single LLM call per run. Receives compact event list, allowed subreddit list,
time window, and max query budget. Returns a scrape plan JSON.

Prompt version stored as PLANNER_PROMPT_V.
Output: scrape plan dict (validated by Node D)
"""
import logging
import os

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from llm.client import LLMClient, extract_tagged_json
from llm.prompts import (
    PLANNER_PROMPT_V,
    PLANNER_PROMPT_TEMPLATE,
    format_event_list,
)
from llm.schemas import ScrapePlan
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def plan_scrape_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    mock_mode = os.environ.get("MOCK_MODE", "false").lower() == "true"
    budget = state.get("budget")

    events = state.get("events", [])
    if not events:
        logger.warning("PlanScrapeNode: no events loaded, using empty plan")
        return {**state, "scrape_plan": {"queries": []}}

    subreddits = config.get("subreddits", [])
    budget_cfg = config.get("budget", {})
    max_queries = int(os.environ.get("MAX_QUERIES_PER_RUN", budget_cfg.get("max_queries_per_run", 20)))
    time_window_hours = int(os.environ.get("TIME_WINDOW_HOURS", 48))

    event_dicts = [
        {"event_id": e.event_id, "title": e.title, "tags": e.tags}
        for e in events
    ]

    prompt = PLANNER_PROMPT_TEMPLATE.format(
        event_list=format_event_list(event_dicts),
        subreddits="\n".join(f"- {s}" for s in subreddits),
        time_window_hours=time_window_hours,
        max_queries=max_queries,
    )

    client = LLMClient(mock_mode=mock_mode)
    raw_response = client.plan_scrape(prompt)

    # Update budget cost estimate
    if budget:
        budget.estimated_cost_usd += client.total_estimated_cost
        budget.llm_calls_made += client.total_calls

    raw_json = extract_tagged_json(raw_response, "plan")
    if not raw_json:
        logger.warning("PlanScrapeNode: could not parse plan response, using empty plan")
        return {**state, "scrape_plan": {"queries": []}}

    try:
        plan = ScrapePlan(**raw_json)
        logger.info(
            "PlanScrapeNode: generated %d queries (prompt_v=%d)",
            len(plan.queries), PLANNER_PROMPT_V,
        )
        return {**state, "scrape_plan": plan.model_dump()}
    except ValidationError as e:
        logger.warning("PlanScrapeNode: plan validation failed: %s", e)
        return {**state, "scrape_plan": {"queries": []}}
