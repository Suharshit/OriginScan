"""CallRecord (one results-grid row per detector call), Parquet writer,
resume support and the completeness check.

Labels are never stored in the grid; they are joined later by version_id.

Phase 1 (CallRecord) and Phase 5 (writer, resume, check).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from originscan.exp.corpus import Split
    from originscan.interfaces import Level, Origin


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One grid row. Fields and order match docs/data-model.md exactly.

    Prediction and usage fields are None when the call failed or the reply
    did not parse; ``status`` and ``parse_ok`` say which.
    """

    slot_id: str
    version_id: str
    origin: Origin
    generator: str | None
    """None for human versions."""
    repo: str
    """Lowercase owner/name, as in slots.csv and split.csv."""
    file: str
    function: str
    split: Split
    level: Level
    context_tokens: int
    detector: str
    model_id: str
    prompt_version: str
    run: int
    pred_vulnerable: bool | None
    pred_cwe: str | None
    pred_line: int | None
    confidence: float | None
    parse_ok: bool
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float | None
    cost_usd: float | None
    status: str
    run_id: str
    git_commit: str
    config_hash: str
    timestamp: str
    """ISO 8601, UTC."""


GRID_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(CallRecord))
"""Grid column names in order."""

CALL_KEY: tuple[str, ...] = ("version_id", "detector", "level", "run")
"""Columns that identify one call (resume and completeness check)."""
