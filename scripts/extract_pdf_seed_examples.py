"""Extract heuristic labeled lead examples from PDF documents.

Example:
    python3 scripts/extract_pdf_seed_examples.py \
      --input "/Users/satish/Downloads/Data.pdf" "/Users/satish/Downloads/Reddit Chats Raw.pdf" \
      --output-jsonl data/quality/pdf_seed_examples.jsonl \
      --output-csv data/quality/pdf_seed_examples.csv
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.dataset import write_csv, write_jsonl

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency pypdf. Install with: pip install pypdf") from exc


POSITIVE_PATTERNS = [
    r"\b(i am|i'm) interested\b",
    r"\bi'?d like to join\b",
    r"\bwould love to join\b",
    r"\blooking for (new )?friends?\b",
    r"\bnew to stockholm\b",
    r"\brecently moved\b",
    r"\bwant to meet (new )?people\b",
    r"\bhänger gärna på\b",
    r"\bjag är intresserad\b",
    r"\bskicka (mig )?dm\b",
]

FUTURE_ONLY_PATTERNS = [
    r"\bcan('|no)?t join\b",
    r"\bcannot make it\b",
    r"\bnot this week\b",
    r"\bnext week\b",
    r"\bnext time\b",
    r"\btentative\b",
    r"\bwould be interested in future dates\b",
    r"\bkan inte denna gång\b",
    r"\bnästa gång\b",
]

LOW_INTENT_PATTERNS = [
    r"\bnice initiative\b",
    r"\bsounds (fun|nice|interesting)\b",
    r"\bthanks\b",
    r"\bok\b",
]

HOST_OR_OUTREACH_PATTERNS = [
    r"\bi saw your post\b",
    r"\bi'll send you a dm\b",
    r"\bwe are hosting\b",
    r"\bhere'?s the event\b",
    r"\bwe'?re a group of friends\b",
]

EVENT_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("evt_coding_seed", "Coding Meetup", ("coding", "code", "cowork", "developer", "projects")),
    ("evt_climbing_seed", "Climbing/Bouldering", ("bouldering", "climbing", "klätter", "karbin")),
    ("evt_language_seed", "Language Cafe", ("language", "swedish practice", "språkcafé", "språkcaf")),
    ("evt_trivia_seed", "Quiz/Pub Crawl", ("quiz", "pub crawl", "pubquiz", "trivia")),
    ("evt_boardgames_seed", "Board Games", ("board game", "boardgame", "carrom")),
    ("evt_hiking_seed", "Hiking/Outdoors", ("hiking", "walk", "outdoors", "bbq", "grill")),
    ("evt_social_seed", "General Social", ("friends", "social", "meet people", "new in stockholm")),
]


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


POSITIVE_RE = _compile(POSITIVE_PATTERNS)
FUTURE_RE = _compile(FUTURE_ONLY_PATTERNS)
LOW_INTENT_RE = _compile(LOW_INTENT_PATTERNS)
HOST_RE = _compile(HOST_OR_OUTREACH_PATTERNS)
SIGNAL_RE = _compile(POSITIVE_PATTERNS + FUTURE_ONLY_PATTERNS + LOW_INTENT_PATTERNS)


def _contains_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _count_hits(text: str, patterns: list[re.Pattern[str]]) -> int:
    return sum(1 for p in patterns if p.search(text))


def _clean_page_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_page_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)>]+", text)


def _infer_event(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for event_id, title, keywords in EVENT_RULES:
        if any(keyword in lowered for keyword in keywords):
            return event_id, title
    return "evt_social_seed", "General Social"


def _infer_subreddit(text: str) -> str:
    lowered = text.lower()
    if "stockholmsocialclub" in lowered or "social club" in lowered:
        return "StockholmSocialClub"
    if "tillsverige" in lowered:
        return "TillSverige"
    if "uppsala" in lowered:
        return "Uppsala"
    return "stockholm"


def _infer_username(text: str, fallback_prefix: str, index: int) -> str:
    match = re.search(r"\b([A-Za-z0-9_\-\[\]]{3,30})\s*:", text)
    if match:
        candidate = match.group(1)
        if candidate.lower() not in {"results", "posted", "comments", "conversation", "link"}:
            return candidate
    return f"{fallback_prefix}_{index:04d}"


def _extract_snippets(clean_text: str) -> list[str]:
    snippets: list[str] = []
    for pattern in SIGNAL_RE:
        for match in pattern.finditer(clean_text):
            start = max(0, match.start() - 140)
            end = min(len(clean_text), match.end() + 220)
            left = max(clean_text.rfind(".", 0, start), clean_text.rfind("!", 0, start), clean_text.rfind("?", 0, start))
            right_candidates = [idx for idx in (clean_text.find(".", end), clean_text.find("!", end), clean_text.find("?", end)) if idx != -1]
            right = min(right_candidates) if right_candidates else len(clean_text)
            snippet = clean_text[(left + 1 if left >= 0 else start):right + 1].strip()
            if len(snippet) >= 35:
                snippets.append(snippet)

    # Dedupe while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        key = re.sub(r"\s+", " ", snippet.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(snippet)
    return deduped


def _label_snippet(text: str) -> tuple[str, str] | None:
    positive_hits = _count_hits(text, POSITIVE_RE)
    future_hits = _count_hits(text, FUTURE_RE)
    low_hits = _count_hits(text, LOW_INTENT_RE)
    host_hits = _count_hits(text, HOST_RE)

    if positive_hits == 0 and future_hits == 0 and low_hits == 0:
        return None

    if host_hits > 0 and positive_hits == 0:
        return "BAD_MATCH", "wrong_event_type_or_context"

    if positive_hits >= 1 and future_hits == 0 and low_hits == 0:
        return "GOOD_MATCH", "explicit_intent"

    if future_hits > 0:
        return "BAD_MATCH", "vague_intent"

    if low_hits > 0 and positive_hits == 0:
        return "BAD_MATCH", "vague_intent"

    if positive_hits >= 1 and low_hits >= 1:
        return "BAD_MATCH", "vague_intent"

    return None


def _stable_item_id(source_file: str, page_num: int, snippet: str) -> str:
    digest = hashlib.sha1(f"{source_file}|{page_num}|{snippet}".encode("utf-8")).hexdigest()[:12]
    return f"pdf_{digest}"


def extract_rows_from_pdf(pdf_path: str, max_rows: int) -> list[dict]:
    reader = PdfReader(pdf_path)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    rows: list[dict] = []

    for page_index, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        clean_text = _clean_page_text(raw_text)
        if not clean_text:
            continue
        page_urls = _extract_page_urls(raw_text)
        source_link = page_urls[0] if page_urls else f"pdf:{Path(pdf_path).name}#page={page_index}"
        snippets = _extract_snippets(clean_text)

        for snippet_index, snippet in enumerate(snippets, start=1):
            label_data = _label_snippet(snippet)
            if label_data is None:
                continue
            label, label_reason = label_data
            event_id, event_title = _infer_event(snippet)
            item_id = _stable_item_id(pdf_path, page_index, snippet)
            username = _infer_username(
                snippet,
                fallback_prefix=Path(pdf_path).stem.lower().replace(" ", "_"),
                index=snippet_index + page_index * 100,
            )

            confidence = 0.82 if label == "GOOD_MATCH" else 0.22
            if _contains_any(snippet, FUTURE_RE):
                confidence = min(confidence, 0.45)

            rows.append(
                {
                    "item_id": item_id,
                    "username": username,
                    "subreddit": _infer_subreddit(clean_text),
                    "text": snippet[:800],
                    "event_id": event_id,
                    "event_title": event_title,
                    "current_confidence": confidence,
                    "source_link": source_link,
                    "timestamp": now_iso,
                    "label": label,
                    "label_reason": label_reason,
                    "reviewer": "seed:pdf_heuristic_v1",
                    "reviewed_at": now_iso,
                }
            )
            if len(rows) >= max_rows:
                return rows
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract labeled seed examples from PDFs.")
    parser.add_argument("--input", nargs="+", required=True, help="Input PDF paths.")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL file path.")
    parser.add_argument("--output-csv", default="", help="Optional output CSV file path.")
    parser.add_argument("--max-rows", type=int, default=500, help="Maximum rows to export.")
    args = parser.parse_args()

    all_rows: list[dict] = []
    for path in args.input:
        all_rows.extend(extract_rows_from_pdf(path, max_rows=max(1, args.max_rows - len(all_rows))))
        if len(all_rows) >= args.max_rows:
            break

    # Dedupe by (item_id, event_id)
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in all_rows:
        key = (str(row["item_id"]), str(row["event_id"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    write_jsonl(deduped, args.output_jsonl)
    if args.output_csv:
        write_csv(deduped, args.output_csv)

    good = sum(1 for r in deduped if r.get("label") == "GOOD_MATCH")
    bad = sum(1 for r in deduped if r.get("label") == "BAD_MATCH")
    print(f"Wrote {len(deduped)} rows to {args.output_jsonl}")
    print(f"GOOD_MATCH={good} BAD_MATCH={bad}")


if __name__ == "__main__":
    main()
