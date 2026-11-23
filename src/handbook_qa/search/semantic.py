"""Meaning search with a small local embedding model (fastembed, ONNX on CPU, no PyTorch).

Embeddings run locally rather than through the LLM provider: they use none of the free API quota,
give the same vectors on every run, and need no network after the first download of the model
(about 67 MB for bge-small) into the model cache.

Memory and speed (measured for the Render free tier, 512 MB RAM and a tenth of a CPU): fastembed's
defaults (batches of 256, one thread per core) peaked at 2.5 GB while embedding the 122 passages.
Batches of 4 on one thread peak at about 320 MB and were faster here (7.9 s instead of 14.6 s). Passage
vectors are also saved to a file in the model cache, so a restart loads them instead of recomputing
them; `python -m handbook_qa.prepare` fills that file ahead of time (Render runs it during the build).
"""

import hashlib
import os
import re
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

# bge models are trained to see this instruction in front of a search query (not in front of the
# passages). fastembed 0.9.1's query_embed does NOT add it (checked: query_embed(q) == embed(q)),
# so we add it ourselves. Measured on the dev set: top 5 went from 33/35 to 34/35 (decision D19).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
BATCH_SIZE = 4


def query_instruction(model_name: str) -> str:
    return BGE_QUERY_INSTRUCTION if model_name.lower().startswith("baai/bge-") else ""


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class Embedder:
    """Loads the model once; reused for every index rebuild (e.g. after an upload)."""

    def __init__(self, model_name: str, cache_dir: Path, threads: int | None = None) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        threads = threads or int(os.environ.get("EMBEDDING_THREADS", "1"))
        self.model = TextEmbedding(model_name, cache_dir=str(cache_dir), threads=threads)
        self.instruction = query_instruction(model_name)
        self.vector_file = cache_dir / f"passage-vectors-{re.sub(r'[^A-Za-z0-9]+', '-', model_name)}.npz"
        self._known: dict[str, np.ndarray] = self._load()  # sha1(text) -> vector
        self._unsaved = False

    def _load(self) -> dict[str, np.ndarray]:
        try:
            with np.load(self.vector_file) as data:
                return {key: data[key] for key in data.files}
        except (OSError, ValueError):  # no file yet, or a damaged one: recompute
            return {}

    def save(self) -> None:
        """Write the vectors computed so far, so the next start doesn't recompute them."""
        if self._unsaved:
            temporary = self.vector_file.with_suffix(".tmp.npz")
            np.savez(temporary, **self._known)
            os.replace(temporary, self.vector_file)
            self._unsaved = False

    def passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0))
        new = [t for t in dict.fromkeys(texts) if _key(t) not in self._known]
        if new:
            vectors = _normalise(np.array(list(self.model.embed(new, batch_size=BATCH_SIZE))))
            for text, vector in zip(new, vectors):
                self._known[_key(text)] = vector
            self._unsaved = True
        return np.array([self._known[_key(t)] for t in texts])

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
