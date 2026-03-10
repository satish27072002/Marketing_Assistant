"""Versioned prompt templates.

Every prompt has a version integer. The version is stored alongside every lead
and affinity row so quality can be tracked across prompt changes over time.
"""

from llm.prompt_examples import format_matcher_few_shots, format_planner_examples

# ---------------------------------------------------------------------------
# Node C — PlanScrapeNode
# ---------------------------------------------------------------------------

PLANNER_PROMPT_V = 2

PLANNER_PROMPT_TEMPLATE = """\
You are a precision-first Reddit query planner for Stockholm social events.
Goal: generate queries that find people with real intent to join.

UPCOMING EVENTS:
{event_list}

ALLOWED SUBREDDITS (you may only use these):
{subreddits}

TIME WINDOW: last {time_window_hours} hours
MAX QUERIES: {max_queries}

Intent rubric for query generation:
- Prioritize explicit join intent and newcomer intent:
  "looking for friends", "would love to join", "new to stockholm", "gärna haka på".
- Cover English + Swedish phrasing where natural.
- Focus on social and activity fit to listed events.
- De-prioritize generic informational or city utility queries.

Good query shapes (adapt to each event):
{planner_query_examples}

Avoid query shapes like:
- "best coffee stockholm"
- "housing queue stockholm"
- "weather stockholm"
- generic activity facts without social intent

Return your response as JSON inside <plan> tags exactly like this:
<plan>
{{
  "queries": [
    {{"query": "pub quiz stockholm", "subreddit": "stockholm", "priority": 3}},
    {{"query": "climbing group meet", "subreddit": "StockholmSocialClub", "priority": 2}}
  ]
}}
</plan>

Rules:
- Each query must be 10 words or fewer
- Only use subreddits from the allowed list
- Priority: 3=highest relevance, 0=lowest
- Maximum {max_queries} queries total
- No duplicate queries
- Keep at least 70% of queries focused on explicit social/join intent
"""


# ---------------------------------------------------------------------------
# Node G — MatchItemsNode
# ---------------------------------------------------------------------------

MATCHER_PROMPT_V = 2

MATCHER_PROMPT_TEMPLATE = """\
You are a precision-first event matcher.
Task: decide if each Reddit item shows genuine intent to join one or more candidate events.
If evidence is weak or ambiguous, prefer returning no match.

CANDIDATE EVENTS:
{event_list}

REDDIT ITEMS TO ANALYSE:
{items_list}

Decision rubric:
- READY_NOW (0.70-1.00):
  clear intent to join soon, asks to join, asks details, or seeks activity partners.
- FUTURE_INTEREST (0.45-0.69):
  interest exists but timing uncertain ("next week", "can't this time", "tentative").
  Only match recurring/likely-repeat events.
- EXCLUDE (<0.45):
  vague praise, generic questions, off-topic utility posts, memes/news/politics, or no join intent.

Language coverage:
- Handle English and Swedish intent signals (for example:
  "jag är intresserad", "hänger gärna på", "gärna", "kan inte denna gång").

Few-shot calibration:
{matcher_few_shots}

Matching requirements:
- Only match when text evidence links person + activity + social intent.
- Prefer precision over recall. When unsure, return empty matches.
- Up to 3 matches per item.
- Include all relevant events only if evidence supports each one.

Return your response as JSON inside <matches> tags exactly like this:
<matches>
{{
  "results": [
    {{
      "item_id": "t3_abc123",
      "matches": [
        {{
          "event_id": "evt_001",
          "match_confidence": 0.85,
          "match_reason": "User explicitly asks about pub quiz events in Stockholm",
          "evidence_excerpt": "Anyone know good pub quiz spots in Stockholm this Friday?"
        }}
      ]
    }},
    {{
      "item_id": "t3_xyz789",
      "matches": []
    }}
  ]
}}
</matches>

Critical rules:
- Include every item_id from the input in your results, even if matches is empty
- match_reason must be 100 characters or fewer
- evidence_excerpt must be 150 characters or fewer and be a direct quote from the text
- match_confidence must be between 0.0 and 1.0
- Maximum 3 matches per item
"""

MATCHER_PROMPT_STRICT_TEMPLATE = """\
You are an event-matching assistant. Return ONLY valid JSON inside <matches> tags.
Do not include any explanation or text outside the tags.

CANDIDATE EVENTS:
{event_list}

REDDIT ITEMS:
{items_list}

Return this exact structure:
<matches>
{{
  "results": [
    {{
      "item_id": "<item_id>",
      "matches": [
        {{
          "event_id": "<event_id>",
          "match_confidence": <float 0.0-1.0>,
          "match_reason": "<max 100 chars>",
          "evidence_excerpt": "<max 150 chars direct quote>"
        }}
      ]
    }}
  ]
}}
</matches>

Include every item_id. Use empty matches list if no match found.
"""


# ---------------------------------------------------------------------------
# Node H — AggregateUserInterestsNode
# ---------------------------------------------------------------------------

SUMMARY_PROMPT_V = 1

SUMMARY_PROMPT_TEMPLATE = """\
Write a single sentence describing this Reddit user's interests based on their posts.
Focus on what kinds of events or activities they are looking for.

USERNAME: {username}

THEIR POSTS/COMMENTS:
{evidence_list}

Write exactly one sentence, starting with "Frequently" or "Interested in" or "Looking for".
Maximum 200 characters. No quotes around the sentence.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_event_list(events: list[dict]) -> str:
    """Compact event representation for prompts (~50 tokens per event)."""
    lines = []
    for e in events:
        tags = ", ".join(e.get("tags", [])) or "general"
        lines.append(f"- ID: {e['event_id']} | {e['title']} | Tags: {tags}")
    return "\n".join(lines)


def format_items_list(items: list[dict]) -> str:
    """Format raw items for the matcher prompt."""
    lines = []
    for item in items:
        lines.append(
            f"item_id: {item['item_id']}\n"
            f"subreddit: r/{item['subreddit']}\n"
            f"text: {item['text'][:400]}\n"
            f"---"
        )
    return "\n".join(lines)


def format_evidence_list(excerpts: list[str]) -> str:
    return "\n".join(f"- {e}" for e in excerpts)


def planner_query_examples() -> str:
    return format_planner_examples()


def matcher_few_shots() -> str:
    return format_matcher_few_shots()
