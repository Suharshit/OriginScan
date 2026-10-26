"""Tests for exp/grid.py: CallRecord survives a Parquet round trip."""

from __future__ import annotations

from dataclasses import asdict, replace

import pyarrow as pa
import pyarrow.parquet as pq

from originscan.exp.grid import GRID_COLUMNS, CallRecord


def test_call_record_parquet_roundtrip(tmp_path) -> None:
    ok = CallRecord(
        slot_id="910",
        version_id="910-human-pre",
        origin="human",
        generator=None,
        repo="mm2/little-cms",
        file="src/cmsio0.c",
        function="_cmsReadHeader",
        split="dev",
        level="L2",
        context_tokens=1834,
        detector="d2",
        model_id="model-a",
        prompt_version="d2_v1",
        run=2,
        pred_vulnerable=True,
        pred_cwe="CWE-122",
        pred_line=41,
        confidence=0.85,
        parse_ok=True,
        input_tokens=2010,
        output_tokens=64,
        latency_ms=812.5,
        cost_usd=0.00123,
        status="ok",
        run_id="run-0001",
        git_commit="7005ef3",
        config_hash="abc123",
        timestamp="2026-10-26T12:00:00+00:00",
    )
    # A failed call is still written; its prediction and usage fields are None.
    failed = replace(
        ok,
        run=3,
        pred_vulnerable=None,
        pred_cwe=None,
        pred_line=None,
        confidence=None,
        parse_ok=False,
        input_tokens=None,
        output_tokens=None,
        latency_ms=None,
        cost_usd=None,
        status="timeout",
    )

    path = tmp_path / "grid.parquet"
    pq.write_table(pa.Table.from_pylist([asdict(ok), asdict(failed)]), path)
    table = pq.read_table(path)

    assert tuple(table.column_names) == GRID_COLUMNS
    assert [CallRecord(**row) for row in table.to_pylist()] == [ok, failed]
