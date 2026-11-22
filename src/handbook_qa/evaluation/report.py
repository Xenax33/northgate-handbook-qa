"""Turn scored eval records into a summary and a readable Markdown report. Shared by
eval/run_eval.py (new runs) and eval/rescore.py (re-scoring a saved run without model calls)."""

from collections import Counter

from handbook_qa.evaluation.questions import Question
from handbook_qa.evaluation.scoring import MEASURES, score_answer


def score_record(question: Question, record: dict) -> dict:
    """Add measures, passed and reasons to one saved answer record (a run's per_question entry)."""
    if record["status"] == "error":
        return {**record, "measures": {m: False for m in MEASURES}, "passed": False, "reasons": [record.get("error", "error")]}
    cited = list(dict.fromkeys(c["doc_id"] for c in record.get("citations", []) if c["verified"] and c["doc_id"]))
    score = score_answer(question, record["status"], record.get("answer", ""), record.get("documents_read", []), cited)
    return {**record, "measures": {m: getattr(score, m) for m in MEASURES}, "passed": score.passed, "reasons": score.reasons}


def summarise(records: list[dict]) -> dict:
    measures = {}
    for m in MEASURES:
        applicable = [r["measures"][m] for r in records if r["measures"].get(m) is not None]
        measures[m] = [sum(applicable), len(applicable)]
    categories = {}
    for category, count in sorted(Counter(r["category"] for r in records).items()):
        categories[category] = [sum(r["passed"] for r in records if r["category"] == category), count]
    return {
        "passed": [sum(r["passed"] for r in records), len(records)],
        "measures": measures,
        "categories": categories,
        "unverified_quotes": sum(1 for r in records for c in r.get("citations", []) if not c["verified"]),
        "answers_with_warnings": sum(1 for r in records if r.get("warnings")),
        "errors": sum(1 for r in records if r["status"] == "error"),
        "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in records),
        "completion_tokens": sum(r.get("completion_tokens") or 0 for r in records),
    }


def markdown_report(run: dict) -> str:
    s = run["summary"]

    def pct(pair):
        return f"{pair[0]}/{pair[1]}" + (f" ({round(100 * pair[0] / pair[1])}%)" if pair[1] else "")

    lines = [
        f"# Eval run {run['run_at']}" + (" (re-scored)" if run.get("rescored_at") else ""),
        "",
        f"Model `{run['model']}`, embeddings `{run['embedding_model']}`, today fixed at {run['today']}, "
        f"code `{run['git_commit']}`. {run['questions_asked']} questions, {run['model_requests']} model requests, "
        f"{s['prompt_tokens']:,} tokens in / {s['completion_tokens']:,} out, {run.get('seconds_total', '?')} s."
        + (f" Label: {run['label']}" if run.get("label") else ""),
    ]
    if run.get("rescored_at"):
        lines += ["", f"Re-scored on {run['rescored_at']} with the current questions and matching rules, "
                      f"without new model calls. {run.get('rescore_note', '')}"]
    lines += ["", "| Measure | Passed |", "|---|---|", f"| **All four (question passes)** | **{pct(s['passed'])}** |"]
    lines += [f"| {m} | {pct(s['measures'][m])} |" for m in MEASURES]
    lines += ["", "| Category | Passed |", "|---|---|"] + [f"| {c} | {pct(v)} |" for c, v in s["categories"].items()]
    lines += ["", f"Unverified quotes: {s['unverified_quotes']}. Answers with a warning: {s['answers_with_warnings']}. "
                  f"Errors: {s['errors']}.", "", "## Failures", ""]
    failures = [r for r in run["per_question"] if not r["passed"]]
    if not failures:
        lines.append("None.")
    for r in failures:
        lines += [f"**{r['id']}** ({r['category']}): {r['question']}",
                  f"- status `{r['status']}`: {r.get('answer', r.get('error', ''))}",
                  *[f"- {reason}" for reason in r["reasons"]], ""]
    return "\n".join(lines) + "\n"
