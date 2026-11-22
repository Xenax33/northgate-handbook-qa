"""Hybrid search over passages (D11), with superseded and deprecated documents left out (D12).

Keyword and meaning search each rank the passages; reciprocal rank fusion (RRF) merges the two
rankings, so a passage that both rank highly wins, and one that only one of them finds still shows up.
"""

from dataclasses import dataclass

from handbook_qa.ingest import State
from handbook_qa.passages import Passage
from handbook_qa.search.keyword import KeywordIndex
from handbook_qa.search.semantic import Embedder, EmbeddingIndex

HIDDEN_STATES = {State.SUPERSEDED, State.DEPRECATED}
RRF_K = 60  # the usual constant; it dampens the gap between rank 1 and rank 2


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float
    keyword_rank: int | None  # 1 = best; None = no shared words with the question
    meaning_rank: int


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Merge rankings of item indexes. Ties keep the order of first appearance, so results are repeatable."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position + 1)
    order = {item: n for n, item in enumerate(dict.fromkeys(i for r in rankings for i in r))}
    return sorted(scores.items(), key=lambda pair: (-pair[1], order[pair[0]]))


class Searcher:
    def __init__(self, passages: list[Passage], embedder: Embedder) -> None:
        self.passages = [p for p in passages if p.state not in HIDDEN_STATES]
        texts = [p.search_text for p in self.passages]
        self.keyword = KeywordIndex(texts)
        self.meaning = EmbeddingIndex(embedder, texts)

    def search(self, query: str, limit: int = 10) -> list[Hit]:
        keyword = self.keyword.rank(query)
        meaning = self.meaning.rank(query)
        keyword_pos = {item: n + 1 for n, item in enumerate(keyword)}
        meaning_pos = {item: n + 1 for n, item in enumerate(meaning)}
        fused = reciprocal_rank_fusion([keyword, meaning])[:limit]
        return [Hit(self.passages[i], score, keyword_pos.get(i), meaning_pos[i]) for i, score in fused]

    def top_documents(self, query: str, n_documents: int = 5) -> list[tuple[str, list[Hit]]]:
        """Documents ranked by their best passage, each with its matching passages (best first)."""
        documents: dict[str, list[Hit]] = {}
        for hit in self.search(query, limit=len(self.passages)):
            documents.setdefault(hit.passage.doc_id, []).append(hit)
        return list(documents.items())[:n_documents]
