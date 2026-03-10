"""RedditCollector — public JSON API implementation of AbstractCollector.

Uses the free, unauthenticated Reddit JSON API — no OAuth credentials needed.
Paginates using the `after` cursor, sleeps 2 s between pages to stay polite.
In mock mode, reads from data/mock/mock_reddit_posts.json instead.
"""
import json
import logging
import os
import re
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

# Comment body values that mean the body is absent
EMPTY_BODY = {"[removed]", "[deleted]"}

# Maximum pages to fetch per subreddit (25 posts/page → 100 posts max)
MAX_PAGES = 4
PAGE_SIZE = 25
PAGE_SLEEP_SECONDS = 2


def _query_terms(query: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) >= 3
    ]


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

    def __init__(self, mock_mode: bool = False, collect_comments: bool = True) -> None:
        self._mock_mode = mock_mode
        self._collect_comments = collect_comments
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
        terms = _query_terms(query)

        results = []
        for post in all_posts:
            if post.get("subreddit", "").lower() != subreddit.lower():
                continue
            created = post.get("created_utc", 0)
            if not (start_ts <= created <= end_ts):
                continue
            text = str(post.get("text", "")).lower()
            if terms and not any(term in text for term in terms):
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _fetch_comments(self, subreddit: str, post_id: str) -> list:
        """Fetch the comment listing for a post.

        Returns a two-element list: [post_listing, comment_listing].
        """
        url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
        response = requests.get(
            url,
            params={"raw_json": 1, "limit": 100},
            headers={"User-Agent": self._user_agent},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def _extract_comments(
        self,
        comment_listing: dict,
        subreddit: str,
        parent_post_title: str,
        start_ts: float,
        end_ts: float,
    ) -> list[dict]:
        """Extract qualifying top-level comments from a comment listing."""
        results = []
        for child in comment_listing.get("data", {}).get("children", []):
            # Only process actual comments (t1), skip "more" objects
            if child.get("kind") != "t1":
                continue

            c = child.get("data", {})

            author = c.get("author", "")
            if author in SKIP_AUTHORS:
                continue

            body = c.get("body", "").strip()
            if body in EMPTY_BODY or len(body) < 30:
                continue

            created = float(c.get("created_utc", 0))
            if not (start_ts <= created <= end_ts):
                continue

            comment_id = c.get("id", "")
            permalink = f"https://www.reddit.com{c.get('permalink', '')}"
            # Include parent post title as context so the matcher understands the thread
            text = f"{parent_post_title}\n\nComment: {body}"

            results.append({
                "item_id": f"t1_{comment_id}",
                "type": "comment",
                "subreddit": subreddit,
                "author": author,
                "permalink": permalink,
                "text": text,
                "created_utc": created,
                "score": c.get("score", 0),
                "parent_post_title": parent_post_title,
            })

        return results

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
        # Track qualifying posts so we can fetch their comments afterwards
        posts_for_comments: list[tuple[str, str]] = []  # (post_id, title)
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
                post_id = post.get("id", "")
                item_id = f"t3_{post_id}"
                permalink = f"https://www.reddit.com{post.get('permalink', '')}"
                title = post.get("title", "")

                results.append({
                    "item_id": item_id,
                    "type": "post",
                    "subreddit": subreddit,
                    "author": author,
                    "permalink": permalink,
                    "text": text,
                    "created_utc": created,
                })

                if self._collect_comments and post_id:
                    posts_for_comments.append((post_id, title))

            pages_fetched += 1
            after = listing.get("after")

            if not after:
                break

            logger.debug(
                "r/%s page %d done (%d items so far) — sleeping %ds before next page",
                subreddit, pages_fetched, len(results), PAGE_SLEEP_SECONDS,
            )
            time.sleep(PAGE_SLEEP_SECONDS)

        # Fetch top-level comments for each qualifying post
        if self._collect_comments:
            for post_id, title in posts_for_comments:
                try:
                    listing = self._fetch_comments(subreddit, post_id)
                    if len(listing) >= 2:
                        comments = self._extract_comments(
                            listing[1], subreddit, title, start_ts, end_ts
                        )
                        results.extend(comments)
                        if comments:
                            logger.debug(
                                "Fetched %d comments for post %s", len(comments), post_id
                            )
                except Exception as e:
                    logger.warning(
                        "Failed to fetch comments for post %s: %s", post_id, e
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
