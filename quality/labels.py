"""Label backfill and candidate export helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from db.models import Lead, RawItem, UserEventAffinity


def backfill_labels_from_reviewed_leads(
    rows: list[dict[str, Any]],
    db: Session,
) -> list[dict[str, Any]]:
    """Populate label fields from existing lead reviewer feedback."""
    keys = {(str(r["username"]), str(r["event_id"])) for r in rows}
    if not keys:
        return rows

    lead_rows = (
        db.query(
            Lead.username,
            Lead.primary_event_id,
            Lead.reviewer_feedback,
            Lead.notes,
        )
        .filter(Lead.reviewer_feedback.in_(["GOOD_MATCH", "BAD_MATCH"]))
        .all()
    )
    lead_map = {
        (str(username), str(event_id)): (str(feedback), str(notes or ""))
        for username, event_id, feedback, notes in lead_rows
    }

    for row in rows:
        if row.get("label"):
            continue
        key = (str(row["username"]), str(row["event_id"]))
        existing = lead_map.get(key)
        if not existing:
            continue
        feedback, notes = existing
        row["label"] = feedback
        if not row.get("label_reason"):
            row["label_reason"] = notes
        if not row.get("reviewer"):
            row["reviewer"] = "backfill:reviewer_feedback"
    return rows


def export_candidate_rows(
    db: Session,
    event_lookup: dict[str, dict[str, Any]],
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Export candidate match rows from affinity evidence for annotation."""
    rows = (
        db.query(
            UserEventAffinity.evidence_item_id,
            UserEventAffinity.username,
            UserEventAffinity.event_id,
            UserEventAffinity.match_confidence,
            RawItem.subreddit,
            RawItem.text,
            RawItem.permalink,
            RawItem.created_utc,
        )
        .join(RawItem, RawItem.item_id == UserEventAffinity.evidence_item_id)
        .order_by(UserEventAffinity.id.desc())
        .limit(limit)
        .all()
    )

    out: list[dict[str, Any]] = []
    for item_id, username, event_id, confidence, subreddit, text, permalink, created_utc in rows:
        event_meta = event_lookup.get(str(event_id), {})
        out.append(
            {
                "item_id": str(item_id),
                "username": str(username),
                "subreddit": str(subreddit or ""),
                "text": str(text or ""),
                "event_id": str(event_id),
                "event_title": str(event_meta.get("event_title", event_id)),
                "current_confidence": float(confidence or 0.0),
                "source_link": str(permalink or ""),
                "timestamp": created_utc.isoformat() if created_utc else "",
                "label": "",
                "label_reason": "",
                "reviewer": "",
                "reviewed_at": "",
            }
        )
    return out

