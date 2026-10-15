"""Tests for Phase 7: reports, policy, escalation, end-to-end."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from originscan.context.tokens import WhitespaceCounter
from originscan.detectors import FakeDetector
from originscan.policy import PolicyConfig, default_policy, load_policy
from originscan.report.json_report import generate_json_report, save_json_report
from originscan.report.markdown_report import (
    generate_markdown_report,
    save_markdown_report,
)
from originscan.runner import (
    RunResult,
    Slot,
    escalate_scan,
    run_experiment,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# -----------------------------------------------------------------------
# Helper to build a sample RunResult
# -----------------------------------------------------------------------


def _make_result() -> RunResult:
    slots = [
        Slot(
            slot_id=f"process_record@{FIXTURES / 'simple.c'}",
            origin="human",
        ),
        Slot(
            slot_id=f"main@{FIXTURES / 'simple.c'}",
            origin="ai",
        ),
    ]
    return run_experiment(slots, levels=["L1", "L2"])


# -----------------------------------------------------------------------
# JSON report
# -----------------------------------------------------------------------


class TestJsonReport:
    def test_generates_valid_json(self) -> None:
        result = _make_result()
        report_str = generate_json_report(result)
        data = json.loads(report_str)
        assert "originscan_version" in data
        assert "metadata" in data
        assert "summary" in data
        assert "results" in data

    def test_has_metadata(self) -> None:
        result = _make_result()
        data = json.loads(generate_json_report(result))
        assert data["metadata"]["config_hash"] != ""
        assert data["metadata"]["tokenizer"] != ""

    def test_results_count(self) -> None:
        result = _make_result()
        data = json.loads(generate_json_report(result))
        assert len(data["results"]) == 4  # 2 slots x 2 levels

    def test_finding_fields(self) -> None:
        result = _make_result()
        data = json.loads(generate_json_report(result))
        for r in data["results"]:
            assert "finding" in r
            assert "verdict" in r["finding"]
            assert "confidence" in r["finding"]

    def test_save_to_file(self) -> None:
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_json_report(result, Path(tmp) / "report.json")
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "results" in data

    def test_token_stats_included(self) -> None:
        result = _make_result()
        data = json.loads(generate_json_report(result))
        assert "token_stats" in data
        assert "L1" in data["token_stats"]


# -----------------------------------------------------------------------
# Markdown report
# -----------------------------------------------------------------------


class TestMarkdownReport:
    def test_generates_markdown(self) -> None:
        result = _make_result()
        md = generate_markdown_report(result)
        assert "## OriginScan Results" in md
        assert "<!-- originscan -->" in md

    def test_has_findings_table(self) -> None:
        result = _make_result()
        md = generate_markdown_report(result)
        assert "| Function |" in md

    def test_has_token_usage(self) -> None:
        result = _make_result()
        md = generate_markdown_report(result)
        assert "Token Usage" in md

    def test_has_disclaimer(self) -> None:
        result = _make_result()
        md = generate_markdown_report(result)
        assert "research prototype" in md

    def test_save_to_file(self) -> None:
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_markdown_report(result, Path(tmp) / "report.md")
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "originscan" in content

    def test_errors_section(self) -> None:
        result = _make_result()
        result.errors = ["test error 1", "test error 2"]
        md = generate_markdown_report(result)
        assert "error(s)" in md
        assert "test error 1" in md


# -----------------------------------------------------------------------
# Policy
# -----------------------------------------------------------------------


class TestPolicy:
    def test_default_policy(self) -> None:
        p = default_policy()
        assert p.choose_level("human") == "L1"
        assert p.choose_level("ai") == "L2"
        assert p.choose_level("unknown") == "L1"

    def test_custom_policy(self) -> None:
        p = PolicyConfig(
            levels={"human": "L2", "ai": "L3", "unknown": "L2"}
        )
        assert p.choose_level("human") == "L2"
        assert p.choose_level("ai") == "L3"

    def test_cwe_override(self) -> None:
        p = PolicyConfig(
            overrides={"CWE-787": {"human": "L2", "ai": "L3"}}
        )
        assert p.choose_level("human", cwe_family="CWE-787") == "L2"
        assert p.choose_level("human") == "L1"  # No override

    def test_load_from_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(
                "levels:\n"
                "  human: L1\n"
                "  ai: L3\n"
                "escalation:\n"
                "  tau: 0.8\n"
                "  budget: 30000\n"
            )
            f.flush()
            p = load_policy(f.name)
            assert p.choose_level("ai") == "L3"
            assert p.escalation_tau == 0.8
            assert p.escalation_budget == 30000

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_policy("/nonexistent/policy.yaml")

    def test_escalation_defaults(self) -> None:
        p = default_policy()
        assert p.escalation_tau == 0.7
        assert p.escalation_max_level == "L3"
        assert p.escalation_budget == 50000


# -----------------------------------------------------------------------
# Escalation loop
# -----------------------------------------------------------------------


class TestEscalation:
    def test_escalation_runs(self) -> None:
        slot_id = f"process_record@{FIXTURES / 'simple.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="human",
            detector=FakeDetector(base_confidence=0.5),
            counter=WhitespaceCounter(),
            tau=0.99,  # Force escalation
            max_level="L2",
        )
        # Should have at least tried L1, possibly escalated to L2
        assert len(results) >= 1
        assert results[0].level == "L1"  # human starts at L1

    def test_escalation_stops_at_max_level(self) -> None:
        slot_id = f"process_record@{FIXTURES / 'simple.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="human",
            detector=FakeDetector(base_confidence=0.5),
            counter=WhitespaceCounter(),
            tau=0.99,
            max_level="L1",  # Can't escalate past L1
        )
        assert len(results) == 1
        assert results[0].level == "L1"

    def test_escalation_respects_budget(self) -> None:
        slot_id = f"process_record@{FIXTURES / 'simple.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="human",
            detector=FakeDetector(base_confidence=0.5),
            counter=WhitespaceCounter(),
            tau=0.99,
            budget=1,  # Very small budget
        )
        # Should stop after first level due to budget
        assert len(results) == 1

    def test_high_confidence_no_escalation(self) -> None:
        slot_id = f"process_record@{FIXTURES / 'simple.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="human",
            detector=FakeDetector(base_confidence=0.95),
            counter=WhitespaceCounter(),
            tau=0.7,
        )
        # High confidence → no escalation needed
        assert len(results) == 1


# -----------------------------------------------------------------------
# End-to-end: scan → report
# -----------------------------------------------------------------------


class TestEndToEnd:
    def test_scan_to_json_report(self) -> None:
        result = _make_result()
        report = generate_json_report(result)
        data = json.loads(report)
        assert data["summary"]["total_results"] > 0
        assert data["summary"]["errors"] == 0

    def test_scan_to_markdown_report(self) -> None:
        result = _make_result()
        md = generate_markdown_report(result)
        assert "OriginScan" in md
        assert "function(s)" in md

    def test_full_pipeline_with_reports(self) -> None:
        """Full end-to-end: slots → run → JSON + MD reports."""
        with tempfile.TemporaryDirectory() as tmp:
            result = _make_result()
            json_path = save_json_report(result, Path(tmp) / "r.json")
            md_path = save_markdown_report(result, Path(tmp) / "r.md")
            assert json_path.exists()
            assert md_path.exists()
            # JSON is valid
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert len(data["results"]) > 0
            # MD has marker
            md = md_path.read_text(encoding="utf-8")
            assert "<!-- originscan -->" in md
