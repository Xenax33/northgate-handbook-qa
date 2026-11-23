"""Show how one file is read, so it can be compared with the original by eye.

    uv run python -m handbook_qa.ingest data/corpus/hr-travel-policy.docx
    uv run python -m handbook_qa.ingest            (lists every document with its state)
"""

import sys
from pathlib import Path

from handbook_qa.config import get_settings
from handbook_qa.ingest import load_corpus, read_sections


def main(argv: list[str]) -> int:
    if argv:
        path = Path(argv[0])
        if not path.is_file():
            print(f"No such file: {path}")
            return 1
        for number, section in enumerate(read_sections(path), start=1):
            print(f"--- section {number}: {section.heading or '(no heading)'}")
            print(section.text)
            print()
        return 0
    settings = get_settings()
    today = settings.today()
    documents = load_corpus(settings.corpus_dir, today, settings.uploads_dir)
    print(f"{len(documents)} documents, states on {today}:")
    for doc in documents:
        extra = f" (by {doc.superseded_by})" if doc.superseded_by else ""
        uploaded = "  [uploaded]" if doc.source == "upload" else ""
        print(f"  {doc.state.value:17} {doc.format:5} {len(doc.sections):2} sections  {doc.doc_id}{extra}{uploaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
