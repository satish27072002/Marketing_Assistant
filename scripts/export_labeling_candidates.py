"""Export candidate match rows from DB for manual labeling.

Example:
    python3 scripts/export_labeling_candidates.py \
      --output-jsonl data/quality/candidates.jsonl \
      --output-csv data/quality/candidates.csv \
      --limit 2000 \
      --backfill-from-db
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from quality.dataset import write_csv, write_jsonl
from quality.events import load_event_metadata
from quality.labels import backfill_labels_from_reviewed_leads, export_candidate_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Export DB candidate rows for annotation.")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL file.")
    parser.add_argument("--output-csv", default="", help="Optional output CSV file.")
    parser.add_argument("--limit", type=int, default=1000, help="Max rows to export.")
    parser.add_argument("--backfill-from-db", action="store_true", help="Backfill labels from reviewed leads.")
    args = parser.parse_args()

    event_lookup = load_event_metadata()
    db = SessionLocal()
    try:
        rows = export_candidate_rows(db, event_lookup=event_lookup, limit=args.limit)
        if args.backfill_from_db:
            rows = backfill_labels_from_reviewed_leads(rows, db)
    finally:
        db.close()

    out_jsonl = Path(args.output_jsonl)
    write_jsonl(rows, out_jsonl)
    if args.output_csv:
        write_csv(rows, args.output_csv)

    labeled = sum(1 for r in rows if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"})
    print(f"Wrote {len(rows)} rows to {out_jsonl}")
    print(f"Labeled rows (after backfill): {labeled}")


if __name__ == "__main__":
    main()
