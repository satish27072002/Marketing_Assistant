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
import uuid
from datetime import date, datetime, time as dt_time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
import yaml

# Ensure project root is on path so pipeline imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from db.database import SessionLocal, get_db
from db.models import Run
from api.schemas import RunResponse, RunCreatedResponse, SSEUpdate

logger = logging.getLogger(__name__)
router = APIRouter()
_RUN_START_LOCK = threading.Lock()
_RUN_META_LOCK = threading.Lock()
_RUN_MAX_COST_BY_ID: dict[str, float] = {}
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")

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


def _default_max_cost_usd() -> float:
    try:
        with open(_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f) or {}
        return float(config.get("budget", {}).get("max_cost_usd", 5.0))
    except Exception:
        return float(os.environ.get("MAX_COST_USD", "5.00"))


def _max_cost_for_run(run_id: str) -> float:
    with _RUN_META_LOCK:
        if run_id in _RUN_MAX_COST_BY_ID:
            return _RUN_MAX_COST_BY_ID[run_id]
    return _default_max_cost_usd()


def _date_range_to_utc_window(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Convert local date range to UTC datetimes (inclusive end date)."""
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    now_local = datetime.now(local_tz)

    start_local = datetime.combine(start_date, dt_time.min, tzinfo=local_tz)
    if end_date == now_local.date():
        end_local = now_local
    else:
        end_local = datetime.combine(end_date, dt_time.max, tzinfo=local_tz)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _run_in_thread(
    run_id: str,
    mock_mode: bool = False,
    time_window_hours: Optional[int] = None,
    time_window_start: Optional[datetime] = None,
    time_window_end: Optional[datetime] = None,
    max_items: Optional[int] = None,
    max_queries: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    sources: Optional[list[str]] = None,
) -> None:
    """Wrapper that runs the pipeline in a background daemon thread."""
    try:
        from pipeline.graph import run_pipeline
        run_pipeline(
            run_id=run_id,
            mock_mode=mock_mode,
            time_window_hours=time_window_hours,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            max_items=max_items,
            max_queries=max_queries,
            max_cost_usd=max_cost_usd,
            sources=sources,
        )
    except Exception as exc:
        logger.error("Background pipeline run failed: %s", exc)


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
                max_cost = _max_cost_for_run(run.run_id)
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
    start_date: Optional[date] = Query(None, description="Optional explicit start date (YYYY-MM-DD, local timezone)."),
    end_date: Optional[date] = Query(None, description="Optional explicit end date (YYYY-MM-DD, local timezone)."),
    max_items: Optional[int] = Query(None, ge=1, le=500, description="Max posts sent to LLM for matching"),
    max_queries: Optional[int] = Query(None, ge=1, le=100, description="Max search queries the LLM generates"),
    max_cost_usd: Optional[float] = Query(None, ge=0.01, le=50.0, description="Budget ceiling in USD"),
    sources: Optional[str] = Query(
        None,
        description="Comma-separated sources to run, e.g. reddit or reddit,facebook",
    ),
):
    """Trigger a new pipeline run. Returns immediately; run executes in background."""
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="Provide both start_date and end_date together.",
        )
    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="end_date must be on or after start_date.",
        )
    if start_date and end_date and time_window_hours is not None:
        raise HTTPException(
            status_code=422,
            detail="Use either time_window_hours or start_date/end_date, not both.",
        )

    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    if start_date and end_date:
        time_window_start, time_window_end = _date_range_to_utc_window(start_date, end_date)

    parsed_sources: Optional[list[str]] = None
    if sources is not None:
        parsed_sources = [s.strip().lower() for s in sources.split(",") if s.strip()]
        allowed = {"reddit", "facebook"}
        invalid = [s for s in parsed_sources if s not in allowed]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid sources: {invalid}. Allowed values: {sorted(allowed)}",
            )
        if not parsed_sources:
            raise HTTPException(status_code=422, detail="sources must include at least one value.")

    with _RUN_START_LOCK:
        db = SessionLocal()
        try:
            running = db.query(Run).filter(Run.status == "RUNNING").first()
            if running:
                raise HTTPException(
                    status_code=409,
                    detail=f"Run {running.run_id} is already RUNNING. Stop it first.",
                )
        finally:
            db.close()

        run_id = str(uuid.uuid4())
        effective_max_cost = max_cost_usd if max_cost_usd is not None else _default_max_cost_usd()
        with _RUN_META_LOCK:
            _RUN_MAX_COST_BY_ID[run_id] = float(effective_max_cost)

        thread = threading.Thread(
            target=_run_in_thread,
            kwargs=dict(
                run_id=run_id,
                mock_mode=mock,
                time_window_hours=time_window_hours,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                max_items=max_items,
                max_queries=max_queries,
                max_cost_usd=max_cost_usd,
                sources=parsed_sources,
            ),
            daemon=True,
            name=f"pipeline-run-{run_id[:8]}",
        )
        thread.start()

    return RunCreatedResponse(run_id=run_id, status="RUNNING")


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
