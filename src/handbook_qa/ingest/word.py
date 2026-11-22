"""Word (.docx) files, read with python-docx.

Paragraph styles tell us the structure: "Title" (dropped, the manifest has it), "Heading 1/2/..."
(start a section), "List Bullet" (a list item). The "Document ID: ..." metadata paragraph repeats the
manifest and is dropped. Tables are kept in document order as Markdown tables, so the hotel cap
"Tier 1 | $275" stays on one row with its header (D8).

A heading's section name includes its parent heading, e.g. "4. Limits > 4.2 Hotels and daily spending
limits", because "4.2 Hotels..." alone loses the context that it is a limit.
"""

from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from handbook_qa.ingest.document import Section


def read(path: Path) -> list[Section]:
    document = docx.Document(str(path))
    sections: list[Section] = []
    heading_path: list[str] = []
    body: list[str] = []

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            sections.append(Section(" > ".join(heading_path) or None, text))
        body.clear()

    for block in document.iter_inner_content():
        if isinstance(block, Table):
            body.append(table_to_markdown(block))
            continue
        assert isinstance(block, Paragraph)
        text = block.text.strip()
        style = block.style.name if block.style is not None else ""
        if not text or style == "Title" or text.startswith("Document ID:"):
            continue
        level = heading_level(style)
        if level:
            flush()
            heading_path[:] = heading_path[: level - 1] + [text]
        elif style.startswith("List"):
            body.append("- " + text)
        else:
            body.append(text)
    flush()
    return sections


def heading_level(style: str) -> int:
    """'Heading 2' -> 2; anything else -> 0."""
    if style.startswith("Heading"):
        digits = style.removeprefix("Heading").strip()
        return int(digits) if digits.isdigit() else 1
    return 0


def table_to_markdown(table: Table) -> str:
    rows = [[cell.text.strip().replace("|", "/") for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)
