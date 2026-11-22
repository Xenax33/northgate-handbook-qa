"""Read manifest.json and work out each document's state for a given day (decision D9).

The manifest's own `status` field can't be trusted on its own: Leave Policy v1 is marked "current"
although v2 supersedes it, and the 2027 parental leave revision is marked "current" although it only
takes effect on 2027-01-01. So the state is derived from three facts the manifest does get right:
`status: deprecated`, `supersedes`, and `effective_date`.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from handbook_qa.ingest.document import State


class ManifestError(ValueError):
    """The manifest is malformed or refers to something that doesn't exist."""


@dataclass(frozen=True)
class ManifestEntry:
    doc_id: str
    path: str
    title: str
    category: str
    owner: str
    effective_date: date
    status: str
    supersedes: str | None = None


REQUIRED = ("doc_id", "path", "title", "category", "owner", "effective_date", "status")


def read_manifest(path: Path) -> list[ManifestEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in raw.get("documents", []):
        missing = [key for key in REQUIRED if not item.get(key)]
        if missing:
            raise ManifestError(f"manifest entry {item.get('doc_id', '?')!r} is missing {', '.join(missing)}")
        try:
            effective = date.fromisoformat(item["effective_date"])
        except ValueError as error:
            raise ManifestError(f"{item['doc_id']}: effective_date {item['effective_date']!r} is not YYYY-MM-DD") from error
        entries.append(
            ManifestEntry(
                doc_id=item["doc_id"],
                path=item["path"],
                title=item["title"],
                category=item["category"],
                owner=item["owner"],
                effective_date=effective,
                status=item["status"],
                supersedes=item.get("supersedes"),
            )
        )
    check_references(entries)
    return entries


def check_references(entries: list[ManifestEntry]) -> None:
    ids = [entry.doc_id for entry in entries]
    duplicates = sorted({doc_id for doc_id in ids if ids.count(doc_id) > 1})
    if duplicates:
        raise ManifestError(f"duplicate doc_id in manifest: {', '.join(duplicates)}")
    known = set(ids)
    for entry in entries:
        if entry.supersedes and entry.supersedes not in known:
            raise ManifestError(f"{entry.doc_id} supersedes {entry.supersedes!r}, which is not in the manifest")


def document_states(entries: list[ManifestEntry], today: date) -> dict[str, tuple[State, str | None]]:
    """Return {doc_id: (state, superseded_by)}.

    Rules, in order:
    1. status "deprecated" -> DEPRECATED.
    2. another document supersedes it and that one is already in force -> SUPERSEDED.
    3. its own effective date is after today -> NOT_YET_IN_FORCE.
    4. otherwise CURRENT.
    """
    superseded_by = {
        entry.supersedes: entry.doc_id
        for entry in entries
        if entry.supersedes and entry.effective_date <= today
    }
    states = {}
    for entry in entries:
        if entry.status == "deprecated":
            states[entry.doc_id] = (State.DEPRECATED, None)
        elif entry.doc_id in superseded_by:
            states[entry.doc_id] = (State.SUPERSEDED, superseded_by[entry.doc_id])
        elif entry.effective_date > today:
            states[entry.doc_id] = (State.NOT_YET_IN_FORCE, None)
        else:
            states[entry.doc_id] = (State.CURRENT, None)
    return states
