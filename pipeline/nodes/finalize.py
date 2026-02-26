"""Node J — FinalizeNode

  - Marks all raw_items from this run as processed
  - Writes final stats to the runs table (status=COMPLETED/FAILED)
  - Checks processing_queue for PENDING or FAILED items → writes to recovery_queue.json
  - Runs retention cleanup: deletes raw_items older than 30 days
  - Triggers failure alert if error count exceeds 20% of items processed

Output: run complete
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import yaml
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import ProcessingQueue, RawItem, Run
from pipeline.state import PipelineState

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
RECOVERY_QUEUE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "recovery_queue.json"
)


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def finalize_node(state: PipelineState) -> PipelineState:
    config = _load_config()
    run_id = state.get("run_id", "dev-run")
    budget = state.get("budget")
    errors: list[str] = state.get("errors", [])
    leads_written = state.get("leads_written", 0)
    retention_days = config.get("retention_days", 30)

    db: Session = SessionLocal()

    try:
        # --- Mark all raw_items from this run as processed ---
        db.query(RawItem).filter(
            RawItem.run_id == run_id,
            RawItem.processed == False,  # noqa: E712
        ).update({"processed": True}, synchronize_session=False)

        # --- Count items for stats ---
        items_collected = (
            db.query(RawItem).filter(RawItem.run_id == run_id).count()
        )
        items_matched = (
            db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.run_id == run_id,
                ProcessingQueue.status == "DONE",
            )
            .count()
        )

        # --- Failure alert ---
        error_count = len(errors)
        if items_collected > 0:
            error_pct = (error_count / items_collected) * 100
            if error_pct > 20:
                logger.error(
                    "HIGH ERROR RATE: %.1f%% of items failed (%d errors / %d items)",
                    error_pct, error_count, items_collected,
                )

        # --- Determine final status ---
        stop_requested = budget.stop_requested if budget else False
        final_status = "STOPPED" if stop_requested else "COMPLETED"
        estimated_cost = budget.estimated_cost_usd if budget else 0.0

        # --- Write final stats to runs table ---
        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run:
            run.completed_at = datetime.now(tz=timezone.utc)
            run.status = final_status
            run.items_collected = items_collected
            run.items_matched = items_matched
            run.leads_written = leads_written
            run.estimated_cost_usd = estimated_cost
            run.error_log = json.dumps(errors) if errors else None

        # --- Recovery queue: PENDING or FAILED items ---
        unfinished = (
            db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.run_id == run_id,
                ProcessingQueue.status.in_(["PENDING", "FAILED"]),
            )
            .all()
        )
        if unfinished:
            recovery_ids = [q.item_id for q in unfinished]
            _write_recovery_queue(recovery_ids)
            logger.info(
                "FinalizeNode: %d items written to recovery queue", len(recovery_ids)
            )
        else:
            _write_recovery_queue([])

        # --- Retention cleanup ---
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
        deleted = (
            db.query(RawItem)
            .filter(RawItem.created_utc < cutoff)
            .delete(synchronize_session=False)
        )
        if deleted:
            logger.info("FinalizeNode: deleted %d raw_items older than %d days", deleted, retention_days)

        db.commit()

        logger.info(
            "FinalizeNode: run %s → %s | collected=%d matched=%d leads=%d cost=$%.4f errors=%d",
            run_id, final_status, items_collected, items_matched,
            leads_written, estimated_cost, error_count,
        )

    finally:
        db.close()

    return state


def _write_recovery_queue(item_ids: list[str]) -> None:
    try:
        os.makedirs(os.path.dirname(RECOVERY_QUEUE_PATH), exist_ok=True)
        with open(RECOVERY_QUEUE_PATH, "w") as f:
            json.dump(item_ids, f, indent=2)
    except OSError as e:
        logger.warning("Could not write recovery queue: %s", e)
