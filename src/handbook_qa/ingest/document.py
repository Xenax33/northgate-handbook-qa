"""The shapes every reader produces: a document made of sections."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path


class State(StrEnum):
    """Whether a document applies today. Worked out from the manifest, not taken from its status field."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    NOT_YET_IN_FORCE = "not yet in force"


class ReaderError(ValueError):
    """A file can't be read the way its format promises (e.g. a CSV row with too many values)."""


@dataclass(frozen=True)
class Section:
    """One part of a document, usually what sits under one heading.

    `heading` is None for text before the first heading, or for documents that have no headings.
    """

    heading: str | None
    text: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    path: str
    format: str
    category: str
    owner: str
    effective_date: date
    state: State
    superseded_by: str | None = None
    supersedes: str | None = None
    sections: list[Section] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The whole document as one string, headings included."""
        parts = []
        for section in self.sections:
            parts.append(f"{section.heading}\n{section.text}" if section.heading else section.text)
        return "\n\n".join(parts)


def read_text_file(path: Path) -> str:
    """UTF-8 (with or without a byte-order mark), falling back to Windows-1252 for older files."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError as error:
            raise ReaderError(f"{path.name}: not UTF-8 or Windows-1252 text") from error
