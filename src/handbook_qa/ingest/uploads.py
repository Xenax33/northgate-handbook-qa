"""Uploaded documents (D24-D26): saved in their own folder with their own manifest (uploads.json, same
format as the handbook's), never mixed into data/corpus. Every check happens before anything is kept:
the file is read with the normal reader first, so a broken or empty file is refused, not stored."""

import json
import os
import re
from datetime import date
from pathlib import Path

from handbook_qa.ingest import READERS, SUPPORTED_FORMATS, UPLOADS_MANIFEST, read_sections
from handbook_qa.ingest.document import ReaderError

MAX_UPLOAD_BYTES = 1_000_000
MAX_UPLOADS = 20
MAX_TITLE_CHARS = 200


class UploadError(ValueError):
    """The upload was refused; the message says why and is safe to show."""


def _manifest(uploads_dir: Path) -> dict:
    path = uploads_dir / UPLOADS_MANIFEST
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {"documents": []}


def _write_manifest(uploads_dir: Path, manifest: dict) -> None:
    temporary = uploads_dir / (UPLOADS_MANIFEST + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, uploads_dir / UPLOADS_MANIFEST)  # never leaves a half-written manifest


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "document"


def save_upload(uploads_dir: Path, filename: str, content: bytes, title: str, effective_date: date,
                replaces: str | None, known_ids: set[str]) -> dict:
    """Check, read and store one uploaded file. Returns its manifest entry."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in READERS:
        raise UploadError(f"That file type isn't supported. Use one of: {', '.join(SUPPORTED_FORMATS)}.")
    if not content:
        raise UploadError("The file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadError(f"The file is larger than {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    title = " ".join((title or "").split())
    if not title:
        raise UploadError("Give the document a title.")
    if len(title) > MAX_TITLE_CHARS:
        raise UploadError(f"Keep the title under {MAX_TITLE_CHARS} characters.")
    if replaces and replaces not in known_ids:
        raise UploadError("The document it replaces doesn't exist.")

    uploads_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(uploads_dir)
    if len(manifest["documents"]) >= MAX_UPLOADS:
        raise UploadError(f"There are already {MAX_UPLOADS} uploaded documents. Remove one first.")

    taken = known_ids | {d["doc_id"] for d in manifest["documents"]}
    doc_id, n = f"upload-{_slug(title)}", 2
    while doc_id in taken:
        doc_id, n = f"upload-{_slug(title)}-{n}", n + 1
    path = uploads_dir / f"{doc_id}{suffix}"
    path.write_bytes(content)
    try:
        sections = read_sections(path)
    except ReaderError as error:
        path.unlink(missing_ok=True)
        raise UploadError(f"The file couldn't be read: {error}") from None
    if not any(section.text.strip() for section in sections):
        path.unlink(missing_ok=True)
        raise UploadError("No text was found in the file (a scanned PDF has none).")

    entry = {"doc_id": doc_id, "path": path.name, "title": title, "category": "Uploaded", "owner": "Unknown",
             "effective_date": effective_date.isoformat(), "status": "current"}
    if replaces:
        entry["supersedes"] = replaces
    manifest["documents"].append(entry)
    _write_manifest(uploads_dir, manifest)
    return entry


def remove_upload(uploads_dir: Path, doc_id: str) -> None:
    manifest = _manifest(uploads_dir)
    entry = next((d for d in manifest["documents"] if d["doc_id"] == doc_id), None)
    if entry is None:
        raise UploadError("Only uploaded documents can be removed.")
    replaced_by_another = [d["doc_id"] for d in manifest["documents"] if d.get("supersedes") == doc_id]
    if replaced_by_another:
        raise UploadError(f"Remove {', '.join(replaced_by_another)} first: it replaces this document.")
    manifest["documents"].remove(entry)
    _write_manifest(uploads_dir, manifest)
    (uploads_dir / entry["path"]).unlink(missing_ok=True)
