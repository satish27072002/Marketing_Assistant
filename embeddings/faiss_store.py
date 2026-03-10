"""FAISS store — persists event embeddings to disk.

Layout on disk:
    data/faiss_index/index.faiss       — the raw FAISS index
    data/faiss_index/index_meta.json   — maps event_id → {faiss_idx, content_hash,
                                          title, active}

Design decisions:
- Uses IndexFlatIP (inner product on L2-normalised vectors == cosine similarity).
- FAISS does not support in-place deletion; inactive events are filtered out of
  search results and the index is rebuilt when inactive entries are present.
- The store is intentionally small-data: personal tool with tens of events, not millions.
"""
import hashlib
import json
import logging
import os
from typing import Optional

import faiss
import numpy as np

logger = logging.getLogger(__name__)

INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "faiss_index")
INDEX_FILE = os.path.join(INDEX_DIR, "index.faiss")
META_FILE = os.path.join(INDEX_DIR, "index_meta.json")

EMBEDDING_DIM = 384


def _ensure_dir() -> None:
    os.makedirs(INDEX_DIR, exist_ok=True)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class FaissStore:
    def __init__(self) -> None:
        self._index: Optional[faiss.IndexFlatIP] = None
        # meta: {event_id: {faiss_idx, content_hash, title, active}}
        self._meta: dict[str, dict] = {}
        # reverse lookup: faiss row index → event_id
        self._idx_to_id: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load index and meta from disk if they exist."""
        _ensure_dir()
        if os.path.exists(INDEX_FILE) and os.path.exists(META_FILE):
            self._index = faiss.read_index(INDEX_FILE)
            with open(META_FILE, "r") as f:
                self._meta = json.load(f)
            self._idx_to_id = {v["faiss_idx"]: k for k, v in self._meta.items()}
            logger.debug("Loaded FAISS index with %d vectors", self._index.ntotal)
        else:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self._meta = {}
            self._idx_to_id = {}
            logger.debug("Initialised empty FAISS index")

    def save(self) -> None:
        """Persist index and meta to disk."""
        _ensure_dir()
        if self._index is None:
            return
        faiss.write_index(self._index, INDEX_FILE)
        with open(META_FILE, "w") as f:
            json.dump(self._meta, f, indent=2)
        logger.debug("Saved FAISS index (%d vectors)", self._index.ntotal)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_content_hash(self, event_id: str) -> Optional[str]:
        entry = self._meta.get(event_id)
        return entry["content_hash"] if entry else None

    def is_active(self, event_id: str) -> bool:
        entry = self._meta.get(event_id)
        return bool(entry and entry.get("active", True))

    def known_ids(self) -> set[str]:
        return set(self._meta.keys())

    def active_ids(self) -> set[str]:
        return {k for k, v in self._meta.items() if v.get("active", True)}

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def upsert(self, event_id: str, title: str, vector: np.ndarray, card_hash: str) -> None:
        """Add a new event or replace it if the content hash changed."""
        if self._index is None:
            self.load()

        existing = self._meta.get(event_id)
        if existing and existing["content_hash"] == card_hash and existing.get("active", True):
            logger.debug("Event %s unchanged — skipping re-embed", event_id)
            return

        # Append new vector (FAISS append-only — old slot stays but is superseded)
        vec = vector.reshape(1, -1).astype(np.float32)
        new_idx = self._index.ntotal
        self._index.add(vec)

        self._meta[event_id] = {
            "faiss_idx": new_idx,
            "content_hash": card_hash,
            "title": title,
            "active": True,
        }
        self._idx_to_id[new_idx] = event_id
        logger.debug("Upserted event %s at FAISS idx %d", event_id, new_idx)

    def mark_inactive(self, event_id: str) -> None:
        if event_id in self._meta:
            self._meta[event_id]["active"] = False
            logger.debug("Marked event %s inactive", event_id)

    def mark_active(self, event_id: str) -> None:
        if event_id in self._meta:
            self._meta[event_id]["active"] = True
            logger.debug("Marked event %s active", event_id)

    def rebuild_active_only(
        self,
        active_event_ids: list[str],
        vectors: dict[str, np.ndarray],
        titles: dict[str, str],
        hashes: dict[str, str],
    ) -> None:
        """Rebuild the index keeping only active events. Clears stale slots."""
        new_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        new_meta: dict[str, dict] = {}
        new_idx_map: dict[int, str] = {}

        for i, event_id in enumerate(active_event_ids):
            vec = vectors[event_id].reshape(1, -1).astype(np.float32)
            new_index.add(vec)
            new_meta[event_id] = {
                "faiss_idx": i,
                "content_hash": hashes[event_id],
                "title": titles[event_id],
                "active": True,
            }
            new_idx_map[i] = event_id

        self._index = new_index
        self._meta = new_meta
        self._idx_to_id = new_idx_map
        logger.info("Rebuilt FAISS index with %d active events", len(active_event_ids))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[dict]:
        """Return top-k active events by cosine similarity.

        Returns list of {event_id, title, score} sorted descending by score.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        vec = query_vector.reshape(1, -1).astype(np.float32)
        fetch_k = min(self._index.ntotal, k * 3)  # over-fetch to filter inactive
        scores, indices = self._index.search(vec, fetch_k)

        results = []
        seen: set[str] = set()

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            event_id = self._idx_to_id.get(int(idx))
            if not event_id:
                continue
            # Only return the most recent slot for each event_id
            if event_id in seen:
                continue
            if not self._meta.get(event_id, {}).get("active", True):
                continue
            seen.add(event_id)
            results.append({
                "event_id": event_id,
                "title": self._meta[event_id]["title"],
                "score": float(score),
            })
            if len(results) >= k:
                break

        return results
