from datetime import date
from pathlib import Path

import pytest

from handbook_qa.answer.llm import Completion
from handbook_qa.config import Settings, get_settings
from handbook_qa.ingest import load_corpus
from handbook_qa.passages import build_passages

CORPUS = Path(__file__).resolve().parents[1] / "data" / "corpus"
QUESTIONS = Path(__file__).resolve().parents[1] / "eval" / "dev_questions.jsonl"
TODAY = date(2026, 11, 22)  # the date the dev questions were written for


@pytest.fixture(scope="session")
def corpus():
    """All 64 handbook documents, keyed by doc_id."""
    return {doc.doc_id: doc for doc in load_corpus(CORPUS, TODAY)}


@pytest.fixture(scope="session")
def passages(corpus):
    return build_passages(list(corpus.values()))


@pytest.fixture(scope="session")
def embedder():
    """The real embedding model (downloaded into .cache/models on the first run, about 67 MB)."""
    from handbook_qa.search.semantic import Embedder

    settings = get_settings()
    return Embedder(settings.embedding_model, settings.model_cache)


@pytest.fixture(scope="session")
def searcher(passages, embedder):
    from handbook_qa.search import Searcher

    return Searcher(passages, embedder)


class FakeModel:
    """Replies with `reply`, or with each reply of a list in turn (for the second search, D20)."""

    name = "fake"

    def __init__(self, reply):
        self.replies = reply if isinstance(reply, list) else [reply]
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema):
        self.calls.append((system, user))
        return Completion(self.replies[min(len(self.calls), len(self.replies)) - 1], 100, 20, 0.01)


SETTINGS = Settings(corpus_dir=CORPUS, model_cache=CORPUS.parents[1] / ".cache" / "models", embedding_model="BAAI/bge-small-en-v1.5",
                    fixed_today=TODAY, llm_base_url="http://unused", llm_model="fake", llm_api_key=None)
