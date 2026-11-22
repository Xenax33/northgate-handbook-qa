"""Turn documents into passages: the pieces that search finds and the employee sees as a source (D10).

A passage is one section of a document. Each carries a label with its document title, section
heading, state and effective date, so even a passage read on its own says "this is the old version".
A section longer than MAX_CHARS (only possible for a long document without headings, e.g. an upload)
is cut at paragraph breaks into pieces of at most MAX_CHARS.
"""

import re
from dataclasses import dataclass
from datetime import date

from handbook_qa.ingest import Document, State

MAX_CHARS = 1600  # about 400 tokens; the longest section in the handbook today is 1,496 characters


@dataclass(frozen=True)
class Passage:
    id: str  # "<doc_id>#<n>", stable as long as the document doesn't change
    doc_id: str
    title: str
    heading: str | None
    text: str
    state: State
    effective_date: date
    superseded_by: str | None = None

    @property
    def label(self) -> str:
        where = f"{self.title} > {self.heading}" if self.heading else self.title
        state = self.state.value.upper()
        if self.state == State.SUPERSEDED and self.superseded_by:
            state += f" by {self.superseded_by}"
        if self.state == State.NOT_YET_IN_FORCE:
            state += f", from {self.effective_date.isoformat()}"
        return f"[{where} | {state} | effective {self.effective_date.isoformat()}]"

    @property
    def search_text(self) -> str:
        """What search indexes: title and heading help both keyword and meaning search."""
        where = f"{self.title} > {self.heading}" if self.heading else self.title
        return f"{where}\n{self.text}"


def build_passages(documents: list[Document]) -> list[Passage]:
    passages = []
    for doc in documents:
        number = 0
        for section in doc.sections:
            for piece in split_long(section.text):
                number += 1
                passages.append(
                    Passage(
                        id=f"{doc.doc_id}#{number}",
                        doc_id=doc.doc_id,
                        title=doc.title,
                        heading=section.heading,
                        text=piece,
                        state=doc.state,
                        effective_date=doc.effective_date,
                        superseded_by=doc.superseded_by,
                    )
                )
    return passages


def split_long(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Keep text whole if it fits; otherwise cut at line breaks. A single line that is itself too
    long (readers join each paragraph into one line) is cut between sentences, or between words."""
    if len(text) <= max_chars:
        return [text]
    lines = [piece for line in text.split("\n") for piece in _split_line(line, max_chars)]
    pieces, current = [], ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if current and len(candidate) > max_chars:
            pieces.append(current.strip())
            current = line
        else:
            current = candidate
    if current.strip():
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def _split_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    units = re.split(r"(?<=[.!?])\s+", line)  # sentences
    if any(len(unit) > max_chars for unit in units):
        units = line.split(" ")  # a sentence that is still too long: fall back to words
    out, current = [], ""
    for unit in units:
        while len(unit) > max_chars:  # a single "word" longer than the limit (e.g. a URL)
            if current:
                out.append(current)
                current = ""
            out.append(unit[:max_chars])
            unit = unit[max_chars:]
        candidate = f"{current} {unit}" if current else unit
        if len(candidate) > max_chars:
            out.append(current)
            current = unit
        else:
            current = candidate
    if current:
        out.append(current)
    return out
