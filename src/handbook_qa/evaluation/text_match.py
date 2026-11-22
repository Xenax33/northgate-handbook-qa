"""The matching rule from eval/README.md, in one place so the eval and the tests can't drift apart.

- Case-insensitive.
- Whitespace and Markdown emphasis (`**bold**`, `_italic_`, backticks) are ignored, so
  "accrue 12 days" matches the Markdown "accrue **12 days**".
- A number must not touch other digits: "16" matches "16 days" and "16-day" but not "160", and
  "500" does not match inside "$2,500" or "500,000" (thousands separators count as part of a number).
"""

import re

_EMPHASIS = re.compile(r"(\*\*|__|\*|`)")


def normalise(text: str) -> str:
    text = _EMPHASIS.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def contains(text: str, term: str) -> bool:
    term = normalise(term)
    if not term:
        return False
    pattern = re.escape(term)
    if term[0].isdigit():
        pattern = r"(?<!\d)(?<!\d[,.])" + pattern
    if term[-1].isdigit():
        pattern += r"(?!\d)(?![,.]\d)"
    return re.search(pattern, normalise(text)) is not None
