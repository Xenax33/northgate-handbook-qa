"""The assistant: question in, answer with checked sources out (decisions D10, D13-D16, D20).

    search the handbook -> pick the documents the model reads -> ask the model for JSON
    -> if it refused: search again with the handbook words it suggested, and ask once more
    -> check every citation -> add warnings where the answer can't be trusted as shown

The second search (D20) exists because employees don't use the handbook's words: "PTO" never
appears in it, so the first search misses the leave policy. It costs a second model request only
when the first answer is a refusal and the new search finds different documents.
"""

import threading
from dataclasses import dataclass, field
from datetime import date

from handbook_qa.answer.citations import Citation, check_citations
from handbook_qa.answer.context import ContextPassage, build_context, render_context
from handbook_qa.answer.llm import ChatModel, LLMError, OpenAICompatibleModel
from handbook_qa.answer.prompt import ANSWER_SCHEMA, system_prompt, user_prompt
from handbook_qa.config import Settings
from handbook_qa.ingest import Document, load_corpus
from handbook_qa.passages import Passage, build_passages
from handbook_qa.search import Searcher
from handbook_qa.search.semantic import Embedder

STATUSES = ("answer", "refuse", "clarify")
MAX_QUESTION_CHARS = 1000

UNVERIFIED = "Couldn't verify this answer against the handbook: none of its quotes were found in the cited passages."
SOME_UNVERIFIED = "{n} of the quotes couldn't be found in the passage they cite."
CITES_FUTURE = "Part of this answer comes from a document that is not in force yet."


@dataclass(frozen=True)
class Answer:
    question: str
    status: str  # answer | refuse | clarify
    text: str
    citations: list[Citation]
    warnings: list[str]
    context: list[ContextPassage] = field(repr=False)
    model: str = ""
    today: date | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    seconds: float | None = None
    model_calls: int = 1
    searched_again_with: str | None = None  # the model's handbook wording, when a second search ran
    first_status: str | None = None  # the first answer's status, when a second search ran


@dataclass(frozen=True)
class Index:
    """Everything built from the documents. Replaced as a whole on reload, so a question asked while a
    document is being added sees either the old index or the new one, never a mix."""

    documents: dict[str, Document]
    passages: list[Passage]
    passages_by_doc: dict[str, list[Passage]]
    searcher: Searcher


class Assistant:
    def __init__(self, settings: Settings, model: ChatModel | None = None, embedder: Embedder | None = None,
                 documents: list[Document] | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or Embedder(settings.embedding_model, settings.model_cache)
        self.model = model or OpenAICompatibleModel(settings.llm_base_url, settings.llm_model, settings.llm_api_key)
        self._reload_lock = threading.Lock()
        self.load(documents if documents is not None else self._read_documents())

    def _read_documents(self) -> list[Document]:
        return load_corpus(self.settings.corpus_dir, self.settings.today(), self.settings.uploads_dir)

    def load(self, documents: list[Document]) -> None:
        """Build passages and search for these documents, then switch to them in one step."""
        passages = build_passages(documents)
        by_doc: dict[str, list[Passage]] = {}
        for passage in passages:
            by_doc.setdefault(passage.doc_id, []).append(passage)
        self.index = Index({doc.doc_id: doc for doc in documents}, passages, by_doc, Searcher(passages, self.embedder))
        try:
            self.embedder.save()  # next start loads these vectors instead of recomputing them
        except OSError:
            pass  # a read-only disk only costs speed

    def reload(self) -> None:
        """Read the handbook and the uploads again (after an upload or a removal), without a restart."""
        with self._reload_lock:
            self.load(self._read_documents())

    @property
    def documents(self) -> dict[str, Document]:
        return self.index.documents

    @property
    def passages(self) -> list[Passage]:
        return self.index.passages

    @property
    def passages_by_doc(self) -> dict[str, list[Passage]]:
        return self.index.passages_by_doc

    @property
    def searcher(self) -> Searcher:
        return self.index.searcher

    def ask(self, question: str) -> Answer:
        question = (question or "").strip()
        if not question:
            raise ValueError("Ask a question first.")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(f"Questions are limited to {MAX_QUESTION_CHARS} characters.")
        today = self.settings.today()
        index = self.index  # one consistent snapshot for this question
        context = build_context(index.searcher, index.passages_by_doc, question)
        first = self.model.complete_json(system_prompt(today), user_prompt(render_context(context), question), ANSWER_SCHEMA)
        completions, final, again, first_status = [first], first, None, None

        terms = str(first.data.get("search_terms") or "").strip()
        if status_of(first.data) == "refuse" and terms and terms.lower() != question.lower():
            new_context = build_context(index.searcher, index.passages_by_doc, terms)
            if {c.passage.doc_id for c in new_context} != {c.passage.doc_id for c in context}:
                second = self.model.complete_json(system_prompt(today), user_prompt(render_context(new_context), question), ANSWER_SCHEMA)
                completions.append(second)
                final, context, again, first_status = second, new_context, terms, "refuse"

        status = status_of(final.data)
        citations = check_citations(final.data.get("citations") or [], context)
        return Answer(
            question=question,
            status=status,
            text=str(final.data.get("answer", "")).strip(),
            citations=citations,
            warnings=warnings_for(status, citations),
            context=context,
            model=self.model.name,
            today=today,
            prompt_tokens=total(c.prompt_tokens for c in completions),
            completion_tokens=total(c.completion_tokens for c in completions),
            seconds=round(sum(c.seconds for c in completions), 2),
            model_calls=len(completions),
            searched_again_with=again,
            first_status=first_status,
        )


def status_of(data: dict) -> str:
    return data.get("status") if data.get("status") in STATUSES else "answer"


def total(values) -> int | None:
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def warnings_for(status: str, citations: list[Citation]) -> list[str]:
    """The code check from D16: an answer must rest on at least one verified quote."""
    warnings = []
    verified = [c for c in citations if c.verified]
    if status == "answer" and not verified:
        warnings.append(UNVERIFIED)
    elif len(verified) < len(citations):
        warnings.append(SOME_UNVERIFIED.format(n=len(citations) - len(verified)))
    if any(c.verified and c.passage and c.passage.state.value == "not yet in force" for c in citations):
        warnings.append(CITES_FUTURE)
    return warnings


__all__ = ["Answer", "Assistant", "Citation", "LLMError"]
