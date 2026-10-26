"""docs/data-model.md and the code that implements it must list the same fields."""

from __future__ import annotations

import re
from pathlib import Path

from originscan.exp.corpus import SPLIT_COLUMNS
from originscan.exp.grid import CALL_KEY, GRID_COLUMNS

DOC = Path(__file__).resolve().parent.parent / "docs" / "data-model.md"


def doc_fields(heading: str) -> tuple[str, ...]:
    """Field names in the first code block under the ``## heading`` section."""
    text = DOC.read_text(encoding="utf-8")
    section = text.split(f"## {heading}", 1)[1]
    block = re.search(r"```\w*\n(.*?)```", section, re.DOTALL)
    assert block, f"no field block under {heading!r}"
    return tuple(block.group(1).split())


def test_grid_row_matches_call_record() -> None:
    assert doc_fields("Grid row") == GRID_COLUMNS


def test_split_csv_matches_corpus() -> None:
    assert doc_fields("`split.csv`") == SPLIT_COLUMNS


def test_call_key_columns_are_grid_columns() -> None:
    assert set(CALL_KEY) <= set(GRID_COLUMNS)


def test_labels_never_in_grid() -> None:
    labels = set(doc_fields("`labels.csv`")) - {"version_id"}
    assert not labels & set(GRID_COLUMNS)
