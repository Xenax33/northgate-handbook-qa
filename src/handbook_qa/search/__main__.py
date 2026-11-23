"""Try the search by hand: which documents and passages come back for a question. No LLM calls.

    uv run python -m handbook_qa.search "how many leave days do I get?"
"""

import sys

from handbook_qa.config import get_settings
from handbook_qa.ingest import load_corpus
from handbook_qa.passages import build_passages
from handbook_qa.search import Searcher
from handbook_qa.search.semantic import Embedder


def main(argv: list[str]) -> int:
    if not argv:
        print('Usage: uv run python -m handbook_qa.search "your question"')
        return 1
    question = " ".join(argv)
    settings = get_settings()
    searcher = Searcher(
        build_passages(load_corpus(settings.corpus_dir, settings.today(), settings.uploads_dir)),
        Embedder(settings.embedding_model, settings.model_cache),
    )
    print(f"Question: {question}\n")
    for rank, (doc_id, hits) in enumerate(searcher.top_documents(question, 5), start=1):
        best = hits[0]
        keyword = best.keyword_rank if best.keyword_rank is not None else "-"
        print(f"{rank}. {doc_id}   (best passage: keyword rank {keyword}, meaning rank {best.meaning_rank})")
        print(f"   {best.passage.label}")
        print("   " + best.passage.text[:300].replace("\n", "\n   ") + ("..." if len(best.passage.text) > 300 else ""))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
