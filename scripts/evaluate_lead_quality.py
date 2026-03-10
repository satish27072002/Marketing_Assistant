"""Evaluate lead quality on labeled dataset and tune confidence thresholds.

Example:
    python3 scripts/evaluate_lead_quality.py \
      --dataset data/quality/training_rows.jsonl \
      --summary-out data/quality/eval_summary.json \
      --detail-out data/quality/eval_detail.csv \
      --baseline data/quality/baseline_summary.json \
      --max-precision-drop 0.02
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.dataset import ALL_FIELDS, normalize_rows, load_rows
from quality.evaluation import evaluate_rows, recommend_thresholds_by_tag, sweep_thresholds
from quality.events import load_event_metadata


def _parse_thresholds(value: str) -> list[float]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return [float(p) for p in parts]


def _age_hours(timestamp_text: str) -> float:
    if not timestamp_text:
        return 0.0
    try:
        dt = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline lead quality evaluation harness.")
    parser.add_argument("--dataset", required=True, help="Input dataset (.csv/.json/.jsonl).")
    parser.add_argument("--summary-out", required=True, help="Summary JSON output.")
    parser.add_argument("--detail-out", required=True, help="Detail CSV output.")
    parser.add_argument("--thresholds", default="0.35,0.4,0.45,0.5,0.55,0.6", help="Comma-separated sweep thresholds.")
    parser.add_argument("--baseline", default="", help="Baseline summary JSON for regression guard.")
    parser.add_argument("--max-precision-drop", type=float, default=0.02, help="Allowed drop vs baseline.")
    args = parser.parse_args()

    event_lookup = load_event_metadata()
    rows = normalize_rows(load_rows(args.dataset), event_lookup=event_lookup)
    for row in rows:
        row["age_hours"] = _age_hours(str(row.get("timestamp", "")))

    thresholds = _parse_thresholds(args.thresholds)
    summary = evaluate_rows(rows, event_lookup=event_lookup)
    summary["threshold_sweep"] = sweep_thresholds(rows, thresholds)
    summary["recommended_tag_thresholds"] = recommend_thresholds_by_tag(rows, thresholds)

    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    detail_fields = ALL_FIELDS + ["event_tag", "query_type", "error_bucket", "age_hours"]
    detail_path = Path(args.detail_out)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=detail_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in detail_fields})

    print(f"Wrote summary: {summary_path}")
    print(f"Wrote details: {args.detail_out}")

    if args.baseline:
        with Path(args.baseline).open("r", encoding="utf-8") as f:
            baseline = json.load(f)
        base_precision = float(baseline.get("overall", {}).get("precision", 0.0))
        curr_precision = float(summary.get("overall", {}).get("precision", 0.0))
        if curr_precision + args.max_precision_drop < base_precision:
            raise SystemExit(
                f"Precision regression guard failed: baseline={base_precision:.4f} current={curr_precision:.4f}"
            )


if __name__ == "__main__":
    main()
