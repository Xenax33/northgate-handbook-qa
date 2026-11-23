"""Check every citation the model gives (D15): the passage key must be one we sent, and the quote
must really appear in that passage. Case, whitespace and Markdown emphasis are ignored; a quote the
model shortened with "..." counts if each part appears, in order."""

import re
from dataclasses import dataclass

from handbook_qa.answer.context import ContextPassage
from handbook_qa.evaluation.text_match import normalise
from handbook_qa.passages import Passage

# Parts of a quote: split at "..." and at line breaks. Each part must appear in the passage, in order.
# Line breaks were added after eval run 5: the model quoted three separate org-chart rows as one
# multi-line quote (rows 1, 3 and 4), which is the same as shortening with "...".
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\n)\s*")


@dataclass(frozen=True)
class Citation:
    key: str
    quote: str
    passage: Passage | None  # None when the model cited a key we never sent
    verified: bool
    problem: str | None = None


def check_citations(raw: list[dict], context: list[ContextPassage]) -> list[Citation]:
    by_key = {item.key: item.passage for item in context}
    checked = []
    for item in raw:
        key = str(item.get("passage", "")).strip().strip("<>[]")
        quote = str(item.get("quote", "")).strip().strip("\"'“”")
        passage = by_key.get(key)
        if passage is None:
            checked.append(Citation(key, quote, None, False, "the model cited a passage it was not given"))
        elif not quote:
            checked.append(Citation(key, quote, passage, False, "no quote given"))
        elif quote_in(quote, passage.text):
            checked.append(Citation(key, quote, passage, True))
        else:
            checked.append(Citation(key, quote, passage, False, "quote not found in the passage"))
    return checked


def quote_in(quote: str, text: str) -> bool:
    haystack = normalise(text)
    position = 0
    for part in (p for p in ELLIPSIS.split(quote) if p.strip()):
        found = haystack.find(normalise(part).rstrip("."), position)
        if found < 0:
            return False
        position = found + 1
    return position > 0
