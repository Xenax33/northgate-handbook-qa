"""The web API through FastAPI's test client, with the fake model: no server, no network, no quota."""

import pytest
from fastapi.testclient import TestClient

from handbook_qa.answer import Assistant
from handbook_qa.answer.llm import LLMError
from handbook_qa.web.app import MissingKeyModel, create_app

from conftest import SETTINGS, FakeModel


@pytest.fixture(scope="module")
def assistant(corpus, embedder):
    return Assistant(SETTINGS, model=FakeModel({}), embedder=embedder, documents=list(corpus.values()))


@pytest.fixture(scope="module")
def client(assistant):
    with TestClient(create_app(assistant)) as test_client:
        yield test_client


def test_the_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "Northgate Handbook" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_health(client):
    assert client.get("/api/health").json() == {
        "documents": 64, "passages": 122, "model": "fake", "today": "2026-11-22", "api_key_set": True,
    }


def test_ask_returns_the_answer_with_checked_sources(client, assistant):
    question = "How many days of annual leave do I get?"
    assistant.model = FakeModel({"status": "refuse", "answer": "", "citations": [], "search_terms": ""})
    first = client.post("/api/ask", json={"question": question}).json()
    key = next(c for c in assistant.ask(question).context if c.passage.heading == "2. Annual leave").key
    assistant.model = FakeModel({"status": "answer", "answer": "16 days.", "search_terms": "",
                                 "citations": [{"passage": key, "quote": "accrue 16 days of annual leave"}]})
    body = client.post("/api/ask", json={"question": question}).json()
    assert first["status"] == "refuse"
    assert body["status"] == "answer" and body["answer"] == "16 days." and body["warnings"] == []
    citation = body["citations"][0]
    assert citation["verified"] is True
    assert citation["doc_id"] == "hr-leave-policy-v2" and citation["heading"] == "2. Annual leave"
    assert citation["passage_id"].startswith("hr-leave-policy-v2#")
    assert "hr-leave-policy-v1" not in body["documents_read"]


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "x" * 1001}])
def test_bad_questions_are_rejected_before_the_model(client, assistant, payload):
    assistant.model = FakeModel({})
    assert client.post("/api/ask", json=payload).status_code == 422
    assert assistant.model.calls == []


def test_blank_question_gets_a_clear_message(client):
    response = client.post("/api/ask", json={"question": "   "})
    assert response.status_code == 400 and response.json()["detail"] == "Ask a question first."


def test_model_errors_become_a_503_with_a_safe_message(client, assistant):
    class Failing:
        name = "fake"

        def complete_json(self, *args):
            raise LLMError("The model service returned HTTP 503.", "http_503", retryable=True)

    assistant.model = Failing()
    response = client.post("/api/ask", json={"question": "VPN sessions?"})
    assert response.status_code == 503 and response.json()["detail"] == "The model service returned HTTP 503."


def test_documents_list_shows_each_state(client):
    docs = {d["doc_id"]: d for d in client.get("/api/documents").json()}
    assert len(docs) == 64
    assert docs["hr-leave-policy-v1"]["state"] == "superseded" and docs["hr-leave-policy-v1"]["superseded_by"] == "hr-leave-policy-v2"
    assert docs["eng-deploy-runbook-2023"]["state"] == "deprecated"
    assert docs["hr-parental-leave-policy-2027"]["state"] == "not yet in force"


def test_one_document_has_its_passages_for_the_viewer(client):
    doc = client.get("/api/documents/hr-travel-policy").json()
    assert doc["title"] == "Travel Policy" and doc["format"] == "docx"
    assert any("| Tier 1 | $275 |" in p["text"] for p in doc["passages"])
    assert client.get("/api/documents/nope").status_code == 404


def test_the_original_file_can_be_downloaded(client):
    response = client.get("/api/documents/hr-leave-policy-v2/file")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert "hr-leave-policy-v2.pdf" in response.headers["content-disposition"]


def test_a_path_outside_the_corpus_is_never_served(client, assistant):
    from dataclasses import replace

    doc = assistant.documents["it-vpn-guide"]
    assistant.documents["it-vpn-guide"] = replace(doc, path="../../pyproject.toml")
    try:
        assert client.get("/api/documents/it-vpn-guide/file").status_code == 404
    finally:
        assistant.documents["it-vpn-guide"] = doc


def test_without_an_api_key_the_page_works_and_questions_explain_why(corpus, embedder):
    no_key = Assistant(SETTINGS, model=MissingKeyModel("No API key found. Put GEMINI_API_KEY=... in the .env file.", "m"),
                       embedder=embedder, documents=list(corpus.values()))
    with TestClient(create_app(no_key)) as client:
        assert client.get("/api/health").json()["api_key_set"] is False
        response = client.post("/api/ask", json={"question": "VPN sessions?"})
        assert response.status_code == 503 and "GEMINI_API_KEY" in response.json()["detail"]
