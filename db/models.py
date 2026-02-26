from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint
)
from db.database import Base


class Run(Base):
    __tablename__ = "runs"

    run_id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="RUNNING")
    time_window_start = Column(DateTime, nullable=False)
    time_window_end = Column(DateTime, nullable=False)
    items_collected = Column(Integer, default=0)
    items_matched = Column(Integer, default=0)
    leads_written = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    stop_requested = Column(Boolean, default=False)
    error_log = Column(Text, nullable=True)


class RawItem(Base):
    __tablename__ = "raw_items"

    item_id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    subreddit = Column(String, nullable=False)
    author = Column(String, nullable=False)
    permalink = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_utc = Column(DateTime, nullable=False)
    query_used = Column(String, nullable=True)
    run_id = Column(String, nullable=False)
    processed = Column(Boolean, default=False)
    processing_status = Column(String, default="PENDING")


class UserEventAffinity(Base):
    __tablename__ = "user_event_affinity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, default="reddit")
    username = Column(String, nullable=False)
    profile_url = Column(String, nullable=True)
    event_id = Column(String, nullable=False)
    evidence_item_id = Column(String, nullable=False)
    evidence_excerpt = Column(String, nullable=True)
    match_confidence = Column(Float, nullable=False)
    match_reason = Column(String, nullable=True)
    prompt_version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "source", "username", "event_id", "evidence_item_id",
            name="uq_affinity_key"
        ),
    )


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, default="reddit")
    username = Column(String, nullable=False)
    profile_url = Column(String, nullable=True)
    primary_event_id = Column(String, nullable=False)
    other_event_ids = Column(String, nullable=True)
    top_confidence = Column(Float, nullable=False)
    user_summary = Column(Text, nullable=True)
    evidence_excerpts = Column(Text, nullable=True)
    evidence_urls = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="NEW")
    reviewer_feedback = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    prompt_version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "source", "username", "primary_event_id",
            name="uq_lead_key"
        ),
    )


class ProcessingQueue(Base):
    __tablename__ = "processing_queue"

    item_id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    batch_id = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    error_detail = Column(Text, nullable=True)
