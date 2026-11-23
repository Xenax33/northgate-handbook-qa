"""The web backend (D21): a thin JSON API over the Assistant, plus the static page (D22).

    GET  /                          the page
    GET  /api/health                documents loaded, model, today's date, whether a key is set
    POST /api/ask                   {"question": "..."} -> answer, status, checked citations, warnings
    GET  /api/documents             every document with its state (current, superseded, ...)
    GET  /api/documents/{doc_id}    one document's passages, for the source viewer
    GET  /api/documents/{doc_id}/file   the original file (PDF, Word, ...)
    POST /api/documents             upload a document (multipart form: file, title, effective_date, replaces)
    DELETE /api/documents/{doc_id}  remove an uploaded document

Uploads (D24-D26) need the X-Upload-Token header when UPLOAD_TOKEN is set on the server; after an upload
or removal the assistant re-reads everything, so the next question can use it without a restart.

Errors come back as {"detail": "..."} with a message that is safe to show: the model client already
removes keys and account ids from provider errors.
"""

import hmac
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from handbook_qa.answer import MAX_QUESTION_CHARS, Answer, Assistant, LLMError
from handbook_qa.answer.llm import Completion
from handbook_qa.config import get_settings
from handbook_qa.ingest import SUPPORTED_FORMATS
from handbook_qa.ingest.uploads import MAX_UPLOAD_BYTES, UploadError, remove_upload, save_upload

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
            "uploads_enabled": a.settings.uploads_dir is not None,
            "upload_token_required": bool(a.settings.upload_token),
            "upload_formats": list(SUPPORTED_FORMATS),
            "max_upload_mb": MAX_UPLOAD_BYTES / 1_000_000,
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
        folder = (a.settings.uploads_dir if doc.source == "upload" else a.settings.corpus_dir)
        folder = folder.resolve() if folder else None
        path = (folder / doc.path).resolve() if folder else None
        if path is None or folder not in path.parents or not path.is_file():  # only files inside their own folder
            raise HTTPException(status_code=404, detail="The original file is not available.")
        return FileResponse(path, filename=path.name)

    def check_uploads_allowed(token: str | None) -> Assistant:
        a: Assistant = app.state.assistant
        if a.settings.uploads_dir is None:
            raise HTTPException(status_code=403, detail="Uploads are switched off on this server.")
        expected = a.settings.upload_token
        if expected and not hmac.compare_digest((token or "").encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="The upload token is missing or wrong.")
        return a

    @app.post("/api/documents", status_code=201)
    def upload(
        file: UploadFile = File(...),
        title: str = Form(""),
        effective_date: str = Form(""),
        replaces: str = Form(""),
        x_upload_token: str | None = Header(default=None),
    ) -> dict:
        a = check_uploads_allowed(x_upload_token)
        content = file.file.read(MAX_UPLOAD_BYTES + 1)  # never read more than the limit
        try:
            effective = date.fromisoformat(effective_date) if effective_date else a.settings.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="The effective date must look like 2026-11-23.") from None
        try:
            entry = save_upload(a.settings.uploads_dir, file.filename or "", content, title or Path(file.filename or "").stem,
                                effective, replaces or None, set(a.documents))
        except UploadError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        try:
            a.reload()
        except Exception:  # a file that read fine alone but breaks the whole load: take it out again
            remove_upload(a.settings.uploads_dir, entry["doc_id"])
            a.reload()
            raise HTTPException(status_code=400, detail="The document couldn't be added to the handbook.") from None
        return document_summary(a.documents[entry["doc_id"]])

    @app.delete("/api/documents/{doc_id}")
    def remove(doc_id: str, x_upload_token: str | None = Header(default=None)) -> dict:
        a = check_uploads_allowed(x_upload_token)
        try:
            remove_upload(a.settings.uploads_dir, doc_id)
        except UploadError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        a.reload()
        return {"removed": doc_id}

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
        "supersedes": doc.supersedes,
        "source": doc.source,
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
                "source": assistant.documents[c.passage.doc_id].source if c.passage and c.passage.doc_id in assistant.documents else None,
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
