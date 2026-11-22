"""Meaning search with a small local embedding model (fastembed, ONNX on CPU, no PyTorch).

Embeddings run locally rather than through the LLM provider: they use none of the free API quota,
give the same vectors on every run, and need no network after the first download of the model
(about 67 MB for bge-small) into the model cache.
"""

from pathlib import Path

import numpy as np
from fastembed import TextEmbedding


class Embedder:
    """Loads the model once; reused for every index rebuild (e.g. after an upload)."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(model_name, cache_dir=str(cache_dir))

    def passages(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.array(list(self.model.embed(texts)))) if texts else np.zeros((0, 0))

    def query(self, text: str) -> np.ndarray:
        # Note: fastembed 0.9.1's query_embed gives exactly the same vector as embed for this model;
        # it does NOT add bge's "Represent this sentence for searching relevant passages: " prefix.
        return _normalise(np.array(list(self.model.query_embed([text]))))[0]


class EmbeddingIndex:
    def __init__(self, embedder: Embedder, texts: list[str]) -> None:
        self.embedder = embedder
        self.vectors = embedder.passages(texts)

    def rank(self, query: str) -> list[int]:
        """Indexes of all texts, most similar in meaning first."""
        if not len(self.vectors):
            return []
        similarity = self.vectors @ self.embedder.query(query)
        return [int(i) for i in np.argsort(-similarity, kind="stable")]


def _normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)
