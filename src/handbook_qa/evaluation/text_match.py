"""The matching rule from eval/README.md, in one place so the eval and the tests can't drift apart.

- Case-insensitive.
- Whitespace and Markdown emphasis (`**bold**`, `*italic*`, backticks) are ignored, so
  "accrue 12 days" matches the Markdown "accrue **12 days**".
- A number must not touch other digits: "16" matches "16 days" and "16-day" but not "160", and
  "500" does not match inside "$2,500" or "500,000" (thousands separators count as part of a number).
- A number and the word after it match whether written with a space or a hyphen, singular or plural:
  "45 minutes" matches "a 45-minute window", "16 days" matches "a 16-day limit". (Added after eval
  run 1, where a correct "within the 45-minute window" was marked wrong.)
"""

import re

_EMPHASIS = re.compile(r"(\*\*|__|\*|`)")
_NUMBER_WORD = re.compile(r"(\d)[ -]([a-z]+)")


def normalise(text: str) -> str:
    text = _EMPHASIS.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _fold_number_words(text: str) -> str:
    """'45-minute' and '45 minutes' both become '45 minute' (applied to text and term alike)."""
    def fold(match: re.Match) -> str:
        word = match.group(2)
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        return f"{match.group(1)} {word}"

    return _NUMBER_WORD.sub(fold, text)


def contains(text: str, term: str) -> bool:
    term = _fold_number_words(normalise(term))
    if not term:
        return False
    pattern = re.escape(term)
    if term[0].isdigit():
        pattern = r"(?<!\d)(?<!\d[,.])" + pattern
    if term[-1].isdigit():
        pattern += r"(?!\d)(?![,.]\d)"
    return re.search(pattern, _fold_number_words(normalise(text))) is not None
