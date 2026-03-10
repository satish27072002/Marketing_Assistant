# Lead Labeling Rubric (Precision-First)

Use this rubric to assign `GOOD_MATCH` vs `BAD_MATCH` consistently.

## Label as `GOOD_MATCH` when all are true
- Explicit social intent exists (e.g., looking for people/group/events, wants company).
- Activity/event fit is plausible for the matched event.
- Context is local and timely enough for outreach (Stockholm/Uppsala focus and recent signal).
- Content is not spam/removed/low-information.

## Label as `BAD_MATCH` when any are true
- Vague or informational-only text with no intent to join/meet.
- Topic mismatch (housing, coffee, grammar, weather, unrelated utility posts).
- Stale or low-signal evidence that is unlikely to convert.
- Spam-like author/content patterns.

## Label reason taxonomy
- `vague_intent`
- `wrong_event_type_or_context`
- `stale_post`
- `spam_author`
- `other`

## Reviewer notes
- Keep `label_reason` short and specific.
- Prefer evidence from direct quotes in the source text.
