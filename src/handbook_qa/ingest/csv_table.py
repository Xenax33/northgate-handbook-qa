"""CSV files: every row becomes one self-contained line, "column: value, column: value".

A row like "L3,2,Chicago; Seattle; ...,75" means little on its own. Written as
"grade: L3, city_tier: 2, example_cities: Chicago; Seattle; ..., per_diem_usd: 75" it can be found by
search and read by the model without the header row (D8). The whole table stays one section: the
largest CSV in the handbook is about 200 tokens.

Malformed tables are refused with a clear message rather than read wrongly: a row with more values
than there are columns (usually an unquoted comma) would otherwise shift values into the wrong
columns, and blank or repeated column names would silently overwrite values.
"""

import csv
import io
from pathlib import Path

from handbook_qa.ingest.document import ReaderError, Section, read_text_file


def read(path: Path) -> list[Section]:
    return parse(read_text_file(path), path.name)


def parse(text: str, name: str = "table") -> list[Section]:
    rows = list(csv.reader(io.StringIO(text)))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [cell.strip() for cell in rows[0]]
    if any(not column for column in header):
        raise ReaderError(f"{name}: a column has no name in the header row")
    repeated = sorted({column for column in header if header.count(column) > 1})
    if repeated:
        raise ReaderError(f"{name}: column name repeated in the header row: {', '.join(repeated)}")
    lines = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) > len(header):
            raise ReaderError(
                f"{name} row {number}: {len(row)} values but {len(header)} columns; quote values that contain commas"
            )
        values = [cell.strip() for cell in row] + [""] * (len(header) - len(row))
        lines.append(", ".join(f"{column}: {value}" for column, value in zip(header, values)))
    return [Section(None, "\n".join(lines))] if lines else []
