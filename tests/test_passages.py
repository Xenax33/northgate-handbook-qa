"""Passages (D10): one per section, each labelled with its document, section and state."""

from datetime import date

from handbook_qa.ingest import Document, Section, State
from handbook_qa.passages import MAX_CHARS, build_passages, split_long


def by_id(passages):
    return {p.id: p for p in passages}


def test_one_passage_per_section_for_the_real_handbook(corpus, passages):
    assert len(passages) == sum(len(doc.sections) for doc in corpus.values()) == 122
    assert len({p.id for p in passages}) == len(passages)  # ids are unique


def test_label_names_document_section_state_and_date(passages):
    p = by_id(passages)["hr-leave-policy-v1#2"]
    assert p.heading == "2. Annual leave"
    assert p.label == "[Leave Policy v1 > 2. Annual leave | SUPERSEDED by hr-leave-policy-v2 | effective 2023-01-01]"


def test_future_document_label_says_when_it_starts(passages):
    p = next(p for p in passages if p.doc_id == "hr-parental-leave-policy-2027")
    assert "NOT YET IN FORCE, from 2027-01-01" in p.label


def test_current_document_without_headings(passages):
    p = next(p for p in passages if p.doc_id == "it-vpn-guide")
    assert p.label == "[VPN Guide | CURRENT | effective 2024-08-20]"
    assert p.search_text.startswith("VPN Guide\n")


def test_no_real_section_is_long_enough_to_be_cut(corpus):
    assert max(len(s.text) for doc in corpus.values() for s in doc.sections) <= MAX_CHARS


def test_long_text_is_cut_at_line_breaks_only():
    lines = [f"line {n} " + "x" * 90 for n in range(40)]
    pieces = split_long("\n".join(lines), max_chars=500)
    assert len(pieces) > 1
    assert all(len(piece) <= 500 for piece in pieces)
    assert "\n".join(pieces).split("\n") == lines  # nothing lost, nothing cut mid-line


def test_short_text_is_left_alone():
    assert split_long("short") == ["short"]


def test_cut_sections_get_numbered_ids():
    long_text = "\n".join("y" * 100 for _ in range(40))
    doc = Document("upload", "Upload", "u.md", "md", "Other", "Me", date(2026, 1, 1), State.CURRENT,
                   sections=[Section(None, long_text), Section("Next", "tail")])
    ids = [p.id for p in build_passages([doc])]
    assert ids[0] == "upload#1" and ids[-1] == f"upload#{len(ids)}" and len(ids) > 2
