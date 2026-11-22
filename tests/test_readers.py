"""Each reader on the real file it was written for, plus small made-up inputs for the edge cases."""

from pathlib import Path

import pytest

from handbook_qa.ingest import UnsupportedFormat, csv_table, html_page, pdf, read_sections, text


def headings(doc):
    return [section.heading for section in doc.sections]


def section(doc, heading):
    return next(s for s in doc.sections if s.heading == heading)


# Markdown and plain text ---------------------------------------------------------------------


def test_markdown_splits_at_headings_and_drops_front_matter_and_title(corpus):
    doc = corpus["hr-leave-policy-v1"]
    assert headings(doc) == [
        "1. Purpose", "2. Annual leave", "3. Sick leave", "4. Carry forward", "5. Company holidays", "6. Approval",
    ]
    assert "12 days of annual leave" in section(doc, "2. Annual leave").text
    assert "doc_id:" not in doc.text and "# Leave Policy v1" not in doc.text


def test_markdown_without_subheadings_is_one_section(corpus):
    doc = corpus["it-vpn-guide"]
    assert headings(doc) == [None]
    assert "2 concurrent VPN sessions" in doc.text


def test_markdown_table_rows_stay_together(corpus):
    objectives = section(corpus["eng-disaster-recovery"], "1. Objectives")
    assert "| Payments service | **4 hours** | 5 minutes |" in objectives.text


def test_text_parse_edge_cases():
    assert text.parse("") == []
    assert text.parse("---\ntitle: x\n---\n# Title\n") == []
    assert text.parse("no headings here") == [text.Section(None, "no headings here")]
    parsed = text.parse("# Title\nintro\n## A\none\n# Second H1\ntwo")
    assert [(s.heading, s.text) for s in parsed] == [(None, "intro"), ("A", "one"), ("Second H1", "two")]


def test_plain_text_file_is_one_section(corpus):
    doc = corpus["eng-sev-definitions"]
    assert len(doc.sections) == 1
    assert "SEV2  Major degradation" in doc.text


# PDF --------------------------------------------------------------------------------------------


def test_pdf_drops_title_and_metadata_even_when_supersedes_wraps(corpus):
    doc = corpus["hr-leave-policy-v2"]
    first = doc.sections[0]
    assert first.heading is None
    assert first.text.startswith("This version supersedes Leave Policy v1")
    assert "hr-leave-policy-v1\n" not in doc.text  # the wrapped "Supersedes:" value is gone too


def test_pdf_splits_at_numbered_headings(corpus):
    doc = corpus["hr-leave-policy-v2"]
    assert headings(doc) == [
        None, "1. Purpose", "2. Annual leave", "3. Sick leave", "4. Carry forward", "5. Approval", "6. Transition",
    ]
    assert "accrue 16 days of annual leave per calendar year" in section(doc, "2. Annual leave").text


def test_pdf_joins_wrapped_lines_into_sentences(corpus):
    text_ = section(corpus["eng-deploy-runbook-2023"], "1. When to deploy").text
    assert "A deploy freeze starts 36 hours before every scheduled release" in text_


def test_pdf_bullets_and_numbered_items_become_list_items(corpus):
    conduct = corpus["hr-code-of-conduct"].text
    assert "\n- Protect confidential information." in conduct
    preflight = section(corpus["eng-deploy-runbook-2023"], "2. Pre-flight").text
    assert preflight.splitlines() == [
        "1) The change has one approving review and a green CI pipeline.",
        "2) The deployer posts the change summary in #deploys.",
    ]


def test_pdf_parse_edge_cases():
    assert pdf.parse("") == []
    raw = "Title\nDocument ID: x | Status: current\n\x7f\nfirst bullet that\nwraps.\n1. Heading\nBody line"
    parsed = pdf.parse(raw)
    assert [(s.heading, s.text) for s in parsed] == [(None, "- first bullet that wraps."), ("1. Heading", "Body line")]


# Word -------------------------------------------------------------------------------------------


def test_word_table_keeps_tier_next_to_its_price(corpus):
    hotels = section(corpus["hr-travel-policy"], "4. Limits > 4.2 Hotels and daily spending limits")
    assert "| City tier | Maximum room rate per night |" in hotels.text
    assert "| Tier 1 | $275 |" in hotels.text
    assert "| Tier 2 | $200 |" in hotels.text
    # the table sits between the sentences around it, in document order
    assert hotels.text.index("capped per night") < hotels.text.index("| Tier 1") < hotels.text.index("Per-Diem Table")


def test_word_headings_carry_their_parent(corpus):
    assert headings(corpus["hr-travel-policy"]) == [
        "1. Scope", "2. Booking", "3. City tiers",
        "4. Limits > 4.1 Flights", "4. Limits > 4.2 Hotels and daily spending limits", "4. Limits > 4.3 Ground transport",
        "5. International travel", "6. Insurance",
    ]


def test_word_bullets_become_list_items(corpus):
    tiers = section(corpus["hr-travel-policy"], "3. City tiers").text
    assert "- Tier 3: Omaha, Tulsa, Boise, Albuquerque, Des Moines and any city not listed above" in tiers


def test_word_without_headings_drops_title_and_metadata(corpus):
    doc = corpus["it-data-retention"]
    assert headings(doc) == [None]
    assert doc.text.startswith("Application logs are retained for 365 days")


# CSV --------------------------------------------------------------------------------------------


def test_csv_rows_become_self_contained_lines(corpus):
    lines = corpus["fin-per-diem-table"].text.splitlines()
    assert len(lines) == 15
    assert "grade: L3, city_tier: 2, example_cities: Chicago; Seattle; Los Angeles; Washington DC, per_diem_usd: 75" in lines


def test_csv_parse_edge_cases():
    assert csv_table.parse("") == []
    assert csv_table.parse("a,b\n") == []
    assert csv_table.parse("a,b\n1,\n,\n")[0].text == "a: 1, b: "


# HTML -------------------------------------------------------------------------------------------


def test_html_splits_at_h2_and_drops_title(corpus):
    doc = corpus["support-escalation"]
    assert headings(doc) == [None, "Status page", "Customer credits"]
    assert "Only the Support lead and the incident commander may publish" in section(doc, "Status page").text
    assert "Customer Support Escalation" not in doc.text


def test_html_list_items_and_link_text(corpus):
    sections_ = section(corpus["ref-handbook-index"], "Sections").text
    assert "- Leave Policy v2 (current) and Leave Policy v1 (superseded)" in sections_


def test_html_parse_edge_cases():
    assert html_page.parse("") == []
    parsed = html_page.parse("<h1>T</h1><p>a <b>bold</b>\n word</p><h2>H</h2><ul><li>x</li></ul><script>no()</script>")
    assert [(s.heading, s.text) for s in parsed] == [(None, "a bold word"), ("H", "- x")]


# Dispatch ---------------------------------------------------------------------------------------


def test_unsupported_format_is_refused_with_a_clear_message(tmp_path: Path):
    file = tmp_path / "notes.rtf"
    file.write_text("x")
    with pytest.raises(UnsupportedFormat, match="unsupported file type"):
        read_sections(file)
