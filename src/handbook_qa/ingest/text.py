"""Markdown and plain-text files.

Markdown files start with YAML front matter (the same metadata as the manifest), which is dropped.
The first level-1 heading is the document title, which the manifest already gives us, so it is
dropped too. Every other heading starts a new section. Plain-text files have no headings and
come out as one section.
"""

import re
from pathlib import Path

from handbook_qa.ingest.document import Section

FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def read(path: Path) -> list[Section]:
    return parse(path.read_text(encoding="utf-8-sig"))


def parse(text: str) -> list[Section]:
    text = FRONT_MATTER.sub("", text.replace("\r\n", "\n"), count=1)
    sections: list[Section] = []
    heading: str | None = None
    lines: list[str] = []
    title_seen = False

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            sections.append(Section(heading, body))
        lines.clear()

    for line in text.split("\n"):
        match = HEADING.match(line)
        if not match:
            lines.append(line)
            continue
        level, name = len(match.group(1)), match.group(2)
        if level == 1 and not title_seen:
            title_seen = True
            continue
        flush()
        heading = name
    flush()
    return sections
