"""RedditCollector — public JSON API implementation of AbstractCollector.

Uses the free, unauthenticated Reddit JSON API — no OAuth credentials needed.
Paginates using the `after` cursor, sleeps 2 s between pages to stay polite.
In mock mode, reads from data/mock/mock_reddit_posts.json instead.
"""
import json
import logging
import os
import time
from datetime import datetime

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from collectors.base import AbstractCollector

logger = logging.getLogger(__name__)

MOCK_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "mock", "mock_reddit_posts.json"
)

# Authors to always skip
SKIP_AUTHORS = {"[deleted]", "AutoModerator"}

# selftext values that mean the body is absent
EMPTY_SELFTEXT = {"", "[removed]", "[deleted]"}

# Maximum pages to fetch per subreddit (25 posts/page → 100 posts max)
MAX_PAGES = 4
PAGE_SIZE = 25
PAGE_SLEEP_SECONDS = 2


def _build_text(post: dict) -> str:
    """Return title + body text. Falls back to crosspost body if selftext is absent."""
    title = post.get("title", "").strip()
    selftext = post.get("selftext", "").strip()

    if selftext in EMPTY_SELFTEXT:
        # Try crosspost body
        crosspost_list = post.get("crosspost_parent_list") or []
        if crosspost_list:
            selftext = crosspost_list[0].get("selftext", "").strip()
        if selftext in EMPTY_SELFTEXT:
            selftext = ""

    return f"{title}\n{selftext}".strip() if selftext else title


def _should_skip(post: dict) -> bool:
    """Return True if this post should be excluded entirely."""
    if post.get("removed_by_category"):
        return True
    author = post.get("author", "")
    if author in SKIP_AUTHORS:
        return True
    return False


class RedditCollector(AbstractCollector):

    def __init__(self, mock_mode: bool = False) -> None:
        self._mock_mode = mock_mode
        self._user_agent = os.environ.get("REDDIT_USER_AGENT", "leadgen-bot/1.0")

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _collect_mock(
        self,
        query: str,
        subreddit: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict]:
        if not os.path.exists(MOCK_DATA_PATH):
            logger.warning("Mock data file not found: %s", MOCK_DATA_PATH)
            return []

        with open(MOCK_DATA_PATH, "r") as f:
            all_posts: list[dict] = json.load(f)

        start_ts = time_window_start.timestamp()
        end_ts = time_window_end.timestamp()

        results = []
        for post in all_posts:
            if post.get("subreddit", "").lower() != subreddit.lower():
                continue
            created = post.get("created_utc", 0)
            if not (start_ts <= created <= end_ts):
                continue
            results.append(post)

        logger.debug(
            "[MOCK] query=%r subreddit=%s matched %d items", query, subreddit, len(results)
        )
        return results

    # ------------------------------------------------------------------
    # Live mode — public JSON API
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _fetch_page(self, subreddit: str, query: str, after: str | None) -> dict:
        """Search a subreddit for posts matching query using the public Reddit JSON API."""
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params: dict = {
            "q": query,
            "sort": "new",
            "restrict_sr": 1,   # only search within this subreddit
            "limit": PAGE_SIZE,
            "raw_json": 1,
        }
        if after:
            params["after"] = after

        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": self._user_agent},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def _collect_live(
        self,
        query: str,
        subreddit: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict]:
        start_ts = time_window_start.timestamp()
        end_ts = time_window_end.timestamp()

        results: list[dict] = []
        after: str | None = None
        pages_fetched = 0

        while pages_fetched < MAX_PAGES:
            try:
                data = self._fetch_page(subreddit, query, after)
            except Exception as e:
                logger.error(
                    "Failed to fetch page %d for r/%s: %s", pages_fetched + 1, subreddit, e
                )
                break

            listing = data.get("data", {})
            children = listing.get("children", [])
            if not children:
                break

            for child in children:
                post = child.get("data", {})
                created = float(post.get("created_utc", 0))

                # Skip posts outside the time window
                if created < start_ts or created > end_ts:
                    continue

                if _should_skip(post):
                    logger.debug(
                        "Skipping post %s (author=%s removed_by_category=%s)",
                        post.get("id"), post.get("author"),
                        post.get("removed_by_category"),
                    )
                    continue

                author = post.get("author", "[deleted]")
                text = _build_text(post)
                item_id = f"t3_{post['id']}"
                permalink = f"https://www.reddit.com{post.get('permalink', '')}"

                results.append({
                    "item_id": item_id,
                    "type": "post",
                    "subreddit": subreddit,
                    "author": author,
                    "permalink": permalink,
                    "text": text,
                    "created_utc": created,
                })

            pages_fetched += 1
            after = listing.get("after")

            if not after:
                break

            logger.debug(
                "r/%s page %d done (%d items so far) — sleeping %ds before next page",
                subreddit, pages_fetched, len(results), PAGE_SLEEP_SECONDS,
            )
            time.sleep(PAGE_SLEEP_SECONDS)

        logger.debug(
            "query=%r subreddit=%s fetched %d items across %d page(s)",
            query, subreddit, len(results), pages_fetched,
        )
        return results

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(
        self,
        query: str,
        subreddit: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict]:
        if self._mock_mode:
            return self._collect_mock(query, subreddit, time_window_start, time_window_end)
        return self._collect_live(query, subreddit, time_window_start, time_window_end)
