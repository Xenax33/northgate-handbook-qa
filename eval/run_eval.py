"""Full evaluation: ask the assistant every dev question and score the four measures (D4).

    uv run python eval/run_eval.py                      # all 40 questions, about 4 minutes
    uv run python eval/run_eval.py --only version-01,refuse-01
    uv run python eval/run_eval.py --label "what changed in this run"

"Today" is fixed at 2026-11-22, the date the questions were written for. Requests are paced to stay
under Gemini's free tier (15 a minute). Temporary errors (rate limit, HTTP 5xx such as 503, timeouts)
are retried up to 3 times with growing pauses. The number of model requests is exact: the SDK's own
retries are switched off and every attempt is counted here. Every run is saved, even a partial one,
as eval/results/eval-<timestamp>.json (everything) and .md (the summary table and the failures).
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import replace
from datetime import date, datetime

from handbook_qa.answer import Assistant
from handbook_qa.answer.llm import LLMError, OpenAICompatibleModel
from handbook_qa.config import PROJECT_ROOT, get_settings
from handbook_qa.evaluation.questions import load_questions
from handbook_qa.evaluation.report import markdown_report, score_record, summarise

EVAL_TODAY = date(2026, 11, 22)
QUESTIONS = PROJECT_ROOT / "eval" / "dev_questions.jsonl"
RESULTS = PROJECT_ROOT / "eval" / "results"
SECONDS_BETWEEN_REQUESTS = 4.5  # 15 requests a minute on the free tier, plus a margin
RETRY_PAUSES = {"rate_limit": [65, 65], "default": [15, 45]}  # seconds before attempt 2 and 3


def git_commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "eval/run_eval.py", "eval/dev_questions.jsonl"],
                               cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()
        return head + ("+uncommitted" if dirty else "")
    except OSError:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--label", default="", help="a note saved with the run")
    args = parser.parse_args()

    settings = replace(get_settings(), fixed_today=EVAL_TODAY, uploads_dir=None)  # official handbook only, never uploads
    model = OpenAICompatibleModel(settings.llm_base_url, settings.llm_model, settings.llm_api_key, max_retries=0)
    assistant = Assistant(settings, model=model)
    questions = load_questions(QUESTIONS, set(assistant.documents))
    if args.only:
        wanted = {q.strip() for q in args.only.split(",")}
        questions = [q for q in questions if q.id in wanted]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    run = {
        "kind": "eval", "run_at": datetime.now().isoformat(timespec="seconds"), "label": args.label,
        "git_commit": git_commit(), "today": EVAL_TODAY.isoformat(), "model": settings.llm_model,
        "embedding_model": settings.embedding_model, "questions_asked": 0, "model_requests": 0,
        "retries": [], "per_question": [],
    }
    last_request = 0.0
    started = time.monotonic()
    for number, question in enumerate(questions, start=1):
        record = {"id": question.id, "category": question.category, "question": question.question}
        answer = None
        for attempt in (1, 2, 3):
            wait = SECONDS_BETWEEN_REQUESTS - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            try:
                answer = assistant.ask(question.question)
                break
            except LLMError as error:
                if not error.retryable or attempt == 3:
                    record["error"] = str(error)
                    break
                pause = RETRY_PAUSES.get(error.kind, RETRY_PAUSES["default"])[attempt - 1]
                run["retries"].append({"id": question.id, "attempt": attempt, "kind": error.kind})
                print(f"   {question.id}: {error.kind}, retrying in {pause} s")
                time.sleep(pause)
        if answer is None:
            record.update(status="error")
        else:
            record.update(
                status=answer.status,
                answer=answer.text,
                citations=[{"key": c.key, "doc_id": c.passage.doc_id if c.passage else None,
                            "heading": c.passage.heading if c.passage else None, "quote": c.quote,
                            "verified": c.verified, "problem": c.problem} for c in answer.citations],
                warnings=answer.warnings,
                documents_read=list(dict.fromkeys(item.passage.doc_id for item in answer.context)),
                passages_read=len(answer.context),
                prompt_tokens=answer.prompt_tokens,
                completion_tokens=answer.completion_tokens,
                seconds=answer.seconds,
                model_calls=answer.model_calls,
                searched_again_with=answer.searched_again_with,
                first_status=answer.first_status,
            )
        record = score_record(question, record)
        run["per_question"].append(record)
        run["questions_asked"] = number
        run["model_requests"] = model.requests_made
        print(f"{number:2}/{len(questions)} {question.id:12} {'PASS' if record['passed'] else 'FAIL'}  [{record['status']}]"
              + ("" if record["passed"] else "  " + "; ".join(record["reasons"])))
        save(run, stamp)

    run["seconds_total"] = round(time.monotonic() - started)
    run["summary"] = summarise(run["per_question"])
    save(run, stamp)
    report = markdown_report(run)
    (RESULTS / f"eval-{stamp}.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Saved eval/results/eval-{stamp}.json and .md")
    return 0


def save(run: dict, stamp: str) -> None:
    (RESULTS / f"eval-{stamp}.json").write_text(json.dumps(run, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
