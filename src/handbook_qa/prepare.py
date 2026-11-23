"""Download the embedding model and compute the passage vectors ahead of time (no API key needed).

    uv run python -m handbook_qa.prepare

Render runs this during the build, so a free instance that wakes up from sleep loads the vectors from
.cache/models instead of embedding every passage on a tenth of a CPU. Locally it is optional: the app
does the same on its first start.
"""

import time

from handbook_qa.config import get_settings
from handbook_qa.ingest import load_corpus
from handbook_qa.passages import build_passages
from handbook_qa.search import Searcher
from handbook_qa.search.semantic import Embedder


def main() -> None:
    started = time.monotonic()
    settings = get_settings()
    embedder = Embedder(settings.embedding_model, settings.model_cache)
    passages = build_passages(load_corpus(settings.corpus_dir, settings.today()))
    Searcher(passages, embedder)
    embedder.save()
    print(f"Ready: {len(passages)} passages embedded with {settings.embedding_model} into {embedder.vector_file.name} "
          f"in {time.monotonic() - started:.1f} s")


if __name__ == "__main__":
    main()
