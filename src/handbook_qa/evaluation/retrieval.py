"""Measure 1 (D4): did search find the expected documents? No LLM calls, so it can run as often as we like."""

from collections import Counter
from dataclasses import dataclass

from handbook_qa.evaluation.questions import Question, alternatives
from handbook_qa.search import Searcher

CUTOFFS = (1, 3, 5)


@dataclass(frozen=True)
class RetrievalResult:
    question_id: str
    category: str
    ranked_documents: list[str]  # top max(CUTOFFS) documents
    hit_at: dict[int, bool]
    forbidden_found: list[str]  # forbid_docs that search returned (should always be empty: D12)


def expected_found(question: Question, documents: list[str]) -> bool:
    return all(any(doc in documents for doc in alternatives(group)) for group in question.expect_docs)


def score_retrieval(searcher: Searcher, questions: list[Question]) -> list[RetrievalResult]:
    results = []
    for question in questions:
        if not question.expect_docs:
            continue  # refuse questions have nothing to find
        ranked = [doc_id for doc_id, _ in searcher.top_documents(question.question, max(CUTOFFS))]
        results.append(
            RetrievalResult(
                question_id=question.id,
                category=question.category,
                ranked_documents=ranked,
                hit_at={n: expected_found(question, ranked[:n]) for n in CUTOFFS},
                forbidden_found=[doc for doc in question.forbid_docs if doc in ranked],
            )
        )
    return results


def summarise(results: list[RetrievalResult]) -> dict:
    total = len(results)
    by_category = Counter(r.category for r in results)
    return {
        "questions": total,
        "hit_at": {n: sum(r.hit_at[n] for r in results) for n in CUTOFFS},
        "hit_at_3_by_category": {
            category: [sum(r.hit_at[3] for r in results if r.category == category), count]
            for category, count in sorted(by_category.items())
        },
        "misses_at_3": {r.question_id: r.ranked_documents[:3] for r in results if not r.hit_at[3]},
        "forbidden_documents_returned": {r.question_id: r.forbidden_found for r in results if r.forbidden_found},
    }
