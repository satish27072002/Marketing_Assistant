"""LLM client — Groq SDK wrapper with timeout, retry, and mock mode.

Mock mode (MOCK_MODE=true): returns hardcoded valid responses for every call type.
Live mode: calls Groq API with tenacity retry and Pydantic validation by the caller.

Cost estimation uses Groq's approximate token pricing for llama-3.3-70b-versatile.
"""
import json
import logging
import os
import re
from typing import Optional

import yaml
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

# Approximate cost per 1k tokens (Groq, llama-3.3-70b-versatile, Feb 2026)
COST_PER_1K_TOKENS = 0.00059


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

MOCK_SCRAPE_PLAN = {
    "queries": [
        {"query": "pub quiz stockholm friday", "subreddit": "stockholm", "priority": 3},
        {"query": "climbing group meet stockholm", "subreddit": "StockholmSocialClub", "priority": 3},
        {"query": "salsa bachata dance event", "subreddit": "StockholmSocialClub", "priority": 3},
        {"query": "social meetup new people stockholm", "subreddit": "TillSverige", "priority": 2},
        {"query": "python developer meetup", "subreddit": "stockholm", "priority": 2},
    ]
}

MOCK_BATCH_MATCH = {
    "results": [
        {
            "item_id": "__ITEM_0__",
            "matches": [
                {
                    "event_id": "__EVENT_0__",
                    "match_confidence": 0.88,
                    "match_reason": "User explicitly asks about pub quiz events in Stockholm",
                    "evidence_excerpt": "Looking for quiz or social events in Stockholm",
                }
            ],
        },
        {
            "item_id": "__ITEM_1__",
            "matches": [
                {
                    "event_id": "__EVENT_0__",
                    "match_confidence": 0.75,
                    "match_reason": "User expresses interest in social events",
                    "evidence_excerpt": "Want to meet new people at events",
                }
            ],
        },
        {"item_id": "__ITEM_2__", "matches": []},
        {"item_id": "__ITEM_3__", "matches": []},
        {"item_id": "__ITEM_4__", "matches": []},
    ]
}

MOCK_USER_SUMMARY = "Frequently looks for social events and pub quiz nights in Stockholm."


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LLMClient:

    def __init__(self, mock_mode: bool = False) -> None:
        self._mock_mode = mock_mode
        self._client = None
        self._config = _load_config()
        self.total_estimated_cost: float = 0.0
        self.total_calls: int = 0

    def _get_client(self):
        if self._client is None:
            try:
                from groq import Groq
            except ImportError:
                raise ImportError("groq package not installed. Run: pip install groq")
            api_key = os.environ.get("GROQ_API_KEY", "")
            if not api_key:
                raise ValueError("GROQ_API_KEY is not set in .env")
            self._client = Groq(api_key=api_key)
        return self._client

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        total_tokens = prompt_tokens + completion_tokens
        return (total_tokens / 1000) * COST_PER_1K_TOKENS

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call_api(self, prompt: str, model: str, temperature: float, max_tokens: int) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        usage = response.usage
        if usage:
            cost = self._estimate_cost(usage.prompt_tokens, usage.completion_tokens)
            self.total_estimated_cost += cost
            logger.debug(
                "Groq call: model=%s tokens=%d cost=$%.4f",
                model, usage.prompt_tokens + usage.completion_tokens, cost,
            )
        self.total_calls += 1
        return response.choices[0].message.content or ""

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a prompt and return the raw text response."""
        if self._mock_mode:
            logger.debug("[MOCK] LLM call skipped")
            return ""

        llm_config = self._config.get("llm", {})
        model = model or llm_config.get("primary_model", "llama-3.3-70b-versatile")
        temperature = temperature if temperature is not None else llm_config.get("temperature", 0.1)
        max_tokens = max_tokens or llm_config.get("max_tokens", 1024)

        return self._call_api(prompt, model, temperature, max_tokens)

    # ------------------------------------------------------------------
    # Typed helpers — return mock data or call live API
    # ------------------------------------------------------------------

    def plan_scrape(self, prompt: str) -> str:
        """Node C — returns raw text containing <plan>...</plan>."""
        if self._mock_mode:
            return f"<plan>\n{json.dumps(MOCK_SCRAPE_PLAN, indent=2)}\n</plan>"
        return self.complete(prompt)

    def match_batch(
        self,
        prompt: str,
        item_ids: list[str],
        event_ids: list[str],
        fast: bool = False,
    ) -> str:
        """Node G — returns raw text containing <matches>...</matches>.

        In mock mode, fills in real item_ids and event_ids so downstream
        Pydantic validation works correctly.
        """
        if self._mock_mode:
            mock = json.loads(json.dumps(MOCK_BATCH_MATCH))  # deep copy
            for i, result in enumerate(mock["results"]):
                result["item_id"] = item_ids[i] if i < len(item_ids) else result["item_id"]
                for match in result.get("matches", []):
                    match["event_id"] = event_ids[0] if event_ids else match["event_id"]
            return f"<matches>\n{json.dumps(mock, indent=2)}\n</matches>"

        llm_config = self._config.get("llm", {})
        model = (
            llm_config.get("fast_model", "llama-3.1-8b-instant")
            if fast
            else llm_config.get("primary_model", "llama-3.3-70b-versatile")
        )
        return self.complete(prompt, model=model)

    def summarise_user(self, prompt: str, username: str) -> str:
        """Node H — returns raw text of a 1-sentence summary."""
        if self._mock_mode:
            return MOCK_USER_SUMMARY

        llm_config = self._config.get("llm", {})
        fast_model = llm_config.get("fast_model", "llama-3.1-8b-instant")
        return self.complete(prompt, model=fast_model)


# ---------------------------------------------------------------------------
# Response parsing helpers
# ---------------------------------------------------------------------------

def extract_tagged_json(text: str, tag: str) -> Optional[dict]:
    """Extract JSON from <tag>...</tag> in LLM response."""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        logger.warning("Could not find <%s> tags in LLM response", tag)
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error in <%s> block: %s", tag, e)
        return None
