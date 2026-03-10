"""Pydantic response schemas for the FastAPI backend."""
import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Run schemas
# ---------------------------------------------------------------------------

class RunResponse(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    time_window_start: datetime
    time_window_end: datetime
    items_collected: int = 0
    items_matched: int = 0
    leads_written: int = 0
    estimated_cost_usd: float = 0.0
    stop_requested: bool = False

    model_config = {"from_attributes": True}


class RunCreatedResponse(BaseModel):
    run_id: str
    status: str = "RUNNING"


# ---------------------------------------------------------------------------
# Lead schemas
# ---------------------------------------------------------------------------

class EvidencePost(BaseModel):
    """Full source item that triggered the lead match."""
    item_id: str
    source: str = "reddit"
    subreddit: str
    text: str
    url: str


class LeadResponse(BaseModel):
    id: int
    source: str = "reddit"
    username: str
    profile_url: Optional[str] = None
    primary_event_id: str
    other_event_ids: Optional[str] = None
    top_confidence: float
    user_summary: Optional[str] = None
    evidence_excerpts: list[str] = []
    evidence_urls: list[str] = []
    evidence_posts: list[EvidencePost] = []   # full post text from raw_items
    status: str
    reviewer_feedback: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("evidence_excerpts", mode="before")
    @classmethod
    def parse_excerpts(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []

    @field_validator("evidence_urls", mode="before")
    @classmethod
    def parse_urls(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []


class LeadPatch(BaseModel):
    status: Optional[str] = None
    reviewer_feedback: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Event schemas
# ---------------------------------------------------------------------------

class EventResponse(BaseModel):
    event_id: str
    title: str
    city: str
    tags: list[str]
    start_time: datetime
    end_time: datetime
    capacity: Optional[int] = None


# ---------------------------------------------------------------------------
# SSE update schema
# ---------------------------------------------------------------------------

class SSEUpdate(BaseModel):
    run_id: str
    status: str
    items_collected: int = 0
    items_matched: int = 0
    leads_found: int = 0
    estimated_cost_usd: float = 0.0
    budget_status: str = "OK"
    errors: int = 0
