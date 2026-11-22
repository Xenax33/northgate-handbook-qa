"""The answer step with a fake model: no network, no quota. What's tested is everything around the
model: which passages it reads, what the prompt tells it, and how its JSON is checked."""

from datetime import date
from pathlib import Path

import pytest

from handbook_qa.answer import UNVERIFIED, Assistant
from handbook_qa.answer.citations import check_citations, quote_in
from handbook_qa.answer.context import SMALL_DOCUMENT_CHARS, ContextPassage
from handbook_qa.answer.llm import Completion, LLMError, OpenAICompatibleModel, redact
from handbook_qa.config import Settings
from handbook_qa.ingest import State
from handbook_qa.passages import Passage

from conftest import CORPUS, TODAY


class FakeModel:
    name = "fake"

    def __init__(self, reply: dict):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system, user, schema):
        self.calls.append((system, user))
        return Completion(self.reply, 100, 20, 0.01)


SETTINGS = Settings(corpus_dir=CORPUS, model_cache=Path(".cache/models"), embedding_model="BAAI/bge-small-en-v1.5",
                    fixed_today=TODAY, llm_base_url="http://unused", llm_model="fake", llm_api_key=None)


@pytest.fixture(scope="module")
def assistant(corpus, embedder):
    return Assistant(SETTINGS, model=FakeModel({}), embedder=embedder, documents=list(corpus.values()))


def ask(assistant, question, reply):
    assistant.model = FakeModel(reply)
    return assistant.ask(question), assistant.model.calls[0]


def key_of(answer, doc_id, heading=None):
    return next(c.key for c in answer.context if c.passage.doc_id == doc_id and (heading is None or c.passage.heading == heading))


# What the model reads ---------------------------------------------------------------------------------


def test_small_documents_are_sent_whole(assistant):
    answer, _ = ask(assistant, "How many days of annual leave do I get?", {"status": "refuse", "answer": "", "citations": []})
    sent = [c.passage for c in answer.context if c.passage.doc_id == "hr-leave-policy-v2"]
    assert len(sent) == 7  # every section, including the intro "supersedes v1" and "6. Transition"
    assert len({c.passage.doc_id for c in answer.context}) == 5


def test_the_long_runbook_sends_only_its_opening_and_best_sections(assistant):
    answer, _ = ask(assistant, "How much is the on-call stipend?", {"status": "refuse", "answer": "", "citations": []})
    runbook = [c.passage for c in answer.context if c.passage.doc_id == "eng-oncall-runbook"]
    assert 1 < len(runbook) <= 4
    assert runbook[0].heading == "1. Purpose and scope"
    assert any("$500 per week" in p.text for p in runbook)
    assert sum(len(p.text) for p in runbook) < sum(len(p.text) for p in assistant.passages_by_doc["eng-oncall-runbook"])


def test_old_documents_never_reach_the_model(assistant):
    _, (_, user) = ask(assistant, "How long is the deploy freeze and how many leave days do I get?",
                       {"status": "refuse", "answer": "", "citations": []})
    assert "SUPERSEDED" not in user and "DEPRECATED" not in user


def test_prompt_has_today_labels_and_keys(assistant):
    answer, (system, user) = ask(assistant, "Parental leave for a baby due in 2027?", {"status": "refuse", "answer": "", "citations": []})
    assert "Today is 2026-11-22 (Sunday)" in system
    assert "<<P1>> [" in user and "NOT YET IN FORCE, from 2027-01-01" in user
    assert user.endswith("Employee question: Parental leave for a baby due in 2027?")
    assert [c.key for c in answer.context] == [f"P{n}" for n in range(1, len(answer.context) + 1)]


# How the reply is checked ------------------------------------------------------------------------------


def test_a_correct_answer_with_a_real_quote_is_verified(assistant):
    question = "How many days of annual leave do I get?"
    first, _ = ask(assistant, question, {"status": "refuse", "answer": "", "citations": []})
    key = key_of(first, "hr-leave-policy-v2", "2. Annual leave")
    answer, _ = ask(assistant, question, {"status": "answer", "answer": "16 days a year.",
                                          "citations": [{"passage": key, "quote": "accrue 16 days of annual leave per calendar year"}]})
    assert answer.status == "answer" and answer.warnings == []
    assert answer.citations[0].verified and answer.citations[0].passage.doc_id == "hr-leave-policy-v2"


def test_an_answer_whose_quote_is_made_up_gets_a_warning(assistant):
    question = "How many days of annual leave do I get?"
    first, _ = ask(assistant, question, {"status": "refuse", "answer": "", "citations": []})
    key = key_of(first, "hr-leave-policy-v2", "2. Annual leave")
    answer, _ = ask(assistant, question, {"status": "answer", "answer": "20 days.",
                                          "citations": [{"passage": key, "quote": "accrue 20 days of annual leave"}]})
    assert not answer.citations[0].verified
    assert answer.warnings == [UNVERIFIED]


def test_citing_a_passage_that_was_never_sent_is_caught(assistant):
    answer, _ = ask(assistant, "VPN sessions?", {"status": "answer", "answer": "2.", "citations": [{"passage": "P99", "quote": "2 concurrent"}]})
    assert answer.citations[0].passage is None and answer.citations[0].problem == "the model cited a passage it was not given"
    assert answer.warnings == [UNVERIFIED]


def test_an_answer_with_no_citations_gets_a_warning_but_a_refusal_does_not(assistant):
    answer, _ = ask(assistant, "VPN sessions?", {"status": "answer", "answer": "2.", "citations": []})
    assert answer.warnings == [UNVERIFIED]
    refusal, _ = ask(assistant, "Dental deductible?", {"status": "refuse", "answer": "Not in the handbook.", "citations": []})
    assert refusal.status == "refuse" and refusal.warnings == []


def test_an_unknown_status_from_the_model_is_treated_as_an_answer(assistant):
    answer, _ = ask(assistant, "VPN sessions?", {"status": "maybe", "answer": "2.", "citations": []})
    assert answer.status == "answer" and answer.warnings == [UNVERIFIED]


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
def test_empty_or_huge_questions_are_refused_before_any_model_call(assistant, question):
    assistant.model = FakeModel({})
    with pytest.raises(ValueError):
        assistant.ask(question)
    assert assistant.model.calls == []


# Quote matching -----------------------------------------------------------------------------------------


def passage_with(text):
    return Passage("d#1", "d", "Doc", None, text, State.CURRENT, date(2024, 1, 1))


def test_quote_matching_rules():
    text = "Full-time employees accrue **16 days of annual leave** per calendar year, credited each pay period."
    assert quote_in("accrue 16 days of annual leave", text)  # bold ignored
    assert quote_in("ACCRUE 16 DAYS", text)  # case ignored
    assert quote_in("accrue 16 days ... credited each pay period.", text)  # shortened with "..."
    assert not quote_in("credited each pay period ... accrue 16 days", text)  # parts out of order
    assert not quote_in("accrue 18 days", text)
    assert not quote_in("...", text)


def test_citation_keys_are_cleaned_and_quotes_unquoted():
    context = [ContextPassage("P1", passage_with("Two concurrent VPN sessions."), True)]
    checked = check_citations([{"passage": "<<P1>>", "quote": "“Two concurrent VPN sessions”"}], context)
    assert checked[0].verified


# The real client, without calling it ---------------------------------------------------------------------


def test_missing_api_key_gives_a_helpful_error():
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        OpenAICompatibleModel("http://unused", "m", None)


def test_keys_and_project_ids_are_removed_from_error_text():
    secret = "AIza" + "x" * 35
    text = f"key {secret} invalid for projects/123456789 (project_number: 987654)"
    cleaned = redact(text, secret)
    assert secret not in cleaned and "123456789" not in cleaned and "987654" not in cleaned


def test_small_document_threshold_covers_all_but_the_runbook(corpus):
    large = [d.doc_id for d in corpus.values() if sum(len(s.text) for s in d.sections) > SMALL_DOCUMENT_CHARS]
    assert large == ["eng-oncall-runbook"]
