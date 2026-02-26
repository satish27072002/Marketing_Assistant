"""Leads router — browse and review leads.

Routes:
    GET   /leads            — list leads with filters + pagination
    PATCH /leads/{lead_id}  — update status, reviewer_feedback, notes
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Lead, UserEventAffinity, RawItem
from api.schemas import LeadResponse, LeadPatch, EvidencePost

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"NEW", "REVIEWED", "MESSAGED", "SKIP"}
VALID_FEEDBACK = {"GOOD_MATCH", "BAD_MATCH"}


def _get_evidence_posts(db: Session, username: str, event_id: str) -> list[EvidencePost]:
    """Fetch the full Reddit post(s) that triggered this lead match."""
    affinities = (
        db.query(UserEventAffinity)
        .filter(
            UserEventAffinity.username == username,
            UserEventAffinity.event_id == event_id,
        )
        .all()
    )
    posts: list[EvidencePost] = []
    seen_item_ids: set[str] = set()
    for aff in affinities:
        if aff.evidence_item_id in seen_item_ids:
            continue
        seen_item_ids.add(aff.evidence_item_id)
        raw = db.query(RawItem).filter(RawItem.item_id == aff.evidence_item_id).first()
        if raw:
            posts.append(EvidencePost(
                item_id=raw.item_id,
                subreddit=raw.subreddit,
                text=raw.text,
                url=raw.permalink,
            ))
    return posts


def _lead_to_response(lead: Lead, db: Session) -> LeadResponse:
    evidence_posts = _get_evidence_posts(db, lead.username, lead.primary_event_id)
    data = LeadResponse.model_validate(lead)
    data.evidence_posts = evidence_posts
    return data


@router.get("", response_model=list[LeadResponse])
def list_leads(
    confidence_min: float = Query(0.0, ge=0.0, le=1.0, description="Minimum match confidence"),
    status: Optional[str] = Query(None, description="Filter by status: NEW, REVIEWED, MESSAGED, SKIP"),
    event_id: Optional[str] = Query(None, description="Filter by primary_event_id"),
    username: Optional[str] = Query(None, description="Search by username (partial match)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List leads with optional filters, sorted by confidence descending."""
    q = db.query(Lead)

    if confidence_min > 0.0:
        q = q.filter(Lead.top_confidence >= confidence_min)

    if status:
        q = q.filter(Lead.status == status.upper())

    if event_id:
        q = q.filter(Lead.primary_event_id == event_id)

    if username:
        q = q.filter(Lead.username.ilike(f"%{username}%"))

    leads = q.order_by(Lead.top_confidence.desc()).offset(skip).limit(limit).all()
    return [_lead_to_response(lead, db) for lead in leads]


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: int,
    patch: LeadPatch,
    db: Session = Depends(get_db),
):
    """Update a lead's review status, feedback, or notes."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    if patch.status is not None:
        if patch.status.upper() not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status {patch.status!r}. Must be one of: {sorted(VALID_STATUSES)}",
            )
        lead.status = patch.status.upper()

    if patch.reviewer_feedback is not None:
        if patch.reviewer_feedback.upper() not in VALID_FEEDBACK:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reviewer_feedback {patch.reviewer_feedback!r}. Must be one of: {sorted(VALID_FEEDBACK)}",
            )
        lead.reviewer_feedback = patch.reviewer_feedback.upper()

    if patch.notes is not None:
        lead.notes = patch.notes

    db.commit()
    db.refresh(lead)
    return _lead_to_response(lead, db)
