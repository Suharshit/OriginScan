"""JSON report generator — RunResult → structured JSON.

Follows the schema in design.md §9: one JSON file per scan with
metadata, per-function results, and summary statistics.

Public API:
    generate_json_report(result) -> str
    save_json_report(result, path) -> Path
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from originscan.runner import RunResult, SlotResult


def _slot_result_to_dict(sr: SlotResult) -> dict:
    """Convert a SlotResult to a JSON-serializable dict."""
    return {
        "slot_id": sr.slot_id,
        "level": sr.level,
        "origin": sr.origin,
        "context_tokens": sr.context_tokens,
        "context_items": sr.context_items,
        "build_time_ms": sr.build_time_ms,
        "detect_time_ms": sr.detect_time_ms,
        "finding": {
            "verdict": sr.finding["verdict"],
            "cwe": sr.finding["cwe"],
            "line": sr.finding["line"],
            "confidence": sr.finding["confidence"],
            "input_tokens": sr.finding["input_tokens"],
            "output_tokens": sr.finding["output_tokens"],
        },
    }


def generate_json_report(result: RunResult) -> str:
    """Generate a JSON report string from a RunResult.

    Returns:
        Pretty-printed JSON string following design.md §9 schema.
    """
    from originscan.runner import compute_token_stats

    report = {
        "originscan_version": "0.1.0",
        "metadata": {
            "config_hash": result.config_hash,
            "tokenizer": result.tokenizer_name,
            "timestamp": result.timestamp,
            "total_slots": result.total_slots,
        },
        "summary": {
            "total_results": len(result.slot_results),
            "total_findings": result.total_findings,
            "total_input_tokens": result.total_input_tokens,
            "total_output_tokens": result.total_output_tokens,
            "total_build_time_ms": round(result.total_build_time_ms, 2),
            "total_detect_time_ms": round(result.total_detect_time_ms, 2),
            "errors": len(result.errors),
        },
        "token_stats": compute_token_stats(result),
        "results": [_slot_result_to_dict(sr) for sr in result.slot_results],
        "errors": result.errors,
    }

    return json.dumps(report, indent=2, ensure_ascii=False)


def save_json_report(result: RunResult, path: str | Path) -> Path:
    """Save a JSON report to a file.

    Args:
        result: The RunResult to serialize.
        path: Output file path.

    Returns:
        The path the report was written to.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_json_report(result), encoding="utf-8")
    return out
