"""Inputs the real handbook doesn't contain but an upload easily could. Each case came from the
independent code review (decision log, QA 2026-11-23) and failed before the fix."""

import json
from datetime import date

import docx
import pytest

from handbook_qa.ingest import ReaderError, State, csv_table, html_page, pdf, read_sections, text
from handbook_qa.ingest.manifest import ManifestEntry, ManifestError, document_states, read_manifest
from handbook_qa.passages import split_long


def pairs(sections):
    return [(s.heading, s.text) for s in sections]


# Markdown / text ------------------------------------------------------------------------------


def test_hash_lines_inside_code_fences_are_not_headings():
    parsed = text.parse("# Title\nSetup:\n```bash\n# install deps\npip install x\n```\nDone.")
    assert len(parsed) == 1 and "# install deps" in parsed[0].text


def test_closing_hashes_are_stripped_but_a_hash_in_the_name_is_kept():
    assert [s.heading for s in text.parse("## Using C#\nx\n## Setup ##\ny")] == ["Using C#", "Setup"]


def test_only_an_h1_on_the_first_line_counts_as_the_title():
    parsed = text.parse("Intro line\n# Real section\nbody")
    assert pairs(parsed) == [(None, "Intro line"), ("Real section", "body")]


def test_txt_files_keep_hash_lines_as_text(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("Agenda\n# 1 Budget review\nApproved.", encoding="utf-8")
    assert pairs(read_sections(notes)) == [(None, "Agenda\n# 1 Budget review\nApproved.")]


def test_bom_and_windows_1252_files_are_read(tmp_path):
    bom = tmp_path / "bom.md"
    bom.write_bytes("﻿# T\n## A\ncafé".encode("utf-8"))
    assert pairs(read_sections(bom)) == [("A", "café")]
    old = tmp_path / "old.md"
    old.write_bytes("## A\n’quoted’ café".encode("cp1252"))
    assert read_sections(old)[0].text == "’quoted’ café"


# CSV ------------------------------------------------------------------------------------------


def test_csv_row_with_an_unquoted_comma_is_refused_not_shifted():
    with pytest.raises(ReaderError, match="row 2: 5 values but 4 columns"):
        csv_table.parse("grade,tier,cities,usd\nL3,2,Chicago, Seattle,75\n")


def test_csv_quoted_commas_are_fine():
    assert csv_table.parse('grade,cities\nL3,"Chicago, Seattle"\n')[0].text == "grade: L3, cities: Chicago, Seattle"


@pytest.mark.parametrize("header, message", [("a,,b", "has no name"), ("a,a,b", "repeated")])
def test_csv_blank_or_repeated_column_names_are_refused(header, message):
    with pytest.raises(ReaderError, match=message):
        csv_table.parse(f"{header}\n1,2,3\n")


def test_csv_short_rows_are_padded():
    assert csv_table.parse("a,b,c\n1\n")[0].text == "a: 1, b: , c: "


# PDF ------------------------------------------------------------------------------------------


def test_pdf_wrapped_line_starting_with_a_year_is_not_a_heading():
    parsed = pdf.parse("Document ID: x\nThe new rate applies from 1 April\n2025. The old rate applies before that.")
    assert pairs(parsed) == [(None, "The new rate applies from 1 April 2025. The old rate applies before that.")]


def test_pdf_headings_with_inner_periods_and_subsection_numbers():
    parsed = pdf.parse("Document ID: x\nIntro.\n2. U.S. travel\nBody.\n4.2 Hotels\nCaps.")
    assert [s.heading for s in parsed] == [None, "2. U.S. travel", "4.2 Hotels"]


def test_pdf_page_number_at_the_bottom_of_a_page_is_dropped():
    assert pdf.drop_page_number("Text on page one.\n3") == "Text on page one."
    assert pdf.drop_page_number("Step\n2") == "Step"
    assert pdf.drop_page_number("7") == "7"  # a page that is only a number is left alone


# HTML -----------------------------------------------------------------------------------------


def test_html_tables_keep_cells_on_their_row():
    html = "<h2>Credits</h2><table><tr><th>Severity</th><th>Credit</th></tr><tr><td>SEV1</td><td>10%</td></tr></table>"
    assert pairs(html_page.parse(html)) == [("Credits", "| Severity | Credit |\n| --- | --- |\n| SEV1 | 10% |")]


def test_html_br_and_pre_keep_line_breaks():
    parsed = html_page.parse("<p>Line one<br>Line two</p><pre>a  b\n  c</pre>")
    assert parsed[0].text == "Line one\nLine two\na  b\n  c"


def test_html_list_item_with_paragraph_keeps_its_marker():
    assert html_page.parse("<ul><li><p>first</p></li><li>second</li></ul>")[0].text == "- first\n- second"


# Word -----------------------------------------------------------------------------------------


def test_word_numbered_lists_merged_cells_and_multi_paragraph_cells(tmp_path):
    document = docx.Document()
    document.add_heading("Steps", level=1)
    document.add_paragraph("Open the portal", style="List Number")
    document.add_paragraph("Submit the form", style="List Number")
    table = document.add_table(rows=2, cols=3)
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.text = "Merged header"
    table.cell(0, 2).text = "Other"
    table.cell(1, 0).text = "a"
    table.cell(1, 1).text = "b"
    cell = table.cell(1, 2)
    cell.text = "first paragraph"
    cell.add_paragraph("second paragraph")
    path = tmp_path / "steps.docx"
    document.save(path)

    section = read_sections(path)[0]
    assert section.heading == "Steps"
    assert section.text.splitlines() == [
        "1) Open the portal",
        "2) Submit the form",
        "| Merged header |  | Other |",  # "Other" stays above its own column
        "| --- | --- | --- |",
        "| a | b | first paragraph second paragraph |",
    ]


# Manifest -------------------------------------------------------------------------------------


def entry(doc_id, effective, status="current", supersedes=None):
    return ManifestEntry(doc_id, f"{doc_id}.md", doc_id, "HR", "P", date.fromisoformat(effective), status, supersedes)


def test_manifest_with_a_bom_and_mixed_case_status(tmp_path):
    path = tmp_path / "manifest.json"
    item = {"doc_id": "a", "path": "a.md", "title": "A", "category": "HR", "owner": "P",
            "effective_date": "2024-01-01", "status": "Deprecated"}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"documents": [item]}).encode())
    entries = read_manifest(path)
    assert document_states(entries, date(2026, 1, 1)) == {"a": (State.DEPRECATED, None)}


def test_invalid_manifest_json_gives_a_clear_error(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        read_manifest(path)


def test_a_deprecated_replacement_does_not_retire_the_old_version():
    entries = [entry("v1", "2023-01-01"), entry("v2", "2025-01-01", status="deprecated", supersedes="v1")]
    assert document_states(entries, date(2026, 1, 1))["v1"] == (State.CURRENT, None)


def test_when_two_documents_supersede_the_same_one_the_latest_is_named():
    entries = [entry("v1", "2020-01-01"), entry("v3", "2024-01-01", supersedes="v1"), entry("v2", "2022-01-01", supersedes="v1")]
    assert document_states(entries, date(2026, 1, 1))["v1"] == (State.SUPERSEDED, "v3")


def test_from_2027_both_parental_leave_documents_apply(corpus):
    """Intended: the 2027 revision only covers births from 2027-01-01 and keeps the 2024 policy's other
    terms, so it doesn't declare `supersedes`, and both stay current (and searchable) from that date."""
    from conftest import CORPUS
    from handbook_qa.ingest import load_corpus

    states = {d.doc_id: d.state for d in load_corpus(CORPUS, date(2027, 1, 1))}
    assert states["hr-parental-leave-policy"] == states["hr-parental-leave-policy-2027"] == State.CURRENT


# Passages -------------------------------------------------------------------------------------


def test_a_single_long_line_is_cut_between_sentences():
    line = " ".join(f"Sentence number {n} says something useful about the policy." for n in range(60))
    pieces = split_long(line, max_chars=400)
    assert len(pieces) > 1 and all(len(p) <= 400 for p in pieces)
    assert " ".join(pieces) == line


def test_a_long_line_without_sentences_is_cut_between_words_and_never_over_the_limit():
    line = "word " * 500 + "x" * 900
    pieces = split_long(line.strip(), max_chars=400)
    assert all(len(p) <= 400 for p in pieces)
    assert "".join(pieces).replace(" ", "") == line.replace(" ", "")
