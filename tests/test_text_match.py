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


def test_number_and_word_match_with_space_or_hyphen_singular_or_plural():
    assert contains("you are within the 45-minute window", "45 minutes")  # eval run 1, multi-06
    assert contains("a 16-day limit", "16 days")
    assert contains("26 weeks fully paid", "26 weeks")
    assert contains("one 24 hour report", "24 hours")
    assert not contains("within the 45-minute window", "44 minutes")
    assert not contains("a 145-minute window", "45 minutes")
    assert contains("2 days per week", "2 days") and not contains("2 days per week", "2 weeks")


def test_empty_term_never_matches():
    assert not contains("anything", "")
    assert not contains("anything", "**")
