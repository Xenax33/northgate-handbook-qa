"""Ask one question from the command line (uses 1 model request).

    uv run python -m handbook_qa.answer "How many days of annual leave do I get?"
"""

import sys

from handbook_qa.answer import Assistant, LLMError
from handbook_qa.config import get_settings


def main(argv: list[str]) -> int:
    if not argv:
        print('Usage: uv run python -m handbook_qa.answer "your question"')
        return 1
    try:
        answer = Assistant(get_settings()).ask(" ".join(argv))
    except (LLMError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(f"[{answer.status}] {answer.text}\n")
    if answer.searched_again_with:
        print(f"  (first answer was a refusal; searched again with: \"{answer.searched_again_with}\")\n")
    for citation in answer.citations:
        mark = "verified" if citation.verified else f"NOT VERIFIED ({citation.problem})"
        where = citation.passage.label if citation.passage else citation.key
        print(f"  {citation.key} {where}\n     \"{citation.quote}\"  -> {mark}")
    for warning in answer.warnings:
        print(f"\n  Warning: {warning}")
    sent = sorted({item.passage.doc_id for item in answer.context})
    print(f"\n  ({answer.model}, today {answer.today}, {len(answer.context)} passages from {len(sent)} documents, "
          f"{answer.model_calls} model call(s), {answer.prompt_tokens} tokens in / {answer.completion_tokens} out, {answer.seconds} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
