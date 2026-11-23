"""The web backend (D21): a thin JSON API over the Assistant, plus the static page (D22).

    GET  /                          the page
    GET  /api/health                documents loaded, model, today's date, whether a key is set
    POST /api/ask                   {"question": "..."} -> answer, status, checked citations, warnings
    GET  /api/documents             every document with its state (current, superseded, ...)
    GET  /api/documents/{doc_id}    one document's passages, for the source viewer
    GET  /api/documents/{doc_id}/file   the original file (PDF, Word, ...)

Errors come back as {"detail": "..."} with a message that is safe to show: the model client already
removes keys and account ids from provider errors.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from handbook_qa.answer import MAX_QUESTION_CHARS, Answer, Assistant, LLMError
from handbook_qa.answer.llm import Completion
from handbook_qa.config import get_settings

STATIC = Path(__file__).parent / "static"


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class MissingKeyModel:
    """Stands in for the model when no API key is set, so the page and the document browser still work."""

    def __init__(self, reason: str, name: str) -> None:
        self.reason = reason
        self.name = name

    def complete_json(self, system: str, user: str, schema: dict) -> Completion:
        raise LLMError(self.reason, "no_key")


def create_app(assistant: Assistant | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if assistant is not None:
            app.state.assistant = assistant
        else:
            settings = get_settings()
            try:
                app.state.assistant = Assistant(settings)
            except LLMError as error:  # no API key: start anyway, explain on the first question
                app.state.assistant = Assistant(settings, model=MissingKeyModel(str(error), settings.llm_model))
        yield

    app = FastAPI(title="Northgate Handbook Q&A", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        a: Assistant = app.state.assistant
        return {
            "documents": len(a.documents),
            "passages": len(a.passages),
            "model": a.model.name,
            "today": a.settings.today().isoformat(),
            "api_key_set": not isinstance(a.model, MissingKeyModel),
        }

    @app.post("/api/ask")
    def ask(body: Question) -> dict:
        a: Assistant = app.state.assistant
        try:
            answer = a.ask(body.question)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except LLMError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        return answer_json(answer, a)

    @app.get("/api/documents")
    def documents() -> list[dict]:
        a: Assistant = app.state.assistant
        return [document_summary(doc) for doc in a.documents.values()]

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str) -> dict:
        a: Assistant = app.state.assistant
        doc = a.documents.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"No document called {doc_id!r}.")
        return {
            **document_summary(doc),
            "passages": [{"id": p.id, "heading": p.heading, "text": p.text} for p in a.passages_by_doc.get(doc_id, [])],
        }

    @app.get("/api/documents/{doc_id}/file")
    def document_file(doc_id: str) -> FileResponse:
        a: Assistant = app.state.assistant
        doc = a.documents.get(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"No document called {doc_id!r}.")
        corpus = a.settings.corpus_dir.resolve()
        path = (corpus / doc.path).resolve()
        if corpus not in path.parents or not path.is_file():  # never serve anything outside the corpus folder
            raise HTTPException(status_code=404, detail="The original file is not available.")
        return FileResponse(path, filename=path.name)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="page")
    return app


def document_summary(doc) -> dict:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "format": doc.format,
        "category": doc.category,
        "owner": doc.owner,
        "effective_date": doc.effective_date.isoformat(),
        "state": doc.state.value,
        "superseded_by": doc.superseded_by,
    }


def answer_json(answer: Answer, assistant: Assistant) -> dict:
    return {
        "question": answer.question,
        "status": answer.status,
        "answer": answer.text,
        "warnings": answer.warnings,
        "citations": [
            {
                "key": c.key,
                "quote": c.quote,
                "verified": c.verified,
                "problem": c.problem,
                "passage_id": c.passage.id if c.passage else None,
                "doc_id": c.passage.doc_id if c.passage else None,
                "title": c.passage.title if c.passage else None,
                "heading": c.passage.heading if c.passage else None,
                "state": c.passage.state.value if c.passage else None,
                "effective_date": c.passage.effective_date.isoformat() if c.passage else None,
            }
            for c in answer.citations
        ],
        "searched_again_with": answer.searched_again_with,
        "documents_read": list(dict.fromkeys(item.passage.doc_id for item in answer.context)),
        "model": answer.model,
        "model_calls": answer.model_calls,
        "today": answer.today.isoformat() if answer.today else None,
        "seconds": answer.seconds,
    }


app = create_app()
