"""The dev question file is valid, and broken question files are rejected clearly."""

import json

import pytest

from handbook_qa.evaluation.questions import QuestionError, load_questions

from conftest import QUESTIONS


def test_the_dev_set_is_valid_and_matches_the_planned_mix(corpus):
    questions = load_questions(QUESTIONS, set(corpus))
    counts = {}
    for q in questions:
        counts[q.category] = counts.get(q.category, 0) + 1
    assert counts == {"lookup": 12, "version": 6, "date": 3, "multi": 6, "words": 5, "refuse": 5, "clarify": 3}


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
