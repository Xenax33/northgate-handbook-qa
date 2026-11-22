from datetime import date
from pathlib import Path

import pytest

from handbook_qa.ingest import load_corpus

CORPUS = Path(__file__).resolve().parents[1] / "data" / "corpus"
TODAY = date(2026, 11, 22)  # the date the dev questions were written for


@pytest.fixture(scope="session")
def corpus():
    """All 64 handbook documents, keyed by doc_id."""
    return {doc.doc_id: doc for doc in load_corpus(CORPUS, TODAY)}
