"""AbstractCollector — pluggable interface for content sources."""
from abc import ABC, abstractmethod
from datetime import datetime


class AbstractCollector(ABC):

    @abstractmethod
    def collect(
        self,
        query: str,
        subreddit: str,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> list[dict]:
        """Fetch posts/comments matching query within the time window.

        Returns a list of dicts with keys:
            item_id      str   — unique ID (e.g. reddit post/comment ID)
            type         str   — "post" or "comment"
            subreddit    str   — source community name (subreddit/group)
            author       str   — username ("[deleted]" if removed)
            permalink    str   — full URL to the item
            text         str   — post title + body, or comment body
            created_utc  float — Unix timestamp
        """
        ...
