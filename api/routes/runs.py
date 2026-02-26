"""Runs router — pipeline run management + SSE live feed.

Routes:
    GET  /runs              — list runs (newest first)
    GET  /runs/live         — SSE stream of the active run
    GET  /runs/{run_id}     — single run details
    POST /runs              — trigger a new pipeline run
    POST /runs/{run_id}/stop — request graceful stop
"""
import asyncio
import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

# Ensure project root is on path so pipeline imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from db.database import get_db
from db.models import Run
from api.schemas import RunResponse, RunCreatedResponse, SSEUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_to_response(run: Run) -> RunResponse:
    return RunResponse(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        time_window_start=run.time_window_start,
        time_window_end=run.time_window_end,
        items_collected=run.items_collected or 0,
        items_matched=run.items_matched or 0,
        leads_written=run.leads_written or 0,
        estimated_cost_usd=run.estimated_cost_usd or 0.0,
        stop_requested=run.stop_requested or False,
    )


def _run_in_thread(
    mock_mode: bool = False,
    time_window_hours: Optional[int] = None,
    max_items: Optional[int] = None,
    max_queries: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
) -> None:
    """Wrapper that runs the pipeline in a background daemon thread."""
    # Save originals so we can restore after the run
    _saved = {}
    overrides = {
        "MOCK_MODE": "true" if mock_mode else None,
        "TIME_WINDOW_HOURS": str(time_window_hours) if time_window_hours is not None else None,
        "MAX_ITEMS_PER_RUN": str(max_items) if max_items is not None else None,
        "MAX_QUERIES_PER_RUN": str(max_queries) if max_queries is not None else None,
        "MAX_COST_USD": str(max_cost_usd) if max_cost_usd is not None else None,
    }
    for key, val in overrides.items():
        if val is not None:
            _saved[key] = os.environ.get(key)
            os.environ[key] = val
            logger.info("Run override: %s=%s", key, val)

    try:
        from pipeline.graph import run_pipeline
        run_pipeline()
    except Exception as exc:
        logger.error("Background pipeline run failed: %s", exc)
    finally:
        # Restore original env values
        for key, original in _saved.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[RunResponse])
def list_runs(
    status: Optional[str] = Query(None, description="Filter by status: RUNNING, COMPLETED, FAILED, STOPPED"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List pipeline runs, newest first."""
    q = db.query(Run)
    if status:
        q = q.filter(Run.status == status.upper())
    runs = q.order_by(Run.started_at.desc()).offset(offset).limit(limit).all()
    return [_run_to_response(r) for r in runs]


@router.get("/live")
async def live_stream(
    run_id: Optional[str] = Query(None, description="Subscribe to a specific run. If omitted, streams the latest active run."),
    db: Session = Depends(get_db),
):
    """Server-Sent Events stream — emits run status every 3 seconds.

    Stops automatically when the run reaches a terminal state (COMPLETED/FAILED/STOPPED)
    or after a 30-minute safety timeout.
    """
    async def event_generator():
        deadline = asyncio.get_event_loop().time() + 30 * 60  # 30 min timeout

        while True:
            now = asyncio.get_event_loop().time()
            if now > deadline:
                yield {"data": json.dumps({"event": "timeout"})}
                break

            # Fresh session per poll to avoid stale cache
            from db.database import SessionLocal
            poll_db = SessionLocal()
            try:
                if run_id:
                    run = poll_db.query(Run).filter(Run.run_id == run_id).first()
                else:
                    run = (
                        poll_db.query(Run)
                        .order_by(Run.started_at.desc())
                        .first()
                    )

                if run is None:
                    yield {"data": json.dumps({"event": "no_run"})}
                    await asyncio.sleep(3)
                    continue

                # Compute budget status from cost fields
                max_cost = float(os.environ.get("MAX_COST_USD", "5.00"))
                cost = run.estimated_cost_usd or 0.0
                pct = (cost / max_cost * 100) if max_cost > 0 else 0
                if pct >= 90:
                    budget_status = "DEGRADED"
                elif pct >= 75:
                    budget_status = "WARNING"
                elif pct >= 50:
                    budget_status = "YELLOW"
                else:
                    budget_status = "OK"

                # Count errors from error_log JSON field
                error_count = 0
                if run.error_log:
                    try:
                        error_count = len(json.loads(run.error_log))
                    except (json.JSONDecodeError, TypeError):
                        pass

                update = SSEUpdate(
                    run_id=run.run_id,
                    status=run.status,
                    items_collected=run.items_collected or 0,
                    items_matched=run.items_matched or 0,
                    leads_found=run.leads_written or 0,
                    estimated_cost_usd=cost,
                    budget_status=budget_status,
                    errors=error_count,
                )
                yield {"data": update.model_dump_json()}

                # Stop streaming if run is in a terminal state
                if run.status in {"COMPLETED", "FAILED", "STOPPED"}:
                    break

            finally:
                poll_db.close()

            await asyncio.sleep(3)

    return EventSourceResponse(event_generator())


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """Get a single run by ID."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return _run_to_response(run)


@router.post("", response_model=RunCreatedResponse, status_code=202)
def trigger_run(
    mock: bool = Query(False, description="Run in mock mode (no API calls, no Reddit)"),
    time_window_hours: Optional[int] = Query(None, ge=1, le=720, description="How many hours back to search Reddit (default: from config)"),
    max_items: Optional[int] = Query(None, ge=1, le=500, description="Max posts sent to LLM for matching"),
    max_queries: Optional[int] = Query(None, ge=1, le=100, description="Max search queries the LLM generates"),
    max_cost_usd: Optional[float] = Query(None, ge=0.01, le=50.0, description="Budget ceiling in USD"),
):
    """Trigger a new pipeline run. Returns immediately; run executes in background."""
    thread = threading.Thread(
        target=_run_in_thread,
        kwargs=dict(
            mock_mode=mock,
            time_window_hours=time_window_hours,
            max_items=max_items,
            max_queries=max_queries,
            max_cost_usd=max_cost_usd,
        ),
        daemon=True,
        name="pipeline-run",
    )
    thread.start()

    # Give the thread a moment to register the run_id in DB
    import time
    time.sleep(0.5)

    # Fetch the most recently created run to return its ID
    from db.database import SessionLocal
    tmp_db = SessionLocal()
    try:
        run = tmp_db.query(Run).order_by(Run.started_at.desc()).first()
        if run:
            return RunCreatedResponse(run_id=run.run_id, status=run.status)
        # Thread may not have written yet — return placeholder
        return RunCreatedResponse(run_id="starting", status="RUNNING")
    finally:
        tmp_db.close()


@router.post("/{run_id}/stop", status_code=200)
def stop_run(run_id: str, db: Session = Depends(get_db)):
    """Request a graceful stop for the given run.
    The pipeline checks this flag between batches and finalises cleanly.
    """
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    if run.status not in {"RUNNING"}:
        raise HTTPException(
            status_code=400,
            detail=f"Run is already in terminal state: {run.status}",
        )
    run.stop_requested = True
    db.commit()
    return {"run_id": run_id, "message": "Stop requested. Run will finish current batch then stop."}
