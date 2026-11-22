"""Document states (D9): the manifest's own status field is wrong for two documents, so we derive it."""

import json
from datetime import date

import pytest

from handbook_qa.ingest import ManifestError, State, load_corpus
from handbook_qa.ingest.manifest import ManifestEntry, document_states, read_manifest

from conftest import CORPUS


def test_states_on_the_day_the_questions_were_written(corpus):
    not_current = {doc_id: doc.state for doc_id, doc in corpus.items() if doc.state != State.CURRENT}
    assert not_current == {
        "hr-leave-policy-v1": State.SUPERSEDED,  # manifest says "current"
        "eng-deploy-runbook-2023": State.DEPRECATED,
        "hr-parental-leave-policy-2027": State.NOT_YET_IN_FORCE,  # manifest says "current"
    }
    assert corpus["hr-leave-policy-v1"].superseded_by == "hr-leave-policy-v2"


def test_the_2027_revision_becomes_current_on_its_effective_date():
    docs = {d.doc_id: d for d in load_corpus(CORPUS, date(2027, 1, 1))}
    assert docs["hr-parental-leave-policy-2027"].state == State.CURRENT


def entry(doc_id, effective, status="current", supersedes=None):
    return ManifestEntry(doc_id, f"{doc_id}.md", doc_id, "HR", "People", date.fromisoformat(effective), status, supersedes)


def test_a_document_is_only_superseded_once_its_replacement_is_in_force():
    entries = [entry("v1", "2023-01-01"), entry("v2", "2025-04-01", supersedes="v1")]
    assert document_states(entries, date(2025, 3, 31)) == {"v1": (State.CURRENT, None), "v2": (State.NOT_YET_IN_FORCE, None)}
    assert document_states(entries, date(2025, 4, 1)) == {"v1": (State.SUPERSEDED, "v2"), "v2": (State.CURRENT, None)}


def test_deprecated_wins_over_everything_else():
    assert document_states([entry("old", "2030-01-01", status="deprecated")], date(2026, 1, 1)) == {"old": (State.DEPRECATED, None)}


def write_manifest(tmp_path, documents):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"documents": documents}), encoding="utf-8")
    return path


GOOD = {"doc_id": "a", "path": "a.md", "title": "A", "category": "HR", "owner": "P", "effective_date": "2024-01-01", "status": "current"}


@pytest.mark.parametrize(
    "documents, message",
    [
        ([{**GOOD, "title": ""}], "missing title"),
        ([{**GOOD, "effective_date": "01/01/2024"}], "not YYYY-MM-DD"),
        ([GOOD, GOOD], "duplicate doc_id"),
        ([{**GOOD, "supersedes": "ghost"}], "not in the manifest"),
    ],
)
def test_bad_manifests_are_rejected_with_a_clear_message(tmp_path, documents, message):
    with pytest.raises(ManifestError, match=message):
        read_manifest(write_manifest(tmp_path, documents))


def test_a_listed_file_that_does_not_exist_is_reported(tmp_path):
    write_manifest(tmp_path, [GOOD])
    with pytest.raises(ManifestError, match="does not exist"):
        load_corpus(tmp_path, date(2026, 1, 1))
