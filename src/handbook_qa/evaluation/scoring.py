"""The four measures from D4, applied to one answer. Pure functions: no model, no search.

1. retrieval  - every expected document was among the documents the model read
2. facts      - every must_include fact is in the answer text, and no must_not_include fact is
3. citation   - the verified citations cover every expected document, and none cites a forbidden one
4. behaviour  - the answer's status (answer / refuse / clarify) is one the question accepts

A measure that doesn't apply to a question is None (for example retrieval and citation for a question
that must be refused: there is nothing to find). A question passes when every measure that applies passes.
"""

from dataclasses import dataclass

from handbook_qa.evaluation.questions import Question, alternatives
from handbook_qa.evaluation.text_match import contains

MEASURES = ("retrieval", "facts", "citation", "behaviour")


@dataclass(frozen=True)
class Score:
    retrieval: bool | None
    facts: bool | None
    citation: bool | None
    behaviour: bool
    reasons: list[str]

    @property
    def passed(self) -> bool:
        return all(value is not False for value in (self.retrieval, self.facts, self.citation, self.behaviour))


def score_answer(question: Question, status: str, text: str, documents_read: list[str], cited_verified: list[str]) -> Score:
    reasons: list[str] = []

    retrieval = None
    if question.expect_docs:
        missing = [group for group in question.expect_docs if not any(d in documents_read for d in alternatives(group))]
        retrieval = not missing
        if missing:
            reasons.append(f"retrieval: expected document not read: {missing}")

    facts = None
    if question.must_include or question.must_not_include:
        absent = [item for item in question.must_include if not any(contains(text, alt) for alt in alternatives(item))]
        present = [term for term in question.must_not_include if contains(text, term)]
        facts = not absent and not present
        if absent:
            reasons.append(f"facts: missing {absent}")
        if present:
            reasons.append(f"facts: contains forbidden {present}")

    citation = None
    if question.expect_docs and question.behaviour != ["refuse"]:
        uncited = [group for group in question.expect_docs if not any(d in cited_verified for d in alternatives(group))]
        forbidden = [d for d in question.forbid_docs if d in cited_verified]
        citation = not uncited and not forbidden
        if uncited:
            reasons.append(f"citation: no verified quote from {uncited}")
        if forbidden:
            reasons.append(f"citation: cites forbidden {forbidden}")
    elif question.forbid_docs:
        citation = not any(d in cited_verified for d in question.forbid_docs)

    behaviour = status in question.behaviour
    if not behaviour:
        reasons.append(f"behaviour: got {status!r}, expected {' or '.join(question.behaviour)}")

    return Score(retrieval, facts, citation, behaviour, reasons)
