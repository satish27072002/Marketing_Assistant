"""Reusable few-shot examples and phrase banks for lead-quality prompting."""

from __future__ import annotations


PLANNER_QUERY_EXAMPLES: list[str] = [
    "new to stockholm looking for friends",
    "recently moved stockholm want social group",
    "stockholm bouldering buddy beginner",
    "pub quiz stockholm need team",
    "language cafe stockholm swedish practice",
    "after work coding stockholm join",
    "board games stockholm join group",
    "stockholm social meetup expats",
]


MATCHER_FEW_SHOTS: list[dict[str, str]] = [
    {
        "label": "READY_NOW_HIGH",
        "text": "Hey! I recently moved to Stockholm and want to meet new people. "
        "Would love to join a board game or language cafe this week.",
        "reason": "Direct social intent, city fit, and immediate join intent.",
        "score_hint": "0.82",
    },
    {
        "label": "READY_NOW_ACTIVITY",
        "text": "Jag är ny i Stockholm och vill gärna haka på klättring i helgen. "
        "Jag bouldrar men har ingen grupp ännu.",
        "reason": "Explicit Swedish intent with activity fit and clear ask.",
        "score_hint": "0.86",
    },
    {
        "label": "FUTURE_INTEREST_MEDIUM",
        "text": "This sounds interesting but I cannot join tonight. "
        "Maybe next week if you do it again.",
        "reason": "Intent exists, but not immediate; recurring events only.",
        "score_hint": "0.52",
    },
    {
        "label": "BAD_VAGUE_LOW",
        "text": "Nice initiative.",
        "reason": "Polite feedback without evidence of intent to join.",
        "score_hint": "0.10",
    },
    {
        "label": "BAD_OFFTOPIC",
        "text": "Anyone know the best coffee near Odenplan?",
        "reason": "No social-event intent and no activity match.",
        "score_hint": "0.05",
    },
]


def format_planner_examples() -> str:
    return "\n".join(f"  - \"{q}\"" for q in PLANNER_QUERY_EXAMPLES)


def format_matcher_few_shots() -> str:
    lines: list[str] = []
    for example in MATCHER_FEW_SHOTS:
        lines.append(
            f"- {example['label']} ({example['score_hint']}):\n"
            f"  Text: {example['text']}\n"
            f"  Why: {example['reason']}"
        )
    return "\n".join(lines)
