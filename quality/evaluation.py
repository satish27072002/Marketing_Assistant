"""Offline quality metrics and threshold calibration helpers."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable


EXPLICIT_INTENT_PATTERNS = [
    re.compile(r"\blooking for\b", re.IGNORECASE),
    re.compile(r"\bwant to meet\b", re.IGNORECASE),
    re.compile(r"\bwould love to join\b", re.IGNORECASE),
    re.compile(r"\bnew to stockholm\b", re.IGNORECASE),
]
VAGUE_INTENT_PATTERNS = [
    re.compile(r"\bmaybe\b", re.IGNORECASE),
    re.compile(r"\bopen to ideas\b", re.IGNORECASE),
    re.compile(r"\bany suggestions\b", re.IGNORECASE),
]
SPAM_USER_PATTERNS = [
    re.compile(r"spam", re.IGNORECASE),
    re.compile(r"bot", re.IGNORECASE),
]


def _has_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def classify_query_type(text: str) -> str:
    if _has_any(text, EXPLICIT_INTENT_PATTERNS):
        return "explicit_intent"
    if "?" in text:
        return "question"
    return "general"


def classify_error_bucket(row: dict[str, Any], stale_hours: int = 168) -> str:
    text = str(row.get("text", ""))
    username = str(row.get("username", ""))
    confidence = float(row.get("current_confidence", 0.0))
    age_hours = float(row.get("age_hours", 0.0))

    if _has_any(username, SPAM_USER_PATTERNS):
        return "spam_author"
    if age_hours > stale_hours:
        return "stale_post"
    if _has_any(text, VAGUE_INTENT_PATTERNS):
        return "vague_intent"
    if confidence < 0.5:
        return "low_confidence"
    return "wrong_event_type_or_context"


def _confusion(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: {"GOOD_MATCH": 0, "BAD_MATCH": 0})
    for row in rows:
        label = row.get("label")
        if label not in {"GOOD_MATCH", "BAD_MATCH"}:
            continue
        group = str(row.get(key) or "unknown")
        matrix[group][label] += 1
    return dict(matrix)


def _precision(rows: list[dict[str, Any]]) -> float:
    labeled = [r for r in rows if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"}]
    if not labeled:
        return 0.0
    good = sum(1 for r in labeled if r["label"] == "GOOD_MATCH")
    return good / len(labeled)


def _false_positive_rate(rows: list[dict[str, Any]]) -> float:
    labeled = [r for r in rows if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"}]
    if not labeled:
        return 0.0
    bad = sum(1 for r in labeled if r["label"] == "BAD_MATCH")
    return bad / len(labeled)


def precision_at_k(rows: list[dict[str, Any]], k: int) -> float:
    ranked = sorted(rows, key=lambda r: float(r.get("current_confidence", 0.0)), reverse=True)
    top = [r for r in ranked[:k] if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"}]
    if not top:
        return 0.0
    good = sum(1 for r in top if r["label"] == "GOOD_MATCH")
    return good / len(top)


def evaluate_rows(
    rows: list[dict[str, Any]],
    event_lookup: dict[str, dict[str, Any]] | None = None,
    ks: list[int] | None = None,
) -> dict[str, Any]:
    event_lookup = event_lookup or {}
    ks = ks or [10, 25, 50]

    for row in rows:
        event_meta = event_lookup.get(str(row.get("event_id", "")), {})
        tags = event_meta.get("tags", [])
        row["event_tag"] = ",".join(tags) if tags else "unknown"
        row["query_type"] = classify_query_type(str(row.get("text", "")))
        if row.get("label") == "BAD_MATCH":
            row["error_bucket"] = classify_error_bucket(row)
        else:
            row["error_bucket"] = ""

    labeled = [r for r in rows if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"}]
    bad_rows = [r for r in labeled if r["label"] == "BAD_MATCH"]

    per_k = {f"p_at_{k}": precision_at_k(rows, k) for k in ks}
    error_buckets: dict[str, int] = defaultdict(int)
    for row in bad_rows:
        error_buckets[row["error_bucket"]] += 1

    return {
        "overall": {
            "rows_total": len(rows),
            "rows_labeled": len(labeled),
            "precision": _precision(rows),
            "false_positive_rate": _false_positive_rate(rows),
            **per_k,
        },
        "confusion": {
            "by_event_tag": _confusion(rows, "event_tag"),
            "by_subreddit": _confusion(rows, "subreddit"),
            "by_query_type": _confusion(rows, "query_type"),
        },
        "error_buckets": dict(error_buckets),
    }


def sweep_thresholds(
    rows: list[dict[str, Any]],
    thresholds: list[float],
) -> list[dict[str, Any]]:
    labeled = [r for r in rows if r.get("label") in {"GOOD_MATCH", "BAD_MATCH"}]
    positives_total = sum(1 for r in labeled if r["label"] == "GOOD_MATCH")

    results: list[dict[str, Any]] = []
    for threshold in thresholds:
        kept = [r for r in labeled if float(r.get("current_confidence", 0.0)) >= threshold]
        if not kept:
            results.append(
                {
                    "threshold": threshold,
                    "rows_kept": 0,
                    "precision": 0.0,
                    "false_positive_rate": 0.0,
                    "recall_proxy": 0.0,
                }
            )
            continue

        good = sum(1 for r in kept if r["label"] == "GOOD_MATCH")
        bad = len(kept) - good
        precision = good / len(kept)
        recall_proxy = (good / positives_total) if positives_total else 0.0
        results.append(
            {
                "threshold": threshold,
                "rows_kept": len(kept),
                "precision": precision,
                "false_positive_rate": bad / len(kept),
                "recall_proxy": recall_proxy,
            }
        )
    return results


def recommend_thresholds_by_tag(
    rows: list[dict[str, Any]],
    thresholds: list[float],
) -> dict[str, float]:
    """Pick threshold per event_tag maximizing precision then recall-proxy."""
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("label") not in {"GOOD_MATCH", "BAD_MATCH"}:
            continue
        tags = str(row.get("event_tag") or "unknown").split(",")
        for tag in tags:
            by_tag[tag.strip() or "unknown"].append(row)

    recommendations: dict[str, float] = {}
    for tag, tag_rows in by_tag.items():
        sweeps = sweep_thresholds(tag_rows, thresholds)
        sweeps = [s for s in sweeps if s["rows_kept"] > 0]
        if not sweeps:
            continue
        sweeps.sort(key=lambda s: (s["precision"], s["recall_proxy"]), reverse=True)
        recommendations[tag] = float(sweeps[0]["threshold"])
    return recommendations

