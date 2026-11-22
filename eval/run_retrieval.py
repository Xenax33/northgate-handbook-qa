"""Measure 1 only: retrieval hit rate on the dev questions. Makes no LLM calls.

    uv run python eval/run_retrieval.py

Prints a table and saves the full result to eval/results/retrieval-<timestamp>.json.
"""

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from handbook_qa.config import PROJECT_ROOT, get_settings
from handbook_qa.evaluation.questions import load_questions
from handbook_qa.evaluation.retrieval import CUTOFFS, score_retrieval, summarise
from handbook_qa.ingest import load_corpus
from handbook_qa.passages import build_passages
from handbook_qa.search import Searcher
from handbook_qa.search.semantic import Embedder

EVAL_TODAY = date(2026, 11, 22)  # the date the dev questions were written for
QUESTIONS = PROJECT_ROOT / "eval" / "dev_questions.jsonl"
RESULTS = PROJECT_ROOT / "eval" / "results"


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout
        return out.stdout.strip() + ("+uncommitted" if dirty.strip() else "")
    except OSError:
        return "unknown"


def main() -> int:
    settings = get_settings()
    documents = load_corpus(settings.corpus_dir, EVAL_TODAY)
    questions = load_questions(QUESTIONS, {d.doc_id for d in documents})
    searcher = Searcher(build_passages(documents), Embedder(settings.embedding_model, settings.model_cache))
    results = score_retrieval(searcher, questions)
    summary = summarise(results)

    n = summary["questions"]
    print(f"Retrieval on {n} dev questions that expect documents (today pinned to {EVAL_TODAY})")
    print("  " + "   ".join(f"top {k}: {summary['hit_at'][k]}/{n}" for k in CUTOFFS))
    print("  top 3 by category: " + ", ".join(f"{c} {h}/{t}" for c, (h, t) in summary["hit_at_3_by_category"].items()))
    for qid, docs in summary["misses_at_3"].items():
        print(f"  miss @3  {qid:12} got {docs}")
    if summary["forbidden_documents_returned"]:
        print(f"  FORBIDDEN documents returned: {summary['forbidden_documents_returned']}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"retrieval-{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "kind": "retrieval",
                "run_at": datetime.now().isoformat(timespec="seconds"),
                "git_commit": git_commit(),
                "today": EVAL_TODAY.isoformat(),
                "embedding_model": settings.embedding_model,
                "passages_searchable": len(searcher.passages),
                "summary": summary,
                "per_question": [
                    {"id": r.question_id, "category": r.category, "top_documents": r.ranked_documents,
                     "hit_at": r.hit_at, "forbidden_found": r.forbidden_found}
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {out.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
