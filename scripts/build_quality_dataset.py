"""Build normalized lead-quality dataset from exported CSV/JSON/JSONL files.

Example:
    python3 scripts/build_quality_dataset.py \
      --input data/exports/data.csv data/exports/reddit_chats.json \
      --output-jsonl data/quality/training_rows.jsonl \
      --output-csv data/quality/training_rows.csv \
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
from quality.dataset import load_rows, normalize_rows, write_csv, write_jsonl
from quality.events import load_event_metadata
from quality.labels import backfill_labels_from_reviewed_leads


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized quality dataset.")
    parser.add_argument("--input", nargs="+", required=True, help="Input files (.csv/.json/.jsonl).")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL path.")
    parser.add_argument("--output-csv", default="", help="Optional output CSV path.")
    parser.add_argument("--backfill-from-db", action="store_true", help="Backfill GOOD/BAD labels from leads.reviewer_feedback.")
    args = parser.parse_args()

    event_lookup = load_event_metadata()

    raw_rows = []
    for path in args.input:
        raw_rows.extend(load_rows(path))

    normalized = normalize_rows(raw_rows, event_lookup=event_lookup)

    if args.backfill_from_db:
        db = SessionLocal()
        try:
            normalized = backfill_labels_from_reviewed_leads(normalized, db)
        finally:
            db.close()

    out_jsonl = Path(args.output_jsonl)
    write_jsonl(normalized, out_jsonl)
    if args.output_csv:
        write_csv(normalized, args.output_csv)

    labeled = sum(1 for r in normalized if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"})
    print(f"Wrote {len(normalized)} normalized rows to {out_jsonl}")
    print(f"Labeled rows: {labeled}")


if __name__ == "__main__":
    main()
