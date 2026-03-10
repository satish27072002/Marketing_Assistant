"""Node B — UpsertEventIndexNode

For each event from Node A:
  - Builds a compact event card text (title + tags + description snippet)
  - Hashes the card and compares to the stored hash in index_meta.json
  - Re-embeds only if the event is new or its content changed
  - Rebuilds the index if any events were removed from disk (inactive cleanup)

Output: event_index_ready = True
"""
import logging

from embeddings.embedder import build_event_card, content_hash, embed_texts
from embeddings.faiss_store import FaissStore
from pipeline.state import Event, PipelineState

logger = logging.getLogger(__name__)


def upsert_event_index_node(state: PipelineState) -> PipelineState:
    events: list[Event] = state.get("events", [])

    store = FaissStore()
    store.load()

    # --- Detect events removed from disk and mark them inactive ---
    current_ids = {e.event_id for e in events}
    newly_inactive = store.known_ids() - current_ids
    for event_id in newly_inactive:
        store.mark_inactive(event_id)
        logger.info("Marked removed event inactive: %s", event_id)

    if not events:
        store.save()
        logger.info("UpsertEventIndexNode: no active events")
        return {**state, "event_index_ready": True}

    # --- Build card text and hashes for all active events ---
    cards: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for event in events:
        card = build_event_card(
            event.event_id, event.title, event.tags, event.description
        )
        cards[event.event_id] = card
        hashes[event.event_id] = content_hash(card)

    # --- If inactive events were found, rebuild the full index cleanly ---
    if newly_inactive:
        all_texts = [cards[e.event_id] for e in events]
        all_vectors = embed_texts(all_texts)
        store.rebuild_active_only(
            active_event_ids=[e.event_id for e in events],
            vectors={e.event_id: v for e, v in zip(events, all_vectors)},
            titles={e.event_id: e.title for e in events},
            hashes=hashes,
        )
        logger.info(
            "Rebuilt index: removed %d inactive events, kept %d active",
            len(newly_inactive), len(events),
        )
    else:
        # --- Reactivate events that are still on disk but were previously marked inactive ---
        reactivated = 0
        for event in events:
            if (
                store.get_content_hash(event.event_id) == hashes[event.event_id]
                and not store.is_active(event.event_id)
            ):
                store.mark_active(event.event_id)
                reactivated += 1
        if reactivated:
            logger.info("Reactivated %d existing events in index", reactivated)

        # --- Upsert only new or changed events ---
        to_embed = [
            e for e in events
            if store.get_content_hash(e.event_id) != hashes[e.event_id]
        ]
        if to_embed:
            texts = [cards[e.event_id] for e in to_embed]
            vectors = embed_texts(texts)
            for event, vector in zip(to_embed, vectors):
                store.upsert(
                    event_id=event.event_id,
                    title=event.title,
                    vector=vector,
                    card_hash=hashes[event.event_id],
                )
            logger.info("Embedded %d new/changed events", len(to_embed))
        else:
            logger.info("All events unchanged — no re-embedding needed")

    store.save()
    logger.info("UpsertEventIndexNode complete — %d active events in index", len(events))
    return {**state, "event_index_ready": True}
