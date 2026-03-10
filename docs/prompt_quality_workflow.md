# Prompt Quality Workflow (PDF-Informed, Precision-First)

## 1) Extract seed dataset from PDFs
```bash
./.venv/bin/python scripts/extract_pdf_seed_examples.py \
  --input "/Users/satish/Downloads/Data.pdf" "/Users/satish/Downloads/Reddit Chats Raw.pdf" \
  --output-jsonl data/quality/pdf_seed_examples.jsonl \
  --output-csv data/quality/pdf_seed_examples.csv \
  --max-rows 500
```

## 2) (Optional) Build larger labeled dataset from DB + exports
```bash
./.venv/bin/python scripts/export_labeling_candidates.py \
  --output-jsonl data/quality/candidates.jsonl \
  --output-csv data/quality/candidates.csv \
  --limit 2000 \
  --backfill-from-db
```

## 3) Create baseline metrics snapshot
```bash
./.venv/bin/python scripts/evaluate_lead_quality.py \
  --dataset data/quality/pdf_seed_examples.jsonl \
  --summary-out data/quality/baseline_summary.json \
  --detail-out data/quality/baseline_detail.csv
```

## 4) Evaluate new prompt/rule iteration with regression guard
```bash
./.venv/bin/python scripts/evaluate_lead_quality.py \
  --dataset data/quality/pdf_seed_examples.jsonl \
  --summary-out data/quality/eval_summary.json \
  --detail-out data/quality/eval_detail.csv \
  --baseline data/quality/baseline_summary.json \
  --max-precision-drop 0.02
```

If precision drops more than the tolerance, the command exits non-zero.
