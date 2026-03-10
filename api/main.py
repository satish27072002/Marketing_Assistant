"""FastAPI application entry point.

Start with:
    python3 -m uvicorn api.main:app --reload --port 8000

Endpoints:
    GET  /health
    GET  /runs            — list runs
    GET  /runs/live       — SSE live stream
    GET  /runs/{run_id}   — single run
    POST /runs            — trigger a new run
    POST /runs/{id}/stop  — graceful stop
    GET  /leads           — list leads
    PATCH /leads/{id}     — update lead review
    GET  /events          — list active events
"""
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root on path so all internal imports resolve
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from api.routes.runs import router as runs_router
from api.routes.leads import router as leads_router
from api.routes.events import router as events_router
from db.database import init_db

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Lead-Gen API",
    description="Multi-source lead generation pipeline (Reddit/Facebook) — REST + SSE backend",
    version="1.0.0",
)

# CORS — allow the React dashboard on both common dev ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Create React App
        "http://localhost:5173",   # Vite
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router, prefix="/runs", tags=["runs"])
app.include_router(leads_router, prefix="/leads", tags=["leads"])
app.include_router(events_router, prefix="/events", tags=["events"])


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", tags=["meta"])
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "lead-gen-api",
        "version": "1.0.0",
        "docs": "/docs",
    }
