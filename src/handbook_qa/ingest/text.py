"""Markdown and plain-text files.

Markdown files start with YAML front matter (the same metadata as the manifest), which is dropped.
The first line, if it is a level-1 heading, is the document title, which the manifest already gives
us, so it is dropped too. Every other heading starts a new section. Lines inside fenced code blocks
are never headings. Plain-text (.txt) files have no heading syntax: they come out as one section,
so a line like "# 1 Budget review" in meeting notes is kept as text.
"""

import re
from pathlib import Path

from handbook_qa.ingest.document import Section, read_text_file

FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")  # "## Using C#" keeps its "#"
FENCE = re.compile(r"^\s*(```|~~~)")


def read(path: Path) -> list[Section]:
    text = read_text_file(path)
    if path.suffix.lower() == ".txt":
        body = text.replace("\r\n", "\n").strip()
        return [Section(None, body)] if body else []
    return parse(text)


def parse(text: str) -> list[Section]:
    text = FRONT_MATTER.sub("", text.replace("\r\n", "\n"), count=1)
    sections: list[Section] = []
    heading: str | None = None
    lines: list[str] = []
    in_fence = False
    first_line = True

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            sections.append(Section(heading, body))
        lines.clear()

    for line in text.split("\n"):
        is_first, first_line = first_line and bool(line.strip()), first_line and not line.strip()
        if FENCE.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue
        match = None if in_fence else HEADING.match(line)
        if not match:
            lines.append(line)
            continue
        level, name = len(match.group(1)), match.group(2)
        if level == 1 and is_first:
            continue  # the title line; the manifest has the title
        flush()
        heading = name
    flush()
    return sections
