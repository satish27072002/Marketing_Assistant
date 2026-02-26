"""Pydantic output schemas — strict validation of all LLM responses.

Every LLM call has a corresponding schema here. If the LLM returns invalid JSON
or violates a constraint, Pydantic raises a ValidationError which the caller
handles (retry or skip — never crash the run).
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Node C — PlanScrapeNode output
# ---------------------------------------------------------------------------

class ScrapeQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=100)
    subreddit: str = Field(..., min_length=1)
    priority: int = Field(..., ge=0, le=3)

    @field_validator("query")
    @classmethod
    def max_ten_words(cls, v: str) -> str:
        if len(v.split()) > 10:
            raise ValueError("query must be 10 words or fewer")
        return v.strip()


class ScrapePlan(BaseModel):
    queries: list[ScrapeQuery] = Field(..., min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# Node G — MatchItemsNode output
# ---------------------------------------------------------------------------

class EventMatch(BaseModel):
    event_id: str = Field(..., min_length=1)
    match_confidence: float = Field(..., ge=0.0, le=1.0)
    match_reason: str = Field(..., max_length=100)
    evidence_excerpt: str = Field(..., max_length=150)

    @field_validator("match_reason", "evidence_excerpt")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class ItemMatch(BaseModel):
    item_id: str = Field(..., min_length=1)
    matches: list[EventMatch] = Field(default_factory=list, max_length=3)


class BatchMatchResult(BaseModel):
    results: list[ItemMatch] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Node H — AggregateUserInterestsNode output
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
    username: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1, max_length=200)

    @field_validator("summary")
    @classmethod
    def single_sentence(cls, v: str) -> str:
        # Trim to first sentence if model returns multiple
        for sep in [".", "!", "?"]:
            idx = v.find(sep)
            if idx != -1:
                return v[: idx + 1].strip()
        return v.strip()
