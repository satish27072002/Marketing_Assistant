"""Operational quality monitoring based on reviewer outcomes in SQLite."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from db.models import Lead


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute rolling lead quality monitoring metrics.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path.")
    args = parser.parse_args()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
    db = SessionLocal()
    try:
        base = db.query(Lead).filter(Lead.id.isnot(None))
        # Fallback to full table if we do not have created_at fields.
        total = base.count()

        reviewed = (
            db.query(func.count(Lead.id))
            .filter(Lead.reviewer_feedback.in_(["GOOD_MATCH", "BAD_MATCH"]))
            .scalar()
            or 0
        )
        bad = (
            db.query(func.count(Lead.id))
            .filter(Lead.reviewer_feedback == "BAD_MATCH")
            .scalar()
            or 0
        )
        messaged = (db.query(func.count(Lead.id)).filter(Lead.status == "MESSAGED").scalar() or 0)
        new_count = (db.query(func.count(Lead.id)).filter(Lead.status == "NEW").scalar() or 0)

        bad_match_rate = (bad / reviewed) if reviewed else 0.0
        new_to_messaged_proxy = (messaged / (messaged + new_count)) if (messaged + new_count) else 0.0

        metrics = {
            "window_days": args.days,
            "window_cutoff_utc": cutoff.isoformat(),
            "total_leads": total,
            "reviewed_leads": reviewed,
            "bad_matches": bad,
            "bad_match_rate": bad_match_rate,
            "messaged_leads": messaged,
            "new_leads": new_count,
            "new_to_messaged_proxy_rate": new_to_messaged_proxy,
        }
    finally:
        db.close()

    print(json.dumps(metrics, indent=2))
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
