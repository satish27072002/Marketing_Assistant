"""Dataset normalization utilities for lead-quality work."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CORE_FIELDS = [
    "item_id",
    "username",
    "subreddit",
    "text",
    "event_id",
    "event_title",
    "current_confidence",
    "source_link",
    "timestamp",
]
ANNOTATION_FIELDS = ["label", "label_reason", "reviewer", "reviewed_at"]
ALL_FIELDS = CORE_FIELDS + ANNOTATION_FIELDS
VALID_LABELS = {"GOOD_MATCH", "BAD_MATCH"}

ALIASES: dict[str, tuple[str, ...]] = {
    "item_id": ("item_id", "id", "post_id", "comment_id", "evidence_item_id"),
    "username": ("username", "author", "user", "reddit_user"),
    "subreddit": ("subreddit", "community"),
    "text": ("text", "body", "content", "message", "post_text"),
    "event_id": ("event_id", "primary_event_id"),
    "event_title": ("event_title", "event_name", "title"),
    "current_confidence": ("current_confidence", "match_confidence", "confidence", "top_confidence"),
    "source_link": ("source_link", "url", "permalink", "link"),
    "timestamp": ("timestamp", "created_utc", "created_at", "time", "date"),
    "label": ("label", "reviewer_feedback"),
    "label_reason": ("label_reason", "reason", "notes", "review_notes"),
    "reviewer": ("reviewer", "annotator"),
    "reviewed_at": ("reviewed_at", "annotated_at"),
}


def _coalesce(record: dict[str, Any], field: str) -> Any:
    for key in ALIASES.get(field, (field,)):
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _parse_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return _parse_timestamp(int(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_confidence(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _normalize_label(value: Any) -> str:
    if value in (None, ""):
        return ""
    label = str(value).strip().upper()
    if label in VALID_LABELS:
        return label
    return ""


def normalize_record(record: dict[str, Any], event_lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize an input row to canonical quality schema."""
    event_lookup = event_lookup or {}
    norm: dict[str, Any] = {}

    for field in CORE_FIELDS:
        norm[field] = _coalesce(record, field)
    for field in ANNOTATION_FIELDS:
        norm[field] = _coalesce(record, field)

    event_id = str(norm.get("event_id") or "").strip()
    if event_id and not norm.get("event_title"):
        norm["event_title"] = event_lookup.get(event_id, {}).get("event_title", event_id)

    norm["item_id"] = str(norm.get("item_id") or "").strip()
    norm["username"] = str(norm.get("username") or "").strip()
    norm["subreddit"] = str(norm.get("subreddit") or "").strip()
    norm["text"] = str(norm.get("text") or "").strip()
    norm["event_id"] = event_id
    norm["event_title"] = str(norm.get("event_title") or event_id).strip()
    norm["current_confidence"] = _parse_confidence(norm.get("current_confidence"))
    norm["source_link"] = str(norm.get("source_link") or "").strip()
    norm["timestamp"] = _parse_timestamp(norm.get("timestamp"))
    norm["label"] = _normalize_label(norm.get("label"))
    norm["label_reason"] = str(norm.get("label_reason") or "").strip()
    norm["reviewer"] = str(norm.get("reviewer") or "").strip()
    norm["reviewed_at"] = _parse_timestamp(norm.get("reviewed_at"))

    missing = [f for f in CORE_FIELDS if norm.get(f) in ("", None)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return norm


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"Unsupported JSON payload shape in {path}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return _load_csv(p)
    if suffix in {".json"}:
        return _load_json(p)
    if suffix in {".jsonl", ".ndjson"}:
        return _load_jsonl(p)
    raise ValueError(f"Unsupported input format: {p}")


def normalize_rows(
    rows: Iterable[dict[str, Any]],
    event_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for idx, row in enumerate(rows):
        try:
            norm = normalize_record(row, event_lookup=event_lookup)
        except Exception as exc:
            raise ValueError(f"Row {idx}: {exc}") from exc
        key = (norm["item_id"], norm["event_id"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(norm)
    return normalized


def write_jsonl(rows: Iterable[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_csv(rows: Iterable[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in ALL_FIELDS})

