"""Checks over the whole real handbook: every file reads, and nothing junky reaches a passage."""

import json

from conftest import CORPUS


def test_every_manifest_document_is_read(corpus):
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert set(corpus) == {item["doc_id"] for item in manifest["documents"]}
    assert len(corpus) == 64


def test_every_document_has_text(corpus):
    empty = [doc_id for doc_id, doc in corpus.items() if not doc.sections or not doc.text.strip()]
    assert empty == []


def test_all_six_formats_are_present(corpus):
    assert {doc.format for doc in corpus.values()} == {"md", "txt", "pdf", "docx", "csv", "html"}


def test_no_extraction_junk_in_any_section(corpus):
    # (cid:NN) is what pdfminer-based readers leave for unmapped glyphs; \x7f and � are
    # raw bullet / replacement characters. None of them should ever be shown as a source.
    junk = ["(cid:", "\x7f", "�"]
    found = [(doc_id, j) for doc_id, doc in corpus.items() for j in junk if j in doc.text]
    assert found == []


def test_metadata_lines_are_not_part_of_the_text(corpus):
    # Front matter and "Document ID: ..." lines repeat the manifest; they would only add noise.
    leaks = [doc_id for doc_id, doc in corpus.items() if "Document ID:" in doc.text or "\ndoc_id:" in "\n" + doc.text]
    assert leaks == []
