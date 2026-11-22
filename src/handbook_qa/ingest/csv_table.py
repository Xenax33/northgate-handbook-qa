"""CSV files: every row becomes one self-contained line, "column: value, column: value".

A row like "L3,2,Chicago; Seattle; ...,75" means little on its own. Written as
"grade: L3, city_tier: 2, example_cities: Chicago; Seattle; ..., per_diem_usd: 75" it can be found by
search and read by the model without the header row (D8). The whole table stays one section: the
largest CSV in the handbook is about 200 tokens.
"""

import csv
import io
from pathlib import Path

from handbook_qa.ingest.document import Section


def read(path: Path) -> list[Section]:
    return parse(path.read_text(encoding="utf-8-sig"))


def parse(text: str) -> list[Section]:
    reader = csv.DictReader(io.StringIO(text))
    lines = []
    for row in reader:
        cells = [f"{column.strip()}: {(value or '').strip()}" for column, value in row.items() if column]
        if any(value for value in row.values()):
            lines.append(", ".join(cells))
    return [Section(None, "\n".join(lines))] if lines else []
