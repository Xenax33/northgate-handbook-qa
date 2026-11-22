"""PDF files, read with pypdf (decision D8: pdfplumber and markitdown leaked "(cid:127)" junk).

What pypdf gives us for these handbook PDFs, and what we do about it:
- Line 1 is the title, line 2 a "Document ID: ... | Status: ..." metadata line (sometimes wrapping
  onto a third line after "Supersedes:"). Both repeat the manifest, so they are dropped.
- Section headings are short lines like "2. Annual leave", "4.2 Hotels" or "2. U.S. travel". A line
  only counts as a heading if the line before it finished a sentence, so a wrapped line that happens
  to start with a number ("2025. The old rate...") is not mistaken for one.
- Bullets come out as a lone DEL character (\x7f) on its own line; numbered list items as a lone
  number on its own line. Both are turned back into list items.
- A lone number as the last line of a page is a page number and is dropped.
- Long lines are wrapped at the page width. Wrapped lines are joined back into paragraphs.

Known limit: a bullet whose text has no closing punctuation absorbs the next line, because nothing
in pypdf's output says where the bullet ends. None of the handbook's PDFs has such a bullet.
"""

import re
from pathlib import Path

from pypdf import PdfReader

from handbook_qa.ingest.document import Section

HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z]\S*(\s+\S+){0,8}$")
BULLET = "\x7f"
LIST_NUMBER = re.compile(r"^\d+$")
ENDS_SENTENCE = (".", ":", ";", "!", "?")


def read(path: Path) -> list[Section]:
    reader = PdfReader(path)
    pages = [drop_page_number(page.extract_text() or "") for page in reader.pages]
    return parse("\n".join(pages))


def drop_page_number(page_text: str) -> str:
    lines = page_text.rstrip().split("\n")
    if len(lines) > 1 and LIST_NUMBER.match(lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines)


def is_heading(line: str, previous: str | None) -> bool:
    if not HEADING.match(line) or line.endswith(ENDS_SENTENCE):
        return False
    return previous is None or previous == "" or previous.endswith(ENDS_SENTENCE) or bool(HEADING.match(previous))


def parse(text: str) -> list[Section]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    lines = drop_title_and_metadata(lines)

    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []
    previous: str | None = None

    def flush() -> None:
        paragraphs = join_wrapped_lines(body)
        if paragraphs:
            sections.append(Section(heading, "\n".join(paragraphs)))
        body.clear()

    for line in lines:
        if is_heading(line, previous):
            flush()
            heading = line
        else:
            body.append(line)
        if line and line != BULLET and not LIST_NUMBER.match(line):
            previous = line
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
    marker: str | None = None  # "- " or "3) " waiting for the text that follows it
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
