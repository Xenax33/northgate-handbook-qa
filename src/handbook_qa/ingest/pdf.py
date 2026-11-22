"""PDF files, read with pypdf (decision D8: pdfplumber and markitdown leaked "(cid:127)" junk).

What pypdf gives us for these handbook PDFs, and what we do about it:
- Line 1 is the title, line 2 a "Document ID: ... | Status: ..." metadata line (sometimes wrapping
  onto a third line after "Supersedes:"). Both repeat the manifest, so they are dropped.
- Section headings are lines like "2. Annual leave". They start new sections.
- Bullets come out as a lone DEL character (\x7f) on its own line; numbered list items as a lone
  number on its own line. Both are turned back into list items.
- Long lines are wrapped at the page width. Wrapped lines are joined back into paragraphs.
"""

import re
from pathlib import Path

from pypdf import PdfReader

from handbook_qa.ingest.document import Section

HEADING = re.compile(r"^\d+\.\s+[A-Z][^.]*$")
BULLET = "\x7f"
LIST_NUMBER = re.compile(r"^\d+$")
ENDS_SENTENCE = (".", ":", ";", "!", "?")


def read(path: Path) -> list[Section]:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return parse(text)


def parse(text: str) -> list[Section]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    lines = drop_title_and_metadata(lines)

    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        paragraphs = join_wrapped_lines(body)
        if paragraphs:
            sections.append(Section(heading, "\n".join(paragraphs)))
        body.clear()

    for line in lines:
        if HEADING.match(line):
            flush()
            heading = line
        else:
            body.append(line)
    flush()
    return sections


def drop_title_and_metadata(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if line.startswith("Document ID:"):
            end = index + 1
            if line.rstrip().endswith("Supersedes:") and end < len(lines):
                end += 1  # the superseded doc_id wrapped onto the next line
            return lines[end:]
    return lines


def join_wrapped_lines(lines: list[str]) -> list[str]:
    """Turn page-width lines back into paragraphs and list items."""
    paragraphs: list[str] = []
    marker: str | None = None  # "- " or "3. " waiting for the text that follows it
    for line in lines:
        if not line:
            continue
        if line == BULLET:
            marker = "- "
            continue
        if LIST_NUMBER.match(line):
            marker = f"{line}) "
            continue
        if marker:
            paragraphs.append(marker + line)
            marker = None
        elif paragraphs and not paragraphs[-1].endswith(ENDS_SENTENCE):
            paragraphs[-1] += " " + line
        else:
            paragraphs.append(line)
    return paragraphs
