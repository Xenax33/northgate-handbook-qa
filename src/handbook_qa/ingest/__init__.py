"""Read the handbook: every file listed in the manifest, one reader per format (decisions D8, D9),
plus any uploaded documents (D24), which follow the same rules."""

from datetime import date
from pathlib import Path

from handbook_qa.ingest import csv_table, html_page, pdf, text, word
from handbook_qa.ingest.document import Document, ReaderError, Section, State
from handbook_qa.ingest.manifest import ManifestEntry, ManifestError, check_references, document_states, read_manifest

READERS = {
    ".md": text.read,
    ".txt": text.read,
    ".pdf": pdf.read,
    ".docx": word.read,
    ".csv": csv_table.read,
    ".html": html_page.read,
}
SUPPORTED_FORMATS = tuple(sorted(suffix.lstrip(".") for suffix in READERS))
UPLOADS_MANIFEST = "uploads.json"


class UnsupportedFormat(ValueError):
    pass


def read_sections(path: Path) -> list[Section]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise UnsupportedFormat(f"{path.name}: unsupported file type; supported: {', '.join(SUPPORTED_FORMATS)}")
    try:
        return reader(path)
    except ReaderError:
        raise
    except Exception as error:  # pypdf / python-docx errors on a damaged file
        raise ReaderError(f"{path.name}: could not be read ({type(error).__name__}: {error})") from error


def load_corpus(corpus_dir: Path, today: date, uploads_dir: Path | None = None) -> list[Document]:
    """Read manifest.json and every document it lists, plus uploads (if a folder is given), with each
    document's state on `today`. Uploads may replace handbook documents, so states are worked out over both."""
    sources: list[tuple[ManifestEntry, Path, str]] = [(e, corpus_dir, "handbook") for e in read_manifest(corpus_dir / "manifest.json")]
    if uploads_dir is not None and (uploads_dir / UPLOADS_MANIFEST).is_file():
        sources += [(e, uploads_dir, "upload") for e in read_manifest(uploads_dir / UPLOADS_MANIFEST, check=False)]
    entries = [entry for entry, _, _ in sources]
    check_references(entries)
    states = document_states(entries, today)
    documents = []
    for entry, folder, source in sources:
        file = folder / entry.path
        if not file.is_file():
            raise ManifestError(f"{entry.doc_id}: file {entry.path} listed in the manifest does not exist")
        state, superseded_by = states[entry.doc_id]
        documents.append(
            Document(
                doc_id=entry.doc_id,
                title=entry.title,
                path=entry.path,
                format=file.suffix.lower().lstrip("."),
                category=entry.category,
                owner=entry.owner,
                effective_date=entry.effective_date,
                state=state,
                superseded_by=superseded_by,
                supersedes=entry.supersedes,
                sections=read_sections(file),
                source=source,
            )
        )
    return documents


__all__ = ["Document", "Section", "State", "ManifestError", "ReaderError", "UnsupportedFormat", "load_corpus",
           "read_sections", "SUPPORTED_FORMATS", "UPLOADS_MANIFEST"]
