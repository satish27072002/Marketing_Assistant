"""Facebook collector.

Modes:
1) manual_json (default): reads rows from a local JSON file.
2) selenium (optional): browser-driven collector for explicitly approved/public pages.

This module intentionally avoids login/captcha bypass logic.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collectors.base import AbstractCollector

logger = logging.getLogger(__name__)

DEFAULT_MANUAL_INPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "import", "facebook_posts.json"
)
DEFAULT_MOCK_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "mock", "mock_facebook_posts.json"
)
BLOCK_PAGE_PATTERNS: list[tuple[str, str]] = [
    ("login_wall", "log in or sign up"),
    ("login_wall", "you must log in"),
    ("login_wall", "create new account"),
    ("checkpoint", "checkpoint"),
    ("checkpoint", "security check"),
    ("captcha", "captcha"),
    ("captcha", "recaptcha"),
    ("temporary_block", "temporarily blocked"),
    ("temporary_block", "unusual activity"),
    ("rate_limited", "rate limit"),
    ("rate_limited", "too many requests"),
]


def _query_terms(query: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) >= 3
    ]


def _parse_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return ts
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.isdigit():
            return _parse_ts(int(text))
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return 0.0


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def _detect_access_wall(page_text: str) -> tuple[bool, str]:
    lowered = (page_text or "").lower()
    for reason, pattern in BLOCK_PAGE_PATTERNS:
        if pattern in lowered:
            return True, reason
    return False, ""


def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    group = str(
        row.get("group")
        or row.get("subreddit")
        or row.get("community")
        or "facebook-group"
    ).strip()
    permalink = str(row.get("permalink") or row.get("url") or "").strip()
    text = str(row.get("text") or row.get("body") or row.get("content") or "").strip()
    author = str(row.get("author") or row.get("username") or "unknown").strip() or "unknown"
    item_type = str(row.get("type") or "post").strip() or "post"
    created_utc = _parse_ts(row.get("created_utc") or row.get("created_at") or row.get("timestamp"))
    if not created_utc:
        created_utc = datetime.now(tz=timezone.utc).timestamp()
    item_id = str(row.get("item_id") or "").strip()
    if not item_id:
        item_id = _stable_id("fb", permalink, author, text[:200], str(created_utc))
    if not permalink:
        permalink = f"https://www.facebook.com/groups/{group}"
    return {
        "item_id": item_id,
        "type": item_type,
        "subreddit": group,
        "author": author,
        "permalink": permalink,
        "text": text,
        "created_utc": created_utc,
    }


class FacebookCollector(AbstractCollector):
    def __init__(
        self,
        *,
        mode: str = "manual_json",
        mock_mode: bool = False,
        manual_input_path: str = DEFAULT_MANUAL_INPUT_PATH,
        selenium_headless: bool = True,
        selenium_max_scrolls: int = 3,
        selenium_scroll_pause_seconds: float = 1.5,
        selenium_group_urls: dict[str, str] | None = None,
    ) -> None:
        self._mode = mode
        self._mock_mode = mock_mode
        self._manual_input_path = manual_input_path
        self._selenium_headless = selenium_headless
        self._selenium_max_scrolls = selenium_max_scrolls
        self._selenium_scroll_pause_seconds = selenium_scroll_pause_seconds
        self._selenium_group_urls = selenium_group_urls or {}

    def _filter_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        query: str,
        group: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict[str, Any]]:
        terms = _query_terms(query)
        start_ts = time_window_start.timestamp()
        end_ts = time_window_end.timestamp()
        out: list[dict[str, Any]] = []

        for raw in rows:
            item = _normalise_row(raw)
            if group and item["subreddit"].lower() != group.lower():
                continue
            ts = float(item["created_utc"])
            if ts < start_ts or ts > end_ts:
                continue
            text_lower = item["text"].lower()
            if terms and not any(term in text_lower for term in terms):
                continue
            out.append(item)
        return out

    def _collect_from_json(
        self,
        *,
        path: str,
        query: str,
        group: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            logger.info("Facebook input file not found: %s", p)
            return []
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            logger.warning("Facebook input must be a JSON list: %s", p)
            return []
        rows = [r for r in payload if isinstance(r, dict)]
        return self._filter_rows(
            rows,
            query=query,
            group=group,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
        )

    def _collect_with_selenium(
        self,
        *,
        query: str,
        group: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict[str, Any]]:
        acknowledged = os.environ.get("FACEBOOK_SCRAPE_ACKNOWLEDGED", "false").lower() == "true"
        if not acknowledged:
            raise RuntimeError(
                "Selenium mode blocked: set FACEBOOK_SCRAPE_ACKNOWLEDGED=true after policy/legal approval."
            )
        url = self._selenium_group_urls.get(group, "").strip()
        if not url:
            logger.warning("No selenium URL configured for facebook group %s", group)
            return []

        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.common.exceptions import TimeoutException, WebDriverException
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("selenium package not installed. Install with: pip install selenium") from exc

        options = Options()
        if self._selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1365,1024")

        rows: list[dict[str, Any]] = []
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)
            driver.get(url)
            WebDriverWait(driver, 12).until(lambda d: d.execute_script("return document.readyState") == "complete")

            blocked, reason = _detect_access_wall(driver.page_source)
            if blocked:
                logger.warning(
                    "Facebook selenium blocked for group=%s reason=%s url=%s",
                    group,
                    reason,
                    url,
                )
                return []

            for _ in range(max(1, self._selenium_max_scrolls)):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(max(0.5, self._selenium_scroll_pause_seconds))

            articles = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
            if not articles:
                blocked, reason = _detect_access_wall(driver.page_source)
                if blocked:
                    logger.warning(
                        "Facebook selenium blocked after scroll for group=%s reason=%s url=%s",
                        group,
                        reason,
                        url,
                    )
                else:
                    logger.warning("Facebook selenium found no article elements for group=%s url=%s", group, url)
                return []

            now_ts = datetime.now(tz=timezone.utc).timestamp()
            for i, article in enumerate(articles):
                text = (article.text or "").strip()
                if len(text) < 40:
                    continue
                link = ""
                anchors = article.find_elements(By.CSS_SELECTOR, "a[href]")
                for a in anchors:
                    href = (a.get_attribute("href") or "").strip()
                    if "facebook.com" in href:
                        link = href
                        break
                rows.append(
                    {
                        "item_id": _stable_id("fb", group, str(i), text[:180]),
                        "type": "post",
                        "subreddit": group,
                        "author": "facebook-user",
                        "permalink": link or url,
                        "text": text,
                        "created_utc": now_ts,
                    }
                )
        except TimeoutException:
            logger.warning("Facebook selenium timeout for group=%s url=%s", group, url)
            return []
        except WebDriverException as exc:
            logger.warning("Facebook selenium webdriver error for group=%s url=%s: %s", group, url, exc)
            return []
        finally:
            if driver is not None:
                driver.quit()

        return self._filter_rows(
            rows,
            query=query,
            group=group,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
        )

    def collect(
        self,
        query: str,
        subreddit: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict]:
        if self._mock_mode:
            return self._collect_from_json(
                path=DEFAULT_MOCK_PATH,
                query=query,
                group=subreddit,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
            )

        mode = (self._mode or "manual_json").lower()
        if mode == "disabled":
            return []
        if mode == "manual_json":
            return self._collect_from_json(
                path=self._manual_input_path,
                query=query,
                group=subreddit,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
            )
        if mode == "selenium":
            return self._collect_with_selenium(
                query=query,
                group=subreddit,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
            )
        raise ValueError(f"Unsupported facebook collector mode: {self._mode}")
