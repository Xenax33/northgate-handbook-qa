"""The dev question file is valid, and broken question files are rejected clearly."""

import json

import pytest

from handbook_qa.evaluation.questions import QuestionError, alternatives, load_questions
from handbook_qa.evaluation.text_match import contains

from conftest import QUESTIONS


def test_the_dev_set_is_valid_and_matches_the_planned_mix(corpus):
    questions = load_questions(QUESTIONS, set(corpus))
    counts = {}
    for q in questions:
        counts[q.category] = counts.get(q.category, 0) + 1
    assert counts == {"lookup": 12, "version": 6, "date": 3, "multi": 6, "words": 5, "refuse": 5, "clarify": 3}


def test_every_expected_fact_survives_the_readers(corpus):
    """If a reader drops or mangles text, the fact a question needs disappears. Catch that here, without any LLM."""
    needs_date_arithmetic = {"date-03"}  # 2026-12-03 minus 72 hours; the date isn't written anywhere
    lost = []
    for q in load_questions(QUESTIONS, set(corpus)):
        pool = " ".join(corpus[d].text for group in q.expect_docs for d in alternatives(group))
        for item in q.must_include:
            if not any(contains(pool, alt) for alt in alternatives(item)) and q.id not in needs_date_arithmetic:
                lost.append((q.id, item))
    assert lost == []


def test_refuse_questions_really_have_no_answer_in_the_handbook(corpus):
    everything = " ".join(doc.text for doc in corpus.values())
    for q in load_questions(QUESTIONS, set(corpus)):
        if q.behaviour == ["refuse"]:
            assert not any(contains(everything, term) for term in q.must_not_include), q.id


GOOD = {"id": "x-01", "category": "lookup", "format": "md", "question": "q?", "expect_docs": ["a"],
        "must_include": [["1", "one"]], "must_not_include": [], "forbid_docs": [], "behaviour": "answer", "note": ""}


@pytest.mark.parametrize(
    "lines, message",
    [
        (["{not json"], "not valid JSON"),
        ([{**GOOD, "category": "trivia"}], "unknown category"),
        ([{**GOOD, "behaviour": "guess"}], "behaviour must be"),
        ([{**GOOD, "must_include": [["1", 2]]}], "must be strings"),
        ([{**GOOD, "expect_docs": ["ghost"]}], "unknown document"),
        ([GOOD, GOOD], "duplicate question ids"),
    ],
)
def test_broken_question_files_are_rejected(tmp_path, lines, message):
    path = tmp_path / "q.jsonl"
    path.write_text("\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines), encoding="utf-8")
    with pytest.raises(QuestionError, match=message):
        load_questions(path, {"a"})
