"""Versioned prompt templates.

Every prompt has a version integer. The version is stored alongside every lead
and affinity row so quality can be tracked across prompt changes over time.
"""

# ---------------------------------------------------------------------------
# Node C — PlanScrapeNode
# ---------------------------------------------------------------------------

PLANNER_PROMPT_V = 1

PLANNER_PROMPT_TEMPLATE = """\
You are a search query planner for a Reddit lead generation tool.

Your job is to generate targeted Reddit search queries to find users who might be
interested in the upcoming events listed below.

UPCOMING EVENTS:
{event_list}

ALLOWED SUBREDDITS (you may only use these):
{subreddits}

TIME WINDOW: last {time_window_hours} hours
MAX QUERIES: {max_queries}

Generate search queries that would find Reddit users expressing interest in activities
matching these events. Focus on intent signals: users asking about similar activities,
looking for groups, or expressing interest in the topic.

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
"""


# ---------------------------------------------------------------------------
# Node G — MatchItemsNode
# ---------------------------------------------------------------------------

MATCHER_PROMPT_V = 1

MATCHER_PROMPT_TEMPLATE = """\
You are an event-matching assistant. Your job is to determine whether Reddit users
expressed genuine interest in specific upcoming events based on what they wrote.

CANDIDATE EVENTS:
{event_list}

REDDIT ITEMS TO ANALYSE:
{items_list}

For each Reddit item, decide which events (if any) the user seems genuinely interested
in based on their post or comment. Only match if there is clear evidence of interest.

Scoring guide:
- 0.9-1.0: Explicitly asks about or seeks this exact type of event
- 0.7-0.8: Strong indirect signal (mentions the activity, looking for it)
- 0.5-0.6: Moderate signal (related interest, possible fit)
- 0.3-0.4: Weak signal (tangential mention)
- Below 0.3: Do not include the match

Return up to 3 matches per item, only if confidence >= 0.3.
If an item has no relevant matches, return an empty matches list for it.

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
