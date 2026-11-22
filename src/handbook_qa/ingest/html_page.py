"""HTML files, read with Python's built-in html.parser.

<title> and the first <h1> are the document title (the manifest has it) and are dropped. <h2>-<h6>
start sections. <p> and <li> become paragraphs and list items. Link text is kept; the link target is not.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

from handbook_qa.ingest.document import Section

BLOCKS = {"p", "li", "div", "td", "th", "dd", "dt", "pre", "blockquote"}
SKIP = {"title", "script", "style", "head"}


def read(path: Path) -> list[Section]:
    return parse(path.read_text(encoding="utf-8-sig"))


def parse(html: str) -> list[Section]:
    parser = _SectionParser()
    parser.feed(html)
    parser.close()
    return parser.finish()


class _SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[Section] = []
        self.heading: str | None = None
        self.paragraphs: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.in_heading: int | None = None
        self.title_seen = False
        self.in_list_item = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in SKIP:
            self.skip_depth += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._end_block()
            self.in_heading = int(tag[1])
        elif tag in BLOCKS:
            self._end_block()
            self.in_list_item = tag == "li"
        elif tag == "br":
            self.current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif re.fullmatch(r"h[1-6]", tag) and self.in_heading:
            text = _clean("".join(self.current))
            self.current.clear()
            if self.in_heading == 1 and not self.title_seen:
                self.title_seen = True
            elif text:
                self._end_section()
                self.heading = text
            self.in_heading = None
        elif tag in BLOCKS:
            self._end_block()

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.current.append(data)

    def _end_block(self) -> None:
        text = _clean("".join(self.current))
        self.current.clear()
        if text and self.in_heading is None:
            self.paragraphs.append(("- " if self.in_list_item else "") + text)
        self.in_list_item = False

    def _end_section(self) -> None:
        self._end_block()
        if self.paragraphs:
            self.sections.append(Section(self.heading, "\n".join(self.paragraphs)))
        self.paragraphs = []

    def finish(self) -> list[Section]:
        self._end_section()
        return self.sections


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", " ", text)).strip()
