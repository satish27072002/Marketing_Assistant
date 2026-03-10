"""Embedder — wraps sentence-transformers/all-MiniLM-L6-v2.

Runs fully locally — no API calls, no cost.
Model is loaded once and cached for the lifetime of the process.
"""
import hashlib
import logging
import re
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
_FALLBACK_ONLY = False


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    logger.info("Loading embedding model: %s", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def _token_hash_embedding(text: str) -> np.ndarray:
    """Deterministic local fallback embedding when model is unavailable."""
    vec = np.zeros((EMBEDDING_DIM,), dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]{2,}", text.lower())
    if not tokens:
        tokens = [text.lower().strip() or "_empty_"]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if (digest[4] & 1) else -1.0
        vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm == 0:
        vec[0] = 1.0
        norm = 1.0
    return vec / norm


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of strings. Returns float32 array of shape (len(texts), 384).

    Vectors are L2-normalised so dot product == cosine similarity.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    global _FALLBACK_ONLY

    if _FALLBACK_ONLY:
        return np.stack([_token_hash_embedding(t) for t in texts]).astype(np.float32)

    try:
        model = _get_model()
        vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        vectors = vectors.astype(np.float32)
    except Exception as exc:
        _FALLBACK_ONLY = True
        logger.warning(
            "Embedding model unavailable (%s). Enabling deterministic hash fallback for this process.",
            exc,
        )
        return np.stack([_token_hash_embedding(t) for t in texts]).astype(np.float32)

    # L2-normalise so inner product search gives cosine similarity
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vectors / norms


def embed_single(text: str) -> np.ndarray:
    """Convenience wrapper for a single string. Returns shape (384,)."""
    return embed_texts([text])[0]


def content_hash(text: str) -> str:
    """Return a short SHA-256 hex digest of text, used to detect card changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_event_card(event_id: str, title: str, tags: list[str], description: str) -> str:
    """Build the text representation of an event that gets embedded.

    Keeps it compact: title, tags, and first 300 chars of description.
    """
    tag_str = ", ".join(tags) if tags else "general"
    desc_snippet = description[:300].strip() if description else ""
    return f"{title}. Tags: {tag_str}. {desc_snippet}"
