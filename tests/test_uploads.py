"""Uploading documents (D24-D26): the store's checks, the state rules for uploads, and the API with and
without a token. Everything runs on a temporary uploads folder with the fake model."""

import io
import json
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from handbook_qa.answer import Assistant
from handbook_qa.ingest import State, load_corpus
from handbook_qa.ingest.uploads import MAX_UPLOAD_BYTES, MAX_UPLOADS, UploadError, remove_upload, save_upload
from handbook_qa.web.app import create_app

from conftest import CORPUS, SETTINGS, TODAY, FakeModel

POLICY = b"# Leave Policy v3\n\n## Annual leave\nFull-time employees accrue 20 days of annual leave per year.\n"
KNOWN = {"hr-leave-policy-v2", "it-vpn-guide"}


def save(folder, name="leave-v3.md", content=POLICY, title="Leave Policy v3", effective=TODAY, replaces=None, known=KNOWN):
    return save_upload(folder, name, content, title, effective, replaces, known)


# The store ---------------------------------------------------------------------------------------------


def test_an_upload_is_saved_with_its_own_manifest(tmp_path):
    entry = save(tmp_path, replaces="hr-leave-policy-v2")
    assert entry["doc_id"] == "upload-leave-policy-v3" and entry["supersedes"] == "hr-leave-policy-v2"
    assert (tmp_path / "upload-leave-policy-v3.md").read_bytes() == POLICY
    manifest = json.loads((tmp_path / "uploads.json").read_text(encoding="utf-8"))
    assert [d["doc_id"] for d in manifest["documents"]] == ["upload-leave-policy-v3"]


def test_the_same_title_twice_gets_a_new_id(tmp_path):
    assert save(tmp_path)["doc_id"] == "upload-leave-policy-v3"
    assert save(tmp_path)["doc_id"] == "upload-leave-policy-v3-2"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"name": "notes.exe"}, "isn't supported"),
        ({"content": b""}, "empty"),
        ({"content": b"x" * (MAX_UPLOAD_BYTES + 1)}, "larger than"),
        ({"title": "   "}, "title"),
        ({"replaces": "no-such-document"}, "doesn't exist"),
        ({"name": "broken.pdf", "content": b"%PDF-1.4 not really a pdf"}, "couldn't be read"),
        ({"name": "empty.md", "content": b"# Only a title\n"}, "No text"),
    ],
)
def test_bad_uploads_are_refused_and_nothing_is_kept(tmp_path, kwargs, message):
    with pytest.raises(UploadError, match=message):
        save(tmp_path, **kwargs)
    assert [p.name for p in tmp_path.iterdir() if p.name != "uploads.json"] == []


def test_there_is_a_limit_on_how_many_uploads_are_kept(tmp_path):
    for _ in range(MAX_UPLOADS):
        save(tmp_path)
    with pytest.raises(UploadError, match="Remove one first"):
        save(tmp_path)


def test_removing_an_upload_deletes_its_file(tmp_path):
    entry = save(tmp_path)
    remove_upload(tmp_path, entry["doc_id"])
    assert not (tmp_path / entry["path"]).exists()
    with pytest.raises(UploadError, match="Only uploaded documents"):
        remove_upload(tmp_path, "hr-leave-policy-v2")


def test_an_upload_that_another_upload_replaces_cannot_be_removed_first(tmp_path):
    first = save(tmp_path)
    save(tmp_path, title="Leave Policy v4", replaces=first["doc_id"], known=KNOWN | {first["doc_id"]})
    with pytest.raises(UploadError, match="replaces this document"):
        remove_upload(tmp_path, first["doc_id"])


# Uploads follow the handbook's state rules (D9, D12) -------------------------------------------------


def test_an_upload_can_replace_a_handbook_document(tmp_path):
    save(tmp_path, replaces="hr-leave-policy-v2")
    docs = {d.doc_id: d for d in load_corpus(CORPUS, TODAY, tmp_path)}
    assert len(docs) == 65
    assert docs["hr-leave-policy-v2"].state == State.SUPERSEDED
    assert docs["hr-leave-policy-v2"].superseded_by == "upload-leave-policy-v3"
    assert docs["upload-leave-policy-v3"].source == "upload" and docs["upload-leave-policy-v3"].state == State.CURRENT


def test_an_upload_with_a_future_date_is_not_yet_in_force(tmp_path):
    save(tmp_path, effective=date(2030, 1, 1), replaces="hr-leave-policy-v2")
    docs = {d.doc_id: d for d in load_corpus(CORPUS, TODAY, tmp_path)}
    assert docs["upload-leave-policy-v3"].state == State.NOT_YET_IN_FORCE
    assert docs["hr-leave-policy-v2"].state == State.CURRENT  # not replaced until 2030


def test_the_official_handbook_files_are_never_touched(tmp_path):
    before = {p.name: p.stat().st_mtime_ns for p in CORPUS.iterdir()}
    save(tmp_path, replaces="hr-leave-policy-v2")
    assert {p.name: p.stat().st_mtime_ns for p in CORPUS.iterdir()} == before


# The API -------------------------------------------------------------------------------------------------


@pytest.fixture
def make_client(corpus, embedder, tmp_path):
    def build(token=None):
        settings = replace(SETTINGS, uploads_dir=tmp_path / "uploads", upload_token=token)
        assistant = Assistant(settings, model=FakeModel({"status": "refuse", "answer": "", "citations": [], "search_terms": ""}),
                              embedder=embedder)
        return TestClient(create_app(assistant)), assistant

    return build


def post(client, content=POLICY, name="leave-v3.md", token=None, **form):
    headers = {"X-Upload-Token": token} if token else {}
    data = {"title": "Leave Policy v3", "effective_date": "2026-11-22", **form}
    return client.post("/api/documents", files={"file": (name, io.BytesIO(content))}, data=data, headers=headers)


def test_upload_then_ask_uses_the_new_document_without_a_restart(make_client):
    client, assistant = make_client()
    with client:
        response = post(client, replaces="hr-leave-policy-v2")
        assert response.status_code == 201, response.text
        assert response.json()["doc_id"] == "upload-leave-policy-v3" and response.json()["source"] == "upload"
        answer = client.post("/api/ask", json={"question": "How many days of annual leave do I get?"}).json()
        assert "upload-leave-policy-v3" in answer["documents_read"]
        assert "hr-leave-policy-v2" not in answer["documents_read"]  # replaced, so hidden from search
        docs = {d["doc_id"]: d for d in client.get("/api/documents").json()}
        assert docs["hr-leave-policy-v2"]["state"] == "superseded"
        assert client.get("/api/documents/upload-leave-policy-v3/file").content == POLICY


def test_removing_the_upload_brings_the_replaced_document_back(make_client):
    client, _ = make_client()
    with client:
        post(client, replaces="hr-leave-policy-v2")
        assert client.delete("/api/documents/upload-leave-policy-v3").status_code == 200
        docs = {d["doc_id"]: d for d in client.get("/api/documents").json()}
        assert "upload-leave-policy-v3" not in docs and docs["hr-leave-policy-v2"]["state"] == "current"
        assert client.delete("/api/documents/hr-leave-policy-v2").status_code == 400  # handbook documents stay


def test_with_a_token_set_uploads_need_it(make_client):
    client, _ = make_client(token="s3cret")
    with client:
        assert client.get("/api/health").json()["upload_token_required"] is True
        assert post(client).status_code == 401
        assert post(client, token="wrong").status_code == 401
        assert post(client, token="s3cret").status_code == 201
        assert client.delete("/api/documents/upload-leave-policy-v3").status_code == 401
        assert client.delete("/api/documents/upload-leave-policy-v3", headers={"X-Upload-Token": "s3cret"}).status_code == 200


def test_upload_errors_are_400_with_a_message(make_client):
    client, _ = make_client()
    with client:
        response = post(client, name="virus.exe")
        assert response.status_code == 400 and "isn't supported" in response.json()["detail"]
        assert post(client, effective_date="22/11/2026").status_code == 400


def test_uploads_can_be_switched_off(corpus, embedder):
    assistant = Assistant(SETTINGS, model=FakeModel({}), embedder=embedder, documents=list(corpus.values()))
    with TestClient(create_app(assistant)) as client:
        assert client.get("/api/health").json()["uploads_enabled"] is False
        assert post(client).status_code == 403


def test_uploads_survive_a_restart(make_client):
    client, _ = make_client()
    with client:
        post(client)
    _, restarted = make_client()  # a new Assistant reading the same folder, as after a server restart
    assert "upload-leave-policy-v3" in restarted.documents


