"""Read the handbook: every file listed in the manifest, one reader per format (decisions D8, D9)."""

from datetime import date
from pathlib import Path

from handbook_qa.ingest import csv_table, html_page, pdf, text, word
from handbook_qa.ingest.document import Document, Section, State
from handbook_qa.ingest.manifest import ManifestError, document_states, read_manifest

READERS = {
    ".md": text.read,
    ".txt": text.read,
    ".pdf": pdf.read,
    ".docx": word.read,
    ".csv": csv_table.read,
    ".html": html_page.read,
}
SUPPORTED_FORMATS = tuple(sorted(suffix.lstrip(".") for suffix in READERS))


class UnsupportedFormat(ValueError):
    pass


def read_sections(path: Path) -> list[Section]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise UnsupportedFormat(f"{path.name}: unsupported file type; supported: {', '.join(SUPPORTED_FORMATS)}")
    return reader(path)


def load_corpus(corpus_dir: Path, today: date) -> list[Document]:
    """Read manifest.json and every document it lists, with each document's state on `today`."""
    entries = read_manifest(corpus_dir / "manifest.json")
    states = document_states(entries, today)
    documents = []
    for entry in entries:
        file = corpus_dir / entry.path
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
            )
        )
    return documents


__all__ = ["Document", "Section", "State", "ManifestError", "UnsupportedFormat", "load_corpus", "read_sections", "SUPPORTED_FORMATS"]
