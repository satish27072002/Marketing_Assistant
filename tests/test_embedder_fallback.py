import numpy as np

from embeddings import embedder


def test_embedder_fallback_if_model_unavailable(monkeypatch):
    def _raise():
        raise RuntimeError("model load failed")

    monkeypatch.setattr(embedder, "_get_model", _raise)
    vecs = embedder.embed_texts(["hello stockholm", "looking for friends"])
    assert vecs.shape == (2, embedder.EMBEDDING_DIM)
    assert np.isfinite(vecs).all()
    norms = np.linalg.norm(vecs, axis=1)
    assert np.all(norms > 0.99)
