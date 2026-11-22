"""Choose what the model reads for a question (D10, option E).

Search ranks passages; the top documents (ranked by their best passage) are sent to the model. A
small document (under SMALL_DOCUMENT_CHARS, 63 of the 64 in the handbook) is sent whole, so the
model also sees rules written in its other sections (e.g. Leave v2's "supersedes v1" intro). For a
large document (the On-Call Runbook) only its opening passage and its best-matching passages are sent.

Every passage gets a short key ("P1", "P2", ...) that the model uses to cite it.
"""

from dataclasses import dataclass

from handbook_qa.passages import Passage
from handbook_qa.search import Searcher

SMALL_DOCUMENT_CHARS = 2000  # about 500 tokens
SECTIONS_FROM_LARGE_DOCUMENT = 3
DOCUMENTS_PER_QUESTION = 5  # top 5 finds the expected documents for 34 of 35 dev questions (D19)


@dataclass(frozen=True)
class ContextPassage:
    key: str
    passage: Passage
    best_match: bool  # the document's best-matching passage for this question


def build_context(
    searcher: Searcher, passages_by_doc: dict[str, list[Passage]], question: str, n_documents: int = DOCUMENTS_PER_QUESTION
) -> list[ContextPassage]:
    chosen: list[tuple[Passage, bool]] = []
    for doc_id, hits in searcher.top_documents(question, n_documents):
        in_document = passages_by_doc[doc_id]
        best = hits[0].passage.id
        if sum(len(p.text) for p in in_document) <= SMALL_DOCUMENT_CHARS:
            picked = in_document
        else:
            wanted = {in_document[0].id} | {hit.passage.id for hit in hits[:SECTIONS_FROM_LARGE_DOCUMENT]}
            picked = [p for p in in_document if p.id in wanted]  # keep the document's own order
        chosen += [(p, p.id == best) for p in picked]
    return [ContextPassage(f"P{n}", passage, best) for n, (passage, best) in enumerate(chosen, start=1)]


def render_context(context: list[ContextPassage]) -> str:
    return "\n\n".join(f"<<{item.key}>> {item.passage.label}\n{item.passage.text}" for item in context)
