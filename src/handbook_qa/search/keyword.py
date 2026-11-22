"""Keyword search with BM25 (bm25s). Good at exact terms: "SEV2", "L2", "$40,000"."""

import bm25s


def _tokenize(texts: list[str]):
    return bm25s.tokenize(texts, stopwords="en", show_progress=False)


class KeywordIndex:
    def __init__(self, texts: list[str]) -> None:
        self.size = len(texts)
        self.model = bm25s.BM25()
        if texts:
            self.model.index(_tokenize(texts), show_progress=False)

    def rank(self, query: str) -> list[int]:
        """Indexes of matching texts, best first. Texts that share no word with the query are left out."""
        if not self.size:
            return []
        tokens = _tokenize([query])
        if not any(len(ids) for ids in tokens.ids):
            return []  # the query was only stopwords or punctuation
        results, scores = self.model.retrieve(tokens, k=self.size, show_progress=False)
        return [int(i) for i, score in zip(results[0], scores[0]) if score > 0]
