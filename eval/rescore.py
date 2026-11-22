"""Re-score a saved eval run with the current questions and matching rules. No model calls.

    uv run python eval/rescore.py eval/results/eval-20261123-033512.json --note "why"

The original file is never changed: the result is written next to it as <name>-rescored.json / .md.
Use this when the measuring instrument changes (a matching rule, an accepted wording), so the effect
of that change can be seen on its own, separately from any change to the assistant.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from handbook_qa.config import PROJECT_ROOT
from handbook_qa.evaluation.questions import load_questions
from handbook_qa.evaluation.report import markdown_report, score_record, summarise

QUESTIONS = PROJECT_ROOT / "eval" / "dev_questions.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    run = json.loads(args.run.read_text(encoding="utf-8"))
    questions = {q.id: q for q in load_questions(QUESTIONS)}
    before = run.get("summary", {}).get("passed")
    run["per_question"] = [score_record(questions[r["id"]], r) for r in run["per_question"]]
    run["summary"] = summarise(run["per_question"])
    run["rescored_at"] = datetime.now().isoformat(timespec="seconds")
    run["rescore_note"] = args.note
    out = args.run.with_name(args.run.stem + "-rescored")
    out.with_suffix(".json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    report = markdown_report(run)
    out.with_suffix(".md").write_text(report, encoding="utf-8")
    print(f"Passed before: {before}, after re-scoring: {run['summary']['passed']}")
    print(report)
    print(f"Saved {out.with_suffix('.json').name} and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
