"""The assistant: question in, answer with checked sources out (decisions D10, D13-D16).

    search the handbook -> pick the documents the model reads -> ask the model for JSON
    -> check every citation -> add warnings where the answer can't be trusted as shown
"""

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


class Assistant:
    def __init__(self, settings: Settings, model: ChatModel | None = None, embedder: Embedder | None = None,
                 documents: list[Document] | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or Embedder(settings.embedding_model, settings.model_cache)
        self.model = model or OpenAICompatibleModel(settings.llm_base_url, settings.llm_model, settings.llm_api_key)
        self.load(documents if documents is not None else load_corpus(settings.corpus_dir, settings.today()))

    def load(self, documents: list[Document]) -> None:
        """(Re)build passages and search, e.g. after a document is added."""
        self.documents = {doc.doc_id: doc for doc in documents}
        self.passages = build_passages(documents)
        self.passages_by_doc: dict[str, list[Passage]] = {}
        for passage in self.passages:
            self.passages_by_doc.setdefault(passage.doc_id, []).append(passage)
        self.searcher = Searcher(self.passages, self.embedder)

    def ask(self, question: str) -> Answer:
        question = (question or "").strip()
        if not question:
            raise ValueError("Ask a question first.")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(f"Questions are limited to {MAX_QUESTION_CHARS} characters.")
        today = self.settings.today()
        context = build_context(self.searcher, self.passages_by_doc, question)
        completion = self.model.complete_json(system_prompt(today), user_prompt(render_context(context), question), ANSWER_SCHEMA)
        data = completion.data
        status = data.get("status") if data.get("status") in STATUSES else "answer"
        citations = check_citations(data.get("citations") or [], context)
        return Answer(
            question=question,
            status=status,
            text=str(data.get("answer", "")).strip(),
            citations=citations,
            warnings=warnings_for(status, citations),
            context=context,
            model=self.model.name,
            today=today,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            seconds=completion.seconds,
        )


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
