"""The four measures on made-up answers to real dev questions. A scoring bug would silently make the
eval numbers wrong, so each measure is checked passing and failing."""

import pytest

from handbook_qa.evaluation.questions import load_questions
from handbook_qa.evaluation.scoring import score_answer

from conftest import QUESTIONS


@pytest.fixture(scope="module")
def q():
    return {question.id: question for question in load_questions(QUESTIONS)}


def test_a_correct_answer_passes_all_four(q):
    s = score_answer(q["version-01"], "answer", "Full-time employees get 16 days a year.",
                     ["hr-leave-policy-v2", "ref-faq"], ["hr-leave-policy-v2"])
    assert (s.retrieval, s.facts, s.citation, s.behaviour, s.passed) == (True, True, True, True, True)
    assert s.reasons == []


def test_the_stale_value_fails_facts_even_next_to_the_right_one(q):
    s = score_answer(q["version-01"], "answer", "16 days (it was 12 days under v1).", ["hr-leave-policy-v2"], ["hr-leave-policy-v2"])
    assert s.facts is False and not s.passed
    assert "facts: contains forbidden ['12 days']" in s.reasons


def test_right_text_but_no_verified_quote_from_the_expected_document_fails_citation(q):
    s = score_answer(q["version-01"], "answer", "16 days.", ["hr-leave-policy-v2"], ["ref-faq"])
    assert s.facts is True and s.citation is False and not s.passed


def test_expected_document_not_read_fails_retrieval(q):
    s = score_answer(q["version-01"], "answer", "16 days.", ["ref-faq"], [])
    assert s.retrieval is False


def test_alternative_documents_and_alternative_wordings(q):
    s = score_answer(q["lookup-04"], "answer", "You need three quotes.", ["fin-procurement-policy"], ["fin-procurement-policy"])
    assert s.passed
    s = score_answer(q["lookup-11"], "answer", "Within 45 minutes.", ["eng-oncall-runbook"], ["eng-oncall-runbook"])
    assert s.passed  # either the SEV definitions or the on-call runbook may be the source


def test_multi_document_questions_need_every_document(q):
    one = score_answer(q["multi-02"], "answer", "$75 a day and $200 a night.", ["fin-per-diem-table", "hr-travel-policy"],
                       ["fin-per-diem-table"])
    assert one.citation is False
    both = score_answer(q["multi-02"], "answer", "$75 a day and $200 a night.", ["fin-per-diem-table", "hr-travel-policy"],
                        ["fin-per-diem-table", "hr-travel-policy"])
    assert both.passed


def test_refuse_questions_skip_retrieval_and_citation(q):
    s = score_answer(q["refuse-01"], "refuse", "The handbook doesn't list holiday dates.", ["hr-working-hours-holidays"], [])
    assert (s.retrieval, s.citation, s.passed) == (None, None, True)
    invented = score_answer(q["refuse-01"], "answer", "Thanksgiving is on November 26.", [], [])
    assert invented.facts is False and invented.behaviour is False and not invented.passed


def test_wrong_behaviour_fails(q):
    s = score_answer(q["clarify-01"], "answer", "Maya Rivera, Maya Brooks and Maya Park.", ["org-chart"], ["org-chart"])
    assert s.behaviour is False and s.facts is True
    assert "behaviour: got 'answer', expected clarify" in s.reasons


def test_a_question_that_accepts_two_behaviours(q):
    for status in ("clarify", "answer"):
        s = score_answer(q["clarify-03"], status, "Birth parents get 16 weeks; secondary caregivers 12 weeks.",
                         ["hr-parental-leave-policy"], ["hr-parental-leave-policy"])
        assert s.passed, status


def test_citing_a_forbidden_document_fails(q):
    s = score_answer(q["version-02"], "answer", "72 hours.", ["eng-deploy-runbook"], ["eng-deploy-runbook", "eng-deploy-runbook-2023"])
    assert s.citation is False
    assert "citation: cites forbidden ['eng-deploy-runbook-2023']" in s.reasons
