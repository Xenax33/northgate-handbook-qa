"""Meaning search with a small local embedding model (fastembed, ONNX on CPU, no PyTorch).

Embeddings run locally rather than through the LLM provider: they use none of the free API quota,
give the same vectors on every run, and need no network after the first download of the model
(about 67 MB for bge-small) into the model cache.
"""

from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

# bge models are trained to see this instruction in front of a search query (not in front of the
# passages). fastembed 0.9.1's query_embed does NOT add it (checked: query_embed(q) == embed(q)),
# so we add it ourselves. Measured on the dev set: top 5 went from 33/35 to 34/35 (decision D19).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def query_instruction(model_name: str) -> str:
    return BGE_QUERY_INSTRUCTION if model_name.lower().startswith("baai/bge-") else ""


class Embedder:
    """Loads the model once; reused for every index rebuild (e.g. after an upload)."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(model_name, cache_dir=str(cache_dir))
        self.instruction = query_instruction(model_name)

    def passages(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.array(list(self.model.embed(texts)))) if texts else np.zeros((0, 0))

    def query(self, text: str) -> np.ndarray:
        return _normalise(np.array(list(self.model.embed([self.instruction + text]))))[0]


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
