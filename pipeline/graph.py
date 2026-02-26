"""pipeline/graph.py — LangGraph assembly and pipeline entry point.

Wires all 10 nodes (A→J) into a sequential StateGraph.
Call run_pipeline() to execute a full run.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import yaml
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from db.database import SessionLocal
from db.models import Run
from pipeline.budget import RunBudget
from pipeline.state import PipelineState
from pipeline.nodes.load_events import load_events_node
from pipeline.nodes.upsert_event_index import upsert_event_index_node
from pipeline.nodes.plan_scrape import plan_scrape_node
from pipeline.nodes.validate_plan import validate_and_clamp_plan_node
from pipeline.nodes.collect_reddit import collect_reddit_node
from pipeline.nodes.select_items import select_items_node
from pipeline.nodes.match_items import match_items_node
from pipeline.nodes.aggregate_users import aggregate_users_node
from pipeline.nodes.write_leads import write_leads_node
from pipeline.nodes.finalize import finalize_node

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("load_events", load_events_node)               # A
    graph.add_node("upsert_event_index", upsert_event_index_node) # B
    graph.add_node("plan_scrape", plan_scrape_node)               # C
    graph.add_node("validate_plan", validate_and_clamp_plan_node) # D
    graph.add_node("collect_reddit", collect_reddit_node)         # E
    graph.add_node("select_items", select_items_node)             # F
    graph.add_node("match_items", match_items_node)               # G
    graph.add_node("aggregate_users", aggregate_users_node)       # H
    graph.add_node("write_leads", write_leads_node)               # I
    graph.add_node("finalize", finalize_node)                     # J

    graph.set_entry_point("load_events")
    graph.add_edge("load_events", "upsert_event_index")
    graph.add_edge("upsert_event_index", "plan_scrape")
    graph.add_edge("plan_scrape", "validate_plan")
    graph.add_edge("validate_plan", "collect_reddit")
    graph.add_edge("collect_reddit", "select_items")
    graph.add_edge("select_items", "match_items")
    graph.add_edge("match_items", "aggregate_users")
    graph.add_edge("aggregate_users", "write_leads")
    graph.add_edge("write_leads", "finalize")
    graph.add_edge("finalize", END)

    return graph


def run_pipeline() -> dict:
    """Execute a full pipeline run. Returns the final state."""
    config = _load_config()
    budget_cfg = config.get("budget", {})
    time_window_hours = int(os.environ.get("TIME_WINDOW_HOURS", budget_cfg.get("time_window_hours", 48)))

    now = datetime.now(tz=timezone.utc)
    run_id = str(uuid.uuid4())

    budget = RunBudget(
        time_window_start=now - timedelta(hours=time_window_hours),
        time_window_end=now,
        max_queries=budget_cfg.get("max_queries_per_run", 20),
        max_items_per_run=budget_cfg.get("max_items_per_run", 100),
        max_cost_usd=float(os.environ.get("MAX_COST_USD", budget_cfg.get("max_cost_usd", 5.00))),
    )

    # Create run record in DB
    db = SessionLocal()
    try:
        run = Run(
            run_id=run_id,
            started_at=now,
            status="RUNNING",
            time_window_start=budget.time_window_start,
            time_window_end=budget.time_window_end,
        )
        db.add(run)
        db.commit()
        logger.info("Started run %s", run_id)
    finally:
        db.close()

    initial_state: PipelineState = {
        "run_id": run_id,
        "budget": budget,
        "errors": [],
    }

    graph = build_graph()
    app = graph.compile()

    try:
        final_state = app.invoke(initial_state)
        logger.info(
            "Run %s complete — leads=%d cost=$%.4f",
            run_id,
            final_state.get("leads_written", 0),
            budget.estimated_cost_usd,
        )
        return final_state
    except Exception as e:
        logger.error("Pipeline run %s failed: %s", run_id, e)
        # Mark run as FAILED
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = "FAILED"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.error_log = json.dumps([str(e)])
                db.commit()
        finally:
            db.close()
        raise
