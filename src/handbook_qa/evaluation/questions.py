"""Load and validate eval/dev_questions.jsonl (format described in eval/README.md)."""

import json
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = {"lookup", "version", "date", "multi", "words", "refuse", "clarify"}
BEHAVIOURS = {"answer", "refuse", "clarify"}

# A "rule list": every item required; an item that is itself a list is a set of alternatives.
Rule = str | list[str]


class QuestionError(ValueError):
    pass


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    format: str
    question: str
    expect_docs: list[Rule]
    must_include: list[Rule]
    must_not_include: list[str]
    forbid_docs: list[str]
    behaviour: list[str]  # acceptable statuses
    note: str


def alternatives(item: Rule) -> list[str]:
    return item if isinstance(item, list) else [item]


def load_questions(path: Path, known_doc_ids: set[str] | None = None) -> list[Question]:
    questions = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise QuestionError(f"{path.name} line {number}: not valid JSON ({error.msg})") from error
        questions.append(_parse(raw, f"{path.name} line {number}", known_doc_ids))
    ids = [q.id for q in questions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise QuestionError(f"duplicate question ids: {', '.join(duplicates)}")
    return questions


def _parse(raw: dict, where: str, known_doc_ids: set[str] | None) -> Question:
    def require(key: str, kind: type):
        if not isinstance(raw.get(key), kind):
            raise QuestionError(f"{where}: field {key!r} must be a {kind.__name__}")
        return raw[key]

    def rules(key: str) -> list[Rule]:
        items = require(key, list)
        for item in items:
            if not (isinstance(item, str) or (isinstance(item, list) and item and all(isinstance(x, str) for x in item))):
                raise QuestionError(f"{where}: {key!r} items must be strings or non-empty lists of strings")
        return items

    category = require("category", str)
    if category not in CATEGORIES:
        raise QuestionError(f"{where}: unknown category {category!r}")
    behaviour = raw.get("behaviour")
    behaviour = [behaviour] if isinstance(behaviour, str) else behaviour
    if not isinstance(behaviour, list) or not behaviour or not set(behaviour) <= BEHAVIOURS:
        raise QuestionError(f"{where}: behaviour must be one of {sorted(BEHAVIOURS)} or a list of them")

    question = Question(
        id=require("id", str),
        category=category,
        format=require("format", str),
        question=require("question", str),
        expect_docs=rules("expect_docs"),
        must_include=rules("must_include"),
        must_not_include=[str(x) for x in require("must_not_include", list)],
        forbid_docs=[str(x) for x in require("forbid_docs", list)],
        behaviour=behaviour,
        note=require("note", str),
    )
    if known_doc_ids is not None:
        named = {d for item in question.expect_docs for d in alternatives(item)} | set(question.forbid_docs)
        unknown = sorted(named - known_doc_ids)
        if unknown:
            raise QuestionError(f"{where} ({question.id}): unknown document id(s) {', '.join(unknown)}")
    return question
