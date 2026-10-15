"""Tests for FakeDetector, choose_start, run orchestrator, and token stats.

Covers:
  - FakeDetector protocol conformance and determinism
  - choose_start with default and custom policies
  - Integration test: runner -> build_context -> detect across L1/L2/L3
  - Token statistics computation
  - Error handling in the runner
"""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.callgraph import CallGraph
from originscan.context.index import RepoIndex
from originscan.context.tokens import WhitespaceCounter
from originscan.detectors import FakeDetector
from originscan.interfaces import Context, DetectorAdapter
from originscan.runner import (
    RunResult,
    Slot,
    choose_start,
    compute_token_stats,
    run_experiment,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MULTIFILE = FIXTURES / "multifile"


# -----------------------------------------------------------------------
# FakeDetector
# -----------------------------------------------------------------------


class TestFakeDetector:
    def test_satisfies_protocol(self) -> None:
        d = FakeDetector()
        assert isinstance(d, DetectorAdapter)

    def test_returns_finding(self) -> None:
        d = FakeDetector()
        ctx = Context(text="int foo() { return 0; }", tokens=10, items=["f"])
        finding = d.run(ctx, run=1)
        assert isinstance(finding["verdict"], bool)
        assert isinstance(finding["confidence"], float)
        assert 0.0 <= finding["confidence"] <= 1.0
        assert finding["input_tokens"] == 10

    def test_deterministic(self) -> None:
        d = FakeDetector()
        ctx = Context(text="void bar() {}", tokens=5, items=["b"])
        f1 = d.run(ctx, run=1)
        f2 = d.run(ctx, run=1)
        assert f1 == f2

    def test_different_runs_may_differ(self) -> None:
        d = FakeDetector()
        ctx = Context(text="void bar() {}", tokens=5, items=["b"])
        # Run 1 and run 2 produce different hashes
        f1 = d.run(ctx, run=1)
        f2 = d.run(ctx, run=2)
        # They may or may not differ, but both should be valid
        assert isinstance(f1["verdict"], bool)
        assert isinstance(f2["verdict"], bool)

    def test_output_tokens_positive(self) -> None:
        d = FakeDetector()
        ctx = Context(text="int x;", tokens=3, items=["x"])
        finding = d.run(ctx, run=1)
        assert finding["output_tokens"] >= 10


# -----------------------------------------------------------------------
# choose_start
# -----------------------------------------------------------------------


class TestChooseStart:
    def test_default_human(self) -> None:
        assert choose_start("human") == "L1"

    def test_default_ai(self) -> None:
        assert choose_start("ai") == "L2"

    def test_default_unknown(self) -> None:
        assert choose_start("unknown") == "L1"

    def test_custom_policy(self) -> None:
        policy = {"human": "L2", "ai": "L3", "unknown": "L2"}
        assert choose_start("human", policy=policy) == "L2"
        assert choose_start("ai", policy=policy) == "L3"
        assert choose_start("unknown", policy=policy) == "L2"

    def test_missing_origin_falls_back(self) -> None:
        policy = {"ai": "L3"}  # No entry for "human"
        assert choose_start("human", policy=policy) == "L1"

    def test_cwe_family_ignored_in_default(self) -> None:
        """CWE family is accepted but doesn't affect default policy."""
        assert choose_start("ai", cwe_family="CWE-787") == "L2"


# -----------------------------------------------------------------------
# Slot data class
# -----------------------------------------------------------------------


class TestSlot:
    def test_create_slot(self) -> None:
        s = Slot(slot_id="foo@bar.c", origin="ai", label=True)
        assert s.slot_id == "foo@bar.c"
        assert s.origin == "ai"
        assert s.label is True

    def test_default_origin(self) -> None:
        s = Slot(slot_id="foo@bar.c")
        assert s.origin == "unknown"
        assert s.label is None


# -----------------------------------------------------------------------
# Integration: run_experiment
# -----------------------------------------------------------------------


class TestRunExperiment:
    @pytest.fixture()
    def slots(self) -> list[Slot]:
        return [
            Slot(
                slot_id=f"process_record@{FIXTURES / 'simple.c'}",
                origin="human",
            ),
            Slot(
                slot_id=f"main@{FIXTURES / 'simple.c'}",
                origin="ai",
            ),
        ]

    def test_basic_run(self, slots: list[Slot]) -> None:
        result = run_experiment(slots)
        assert isinstance(result, RunResult)
        assert len(result.slot_results) == 2
        assert result.total_slots == 2
        assert len(result.errors) == 0

    def test_results_have_metadata(self, slots: list[Slot]) -> None:
        result = run_experiment(slots)
        assert result.config_hash != ""
        assert result.tokenizer_name != ""
        assert result.timestamp != ""

    def test_slot_results_have_timing(self, slots: list[Slot]) -> None:
        result = run_experiment(slots)
        for sr in result.slot_results:
            assert sr.build_time_ms >= 0
            assert sr.detect_time_ms >= 0

    def test_level_selection_by_origin(self, slots: list[Slot]) -> None:
        """Human→L1, AI→L2 via default policy."""
        result = run_experiment(slots)
        human_result = next(
            sr for sr in result.slot_results if sr.origin == "human"
        )
        ai_result = next(
            sr for sr in result.slot_results if sr.origin == "ai"
        )
        assert human_result.level == "L1"
        assert ai_result.level == "L2"

    def test_explicit_levels_override(self, slots: list[Slot]) -> None:
        """When levels are specified, all slots run at those levels."""
        result = run_experiment(slots, levels=["L1", "L2"])
        assert len(result.slot_results) == 4  # 2 slots × 2 levels
        levels_used = {sr.level for sr in result.slot_results}
        assert levels_used == {"L1", "L2"}

    def test_multiple_runs(self, slots: list[Slot]) -> None:
        result = run_experiment(slots, runs_per_slot=3)
        assert len(result.slot_results) == 6  # 2 slots × 1 level × 3 runs

    def test_custom_detector(self, slots: list[Slot]) -> None:
        d = FakeDetector(base_confidence=0.9)
        result = run_experiment(slots, detector=d)
        for sr in result.slot_results:
            assert sr.finding["confidence"] >= 0.9

    def test_custom_counter(self, slots: list[Slot]) -> None:
        result = run_experiment(slots, counter=WhitespaceCounter())
        assert result.tokenizer_name == "whitespace"

    def test_custom_policy(self, slots: list[Slot]) -> None:
        policy = {"human": "L2", "ai": "L1", "unknown": "L1"}
        result = run_experiment(slots, policy=policy)
        human_result = next(
            sr for sr in result.slot_results if sr.origin == "human"
        )
        assert human_result.level == "L2"

    def test_token_cap_invariant(self, slots: list[Slot]) -> None:
        """Token counts must never exceed caps."""
        caps = {"L1": 200, "L2": 500, "L3": 1000}
        result = run_experiment(
            slots, levels=["L1", "L2"], caps=caps
        )
        for sr in result.slot_results:
            cap = caps[sr.level]
            assert sr.context_tokens <= cap, (
                f"{sr.slot_id}@{sr.level}: "
                f"{sr.context_tokens} > {cap}"
            )

    def test_error_handling(self) -> None:
        """Bad slot_id should be caught, not crash the whole run."""
        slots = [
            Slot(slot_id="nonexistent@fake.c", origin="human"),
        ]
        result = run_experiment(slots)
        assert len(result.errors) == 1
        assert len(result.slot_results) == 0


# -----------------------------------------------------------------------
# Integration: full pipeline with L3
# -----------------------------------------------------------------------


class TestRunExperimentWithL3:
    @pytest.fixture()
    def index(self) -> RepoIndex:
        return RepoIndex.build(MULTIFILE, commit="test_abc")

    @pytest.fixture()
    def graph(self, index: RepoIndex) -> CallGraph:
        return CallGraph.build(index)

    def test_l3_end_to_end(
        self, index: RepoIndex, graph: CallGraph
    ) -> None:
        slots = [
            Slot(
                slot_id=f"process_and_validate@{MULTIFILE / 'utils.c'}",
                origin="ai",
            ),
        ]
        result = run_experiment(
            slots,
            levels=["L1", "L2", "L3"],
            graph=graph,
            index=index,
            counter=WhitespaceCounter(),
        )
        assert len(result.slot_results) == 3
        assert len(result.errors) == 0
        l3_result = next(
            sr for sr in result.slot_results if sr.level == "L3"
        )
        assert l3_result.context_tokens > 0


# -----------------------------------------------------------------------
# Token statistics
# -----------------------------------------------------------------------


class TestTokenStats:
    def test_basic_stats(self) -> None:
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
        result = run_experiment(slots, levels=["L1", "L2"])
        stats = compute_token_stats(result)

        assert "L1" in stats
        assert "L2" in stats
        for level_stats in stats.values():
            assert level_stats["count"] == 2
            assert level_stats["min"] > 0
            assert level_stats["max"] >= level_stats["min"]
            assert level_stats["mean"] > 0
            assert level_stats["median"] > 0

    def test_empty_result(self) -> None:
        result = RunResult()
        stats = compute_token_stats(result)
        assert stats == {}
