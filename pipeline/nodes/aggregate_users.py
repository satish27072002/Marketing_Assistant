"""Node H — AggregateUserInterestsNode

Deterministic aggregation (no LLM cost):
  - Groups user_event_affinity rows by username
  - Sorts by confidence, takes top 3 events per user
  - Collects up to 3 evidence excerpts

Then one small LLM call per user generates a single-sentence interest summary.
If the LLM call fails: a template fallback is used — no run impact.

Output: list of user aggregate dicts
"""
import logging
import os
import re
from collections import defaultdict

from dotenv import load_dotenv
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import RawItem, UserEventAffinity
from llm.client import LLMClient
from llm.prompts import SUMMARY_PROMPT_V, SUMMARY_PROMPT_TEMPLATE, format_evidence_list
from llm.schemas import UserSummary
from pipeline.state import PipelineState

load_dotenv()
logger = logging.getLogger(__name__)

_FB_GROUP_URL_RE = re.compile(
    r"(https?://(?:www\.)?facebook\.com/groups/[^/?#]+)",
    re.IGNORECASE,
)


def _facebook_group_url(url: str | None) -> str | None:
    if not url:
        return None
    m = _FB_GROUP_URL_RE.search(url)
    if not m:
        return None
    return m.group(1).rstrip("/") + "/"


def _template_summary(username: str, top_events: list[str]) -> str:
    if top_events:
        return f"Interested in social events including {', '.join(top_events[:2])} in Stockholm."
    return "Interested in social events and meetups in Stockholm."


def aggregate_users_node(state: PipelineState) -> PipelineState:
    run_cfg = state.get("run_config", {})
    mock_mode = bool(
        run_cfg.get(
            "mock_mode",
            os.environ.get("MOCK_MODE", "false").lower() == "true",
        )
    )
    run_id = state.get("run_id", "dev-run")
    budget = state.get("budget")

    client = LLMClient(mock_mode=mock_mode)
    db: Session = SessionLocal()
    user_aggregates = []

    try:
        # Load all affinity rows written during this run's items
        # (join via evidence_item_id → raw_items → run_id)
        run_item_ids = (
            db.query(RawItem.item_id)
            .filter(RawItem.run_id == run_id)
            .subquery()
            .select()
        )
        affinities = (
            db.query(UserEventAffinity)
            .filter(UserEventAffinity.evidence_item_id.in_(run_item_ids))
            .all()
        )

        if not affinities:
            logger.info("AggregateUsersNode: no affinity rows for run %s", run_id)
            return {**state, "user_aggregates": []}

        # Group by (source, username)
        grouped: dict[tuple, list[UserEventAffinity]] = defaultdict(list)
        for row in affinities:
            grouped[(row.source, row.username)].append(row)

        for (source, username), rows in grouped.items():
            # Sort by confidence descending
            rows.sort(key=lambda r: r.match_confidence, reverse=True)

            # Top 3 unique events
            seen_events: set[str] = set()
            top_events: list[str] = []
            top_confidence = 0.0
            primary_event_id = None
            other_event_ids: list[str] = []

            for row in rows:
                if row.event_id not in seen_events:
                    seen_events.add(row.event_id)
                    top_events.append(row.event_id)
                    if primary_event_id is None:
                        primary_event_id = row.event_id
                        top_confidence = row.match_confidence
                    else:
                        other_event_ids.append(row.event_id)
                if len(top_events) >= 3:
                    break

            if primary_event_id is None:
                continue

            # Collect up to 3 evidence excerpts
            excerpts = [
                r.evidence_excerpt for r in rows[:3]
                if r.evidence_excerpt
            ]
            evidence_item_ids = [r.evidence_item_id for r in rows[:3]]
            raw_rows = (
                db.query(RawItem.item_id, RawItem.permalink)
                .filter(RawItem.item_id.in_(evidence_item_ids))
                .all()
            )
            permalink_map = {item_id: permalink for item_id, permalink in raw_rows}
            evidence_urls = [
                permalink_map[item_id]
                for item_id in evidence_item_ids
                if permalink_map.get(item_id)
            ]
            profile_url = rows[0].profile_url if rows else None
            if not profile_url and source == "facebook":
                for evidence_url in evidence_urls:
                    group_url = _facebook_group_url(evidence_url)
                    if group_url:
                        profile_url = group_url
                        break

            # Generate LLM summary
            summary = None
            try:
                prompt = SUMMARY_PROMPT_TEMPLATE.format(
                    username=username,
                    evidence_list=format_evidence_list(excerpts),
                )
                raw = client.summarise_user(prompt, username=username)
                if raw.strip():
                    validated = UserSummary(username=username, summary=raw.strip())
                    summary = validated.summary
            except (ValidationError, Exception) as e:
                logger.debug("Summary LLM call failed for %s: %s — using fallback", username, e)

            if not summary:
                summary = _template_summary(username, top_events)

            user_aggregates.append({
                "source": source,
                "username": username,
                "profile_url": profile_url,
                "primary_event_id": primary_event_id,
                "other_event_ids": ",".join(other_event_ids),
                "top_confidence": top_confidence,
                "user_summary": summary,
                "evidence_excerpts": excerpts,
                "evidence_urls": evidence_urls,
                "prompt_version": SUMMARY_PROMPT_V,
            })

        # Update budget
        if budget:
            budget.estimated_cost_usd += client.total_estimated_cost
            budget.llm_calls_made += client.total_calls

        logger.info(
            "AggregateUsersNode: aggregated %d unique users", len(user_aggregates)
        )

    finally:
        db.close()

    return {**state, "user_aggregates": user_aggregates}
