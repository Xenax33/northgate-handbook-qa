"""The eval's text-matching rule (eval/README.md). A wrong rule silently passes or fails answers."""

from handbook_qa.evaluation.text_match import contains


def test_case_and_whitespace_are_ignored():
    assert contains("Full-time employees accrue\n  16 days", "accrue 16 DAYS")


def test_markdown_emphasis_is_ignored():
    assert contains("accrue **12 days of annual leave** per year", "accrue 12 days of annual leave")
    assert contains("the `x-request-id` header", "x-request-id header")


def test_numbers_must_stand_alone():
    assert contains("16 days", "16")
    assert contains("a 16-day limit", "16")
    assert contains("costs $500 per week.", "500")
    assert not contains("160 days", "16")
    assert not contains("claims above $2,500", "500")
    assert not contains("16,000 robots", "16")


def test_empty_term_never_matches():
    assert not contains("anything", "")
    assert not contains("anything", "**")
