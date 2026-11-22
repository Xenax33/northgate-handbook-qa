"""The shapes every reader produces: a document made of sections."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class State(StrEnum):
    """Whether a document applies today. Worked out from the manifest, not taken from its status field."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    NOT_YET_IN_FORCE = "not yet in force"


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
