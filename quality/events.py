"""Helpers for loading event metadata used by quality tooling."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVENTS_DIR = PROJECT_ROOT / "data" / "events"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _load_tag_keywords(config_path: Path) -> dict[str, list[str]]:
    try:
        with config_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except OSError:
        return {}
    return cfg.get("tag_keywords", {}) or {}


def _derive_tags(description: str, tag_keywords: dict[str, list[str]]) -> list[str]:
    text = (description or "").lower()
    tags: list[str] = []
    for tag, keywords in tag_keywords.items():
        if any(str(kw).lower() in text for kw in keywords):
            tags.append(tag)
    return tags


def load_event_metadata(
    events_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load event metadata keyed by event_id."""
    event_dir = Path(events_dir) if events_dir else DEFAULT_EVENTS_DIR
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    tag_keywords = _load_tag_keywords(cfg_path)

    result: dict[str, dict[str, Any]] = {}
    if not event_dir.is_dir():
        return result

    for filename in os.listdir(event_dir):
        if not filename.endswith(".json") or filename.startswith("."):
            continue
        path = event_dir / filename
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        if isinstance(raw, dict) and isinstance(raw.get("event"), dict):
            raw = raw["event"]

        event_id = str(raw.get("id") or path.stem)
        title = str(raw.get("title") or event_id)
        tags = [str(t) for t in (raw.get("parentInterestIds") or [])]
        if not tags:
            tags = _derive_tags(str(raw.get("description") or ""), tag_keywords)

        result[event_id] = {
            "event_id": event_id,
            "event_title": title,
            "tags": tags,
        }

    return result

