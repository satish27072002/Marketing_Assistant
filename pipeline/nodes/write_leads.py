"""Node I — WriteLeadsNode

For each UserAggregate:
  - Checks if (source, username, primary_event_id) already exists — skips if so
  - Inserts new leads with status = NEW
  - Updates the runs table with leads_written count

Output: number of leads written
"""
import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import Lead, Run
from pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def write_leads_node(state: PipelineState) -> PipelineState:
    user_aggregates: list[dict] = state.get("user_aggregates", [])
    run_id = state.get("run_id", "dev-run")
    leads_written = 0

    if not user_aggregates:
        logger.info("WriteLeadsNode: no user aggregates to write")
        return {**state, "leads_written": 0}

    db: Session = SessionLocal()

    try:
        for agg in user_aggregates:
            # Dedup check: skip if this user+event combo already exists
            existing = (
                db.query(Lead)
                .filter(
                    Lead.source == agg["source"],
                    Lead.username == agg["username"],
                    Lead.primary_event_id == agg["primary_event_id"],
                )
                .first()
            )
            if existing:
                logger.debug(
                    "Lead already exists for user=%s event=%s — skipping",
                    agg["username"], agg["primary_event_id"],
                )
                continue

            lead = Lead(
                source=agg["source"],
                username=agg["username"],
                profile_url=agg.get("profile_url"),
                primary_event_id=agg["primary_event_id"],
                other_event_ids=agg.get("other_event_ids", ""),
                top_confidence=agg["top_confidence"],
                user_summary=agg.get("user_summary"),
                evidence_excerpts=json.dumps(agg.get("evidence_excerpts", [])),
                evidence_urls=json.dumps(agg.get("evidence_urls", [])),
                status="NEW",
                prompt_version=agg.get("prompt_version", 1),
            )

            try:
                db.add(lead)
                db.flush()
                leads_written += 1
            except IntegrityError:
                db.rollback()
                logger.debug(
                    "Integrity error for user=%s — already exists", agg["username"]
                )
                continue

        # Update runs table
        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run:
            run.leads_written = leads_written

        db.commit()
        logger.info("WriteLeadsNode: wrote %d new leads", leads_written)

    finally:
        db.close()

    return {**state, "leads_written": leads_written}
