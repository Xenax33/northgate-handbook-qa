"""Hybrid search (D11) with old documents hidden (D12)."""

from handbook_qa.evaluation.questions import load_questions
from handbook_qa.search import HIDDEN_STATES, reciprocal_rank_fusion
from handbook_qa.search.keyword import KeywordIndex

from conftest import QUESTIONS


def doc_ids(searcher, query, n=3):
    return [doc_id for doc_id, _ in searcher.top_documents(query, n)]


# Old documents --------------------------------------------------------------------------------


def test_superseded_and_deprecated_passages_are_not_searchable(searcher, passages):
    hidden = {p.doc_id for p in passages if p.state in HIDDEN_STATES}
    assert hidden == {"hr-leave-policy-v1", "eng-deploy-runbook-2023"}
    assert not any(p.doc_id in hidden for p in searcher.passages)
    assert len(searcher.passages) == 111


def test_no_dev_question_ever_retrieves_an_old_document(searcher):
    for question in load_questions(QUESTIONS):
        found = doc_ids(searcher, question.question, n=10)
        assert "hr-leave-policy-v1" not in found and "eng-deploy-runbook-2023" not in found, question.id


def test_future_document_is_still_searchable(searcher):
    assert "hr-parental-leave-policy-2027" in doc_ids(searcher, "secondary caregiver leave for a baby born in 2027", n=3)


# Each half of the hybrid covers what the other misses (from the D11 spike) -------------------------


def test_exact_terms_are_found(searcher):
    assert doc_ids(searcher, "How many quotes do I need for a purchase above $40,000?", 1) == ["fin-procurement-policy"]
    assert doc_ids(searcher, "Where should secrets like API keys be stored?", 1) == ["sec-security-policy"]


def test_meaning_is_found_without_shared_words(searcher):
    assert "it-laptop-policy" in doc_ids(searcher, "my notebook computer was stolen, what now", 3)


def test_top_documents_groups_passages_by_document(searcher):
    results = searcher.top_documents("How long before a scheduled release does the deploy freeze start?", 5)
    assert len(results) == 5
    assert len({doc_id for doc_id, _ in results}) == 5
    for doc_id, hits in results:
        assert hits and all(h.passage.doc_id == doc_id for h in hits)


# Building blocks ------------------------------------------------------------------------------------


def test_rrf_rewards_items_both_rankings_like():
    fused = [item for item, _ in reciprocal_rank_fusion([[1, 2, 3], [4, 2, 5]])]
    assert fused[0] == 2  # 2nd in both beats 1st in only one of them
    assert set(fused) == {1, 2, 3, 4, 5}


def test_rrf_ties_are_broken_by_first_appearance():
    assert [item for item, _ in reciprocal_rank_fusion([[5, 6], [6, 5]])] == [5, 6]


def test_keyword_index_edge_cases():
    assert KeywordIndex([]).rank("anything") == []
    index = KeywordIndex(["VPN sessions limit", "annual leave days"])
    assert index.rank("the and of") == []  # only stopwords
    assert index.rank("VPN") == [0]  # passages sharing no word are left out
