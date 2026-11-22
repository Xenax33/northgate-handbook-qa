"""HTML files, read with Python's built-in html.parser.

<title> and the first <h1> are the document title (the manifest has it) and are dropped. <h2>-<h6>
start sections. <p> and <li> become paragraphs and list items; <br> keeps its line break; <pre> keeps
its layout. Tables become Markdown tables, one row per line, so a cell stays next to its header (the
same reason as for Word tables, D8). Link text is kept; the link target is not.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

from handbook_qa.ingest.document import Section, read_text_file

BLOCKS = {"p", "li", "div", "dd", "dt", "pre", "blockquote", "ul", "ol", "dl", "section", "article"}
SKIP = {"title", "script", "style", "head"}
BREAK = "\x00"  # stands for <br> until the block is cleaned


def read(path: Path) -> list[Section]:
    return parse(read_text_file(path))


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
        self.list_marker_pending = False
        self.pre_depth = 0
        self.table: list[list[str]] | None = None  # rows of cell texts while inside a <table>
        self.cell: list[str] | None = None

    # tags ----------------------------------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in SKIP:
            self.skip_depth += 1
        elif self.table is not None:
            if tag == "tr":
                self.table.append([])
            elif tag in ("td", "th"):
                self.cell = []
            elif tag == "br" and self.cell is not None:
                self.cell.append(" ")
        elif tag == "table":
            self._end_block()
            self.table = []
        elif re.fullmatch(r"h[1-6]", tag):
            self._end_block()
            self.in_heading = int(tag[1])
        elif tag in BLOCKS:
            self._end_block()
            if tag == "li":
                self.list_marker_pending = True
            if tag == "pre":
                self.pre_depth += 1
        elif tag == "br":
            self.current.append(BREAK)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif self.table is not None:
            if tag in ("td", "th") and self.cell is not None:
                if not self.table:
                    self.table.append([])
                self.table[-1].append(_clean("".join(self.cell)).replace("|", "/"))
                self.cell = None
            elif tag == "table":
                self._emit(_markdown_table(self.table))
                self.table = None
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
            if tag == "li":
                self.list_marker_pending = False
            if tag == "pre":
                self.pre_depth = max(0, self.pre_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.table is not None:
            if self.cell is not None:
                self.cell.append(data)
        else:
            self.current.append(data)

    # building sections ----------------------------------------------------------------------------

    def _emit(self, text: str) -> None:
        if not text:
            return
        if self.list_marker_pending:
            text = "- " + text
            self.list_marker_pending = False
        self.paragraphs.append(text)

    def _end_block(self) -> None:
        raw = "".join(self.current)
        self.current.clear()
        if self.in_heading is not None:
            return
        if self.pre_depth:
            self._emit(raw.strip("\n").replace(BREAK, "\n"))
        else:
            self._emit("\n".join(filter(None, (_clean(part) for part in raw.split(BREAK)))))

    def _end_section(self) -> None:
        self._end_block()
        if self.paragraphs:
            self.sections.append(Section(self.heading, "\n".join(self.paragraphs)))
        self.paragraphs = []

    def finish(self) -> list[Section]:
        self._end_section()
        return self.sections


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _markdown_table(rows: list[list[str]]) -> str:
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows[1:]])
