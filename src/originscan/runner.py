"""Run orchestrator — wires build_context, detect, and choose_start.

Drives the experiment loop: for each slot, determine the start level,
build context, run detection, and collect results with full metadata.

See PRD Phase 5 (tasks 5.1, 5.3) and design.md §8.

Public API:
    run_experiment(slots, ...) -> RunResult
    RunResult — frozen result container with metadata
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from originscan.context.builders import build_context
from originscan.context.tokens import TokenCounter, create_counter
from originscan.detectors import FakeDetector

if TYPE_CHECKING:
    from originscan.context.builders import SlotResolver
    from originscan.context.callgraph import CallGraph
    from originscan.context.index import RepoIndex
    from originscan.interfaces import (
        DetectorAdapter,
        Finding,
        Level,
        Origin,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# choose_start — deterministic start-level chooser
# ---------------------------------------------------------------------------

# Default policy: human→L1, ai→L2, unknown→L1 (PRD FR-19)
DEFAULT_POLICY: dict[str, Level] = {
    "human": "L1",
    "ai": "L2",
    "unknown": "L1",
}


def choose_start(
    origin: Origin,
    cwe_family: str | None = None,
    policy: dict[str, Level] | None = None,
) -> Level:
    """Choose the starting context level based on provenance.

    Args:
        origin: Code provenance label (ai, human, unknown).
        cwe_family: Optional CWE family for policy-based overrides.
        policy: Override policy dict (origin -> level).
                Defaults to human→L1, ai→L2, unknown→L1.

    Returns:
        The starting context level.
    """
    p = policy if policy is not None else DEFAULT_POLICY
    return p.get(origin, "L1")


# ---------------------------------------------------------------------------
# Slot definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """A function slot for the experiment.

    Represents a target function to scan, with optional provenance
    metadata from P2.
    """

    slot_id: str
    """Function identifier (e.g. 'process_record@src/vuln.c')."""

    origin: Origin = "unknown"
    """Code provenance label."""

    cwe_family: str | None = None
    """Optional CWE family for policy-based level selection."""

    label: bool | None = None
    """Ground truth: True if vulnerable, False if safe, None if unknown."""


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotResult:
    """Result of running a single slot through the experiment."""

    slot_id: str
    level: Level
    origin: Origin
    finding: Finding
    context_tokens: int
    context_items: list[str]
    build_time_ms: float
    detect_time_ms: float


@dataclass
class RunResult:
    """Complete result of an experiment run.

    Contains all slot results plus metadata for reproducibility.
    """

    slot_results: list[SlotResult] = field(default_factory=list)
    config_hash: str = ""
    tokenizer_name: str = ""
    timestamp: str = ""
    total_slots: int = 0
    total_findings: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_build_time_ms: float = 0.0
    total_detect_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Run orchestrator
# ---------------------------------------------------------------------------


def run_experiment(
    slots: list[Slot],
    levels: list[Level] | None = None,
    detector: DetectorAdapter | None = None,
    counter: TokenCounter | None = None,
    resolver: SlotResolver | None = None,
    graph: CallGraph | None = None,
    index: RepoIndex | None = None,
    policy: dict[str, Level] | None = None,
    caps: dict[str, int] | None = None,
    runs_per_slot: int = 1,
) -> RunResult:
    """Run the experiment loop over a set of slots.

    For each slot:
      1. Determine start level via choose_start(origin, policy)
      2. Build context at the chosen level (or all specified levels)
      3. Run detection
      4. Collect results with timing metadata

    Args:
        slots: List of function slots to scan.
        levels: If set, override level selection and run all these levels
                for every slot. If None, use choose_start per slot.
        detector: Detector adapter. Defaults to FakeDetector.
        counter: Token counter. Defaults to tiktoken cl100k_base.
        resolver: SlotResolver for build_context.
        graph: CallGraph for L3 support.
        index: RepoIndex for L3 support.
        policy: Policy dict for choose_start.
        caps: Token cap overrides per level.
        runs_per_slot: Number of detection runs per (slot, level) pair.

    Returns:
        RunResult with all slot results and metadata.
    """
    if detector is None:
        detector = FakeDetector()
    if counter is None:
        counter = create_counter()

    # Build config hash for reproducibility
    config_str = (
        f"caps={caps}:policy={policy}:"
        f"tokenizer={counter.name}:runs={runs_per_slot}"
    )
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    result = RunResult(
        config_hash=config_hash,
        tokenizer_name=counter.name,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        total_slots=len(slots),
    )

    for slot in slots:
        # Determine levels to run
        if levels is not None:
            slot_levels = levels
        else:
            start = choose_start(slot.origin, slot.cwe_family, policy)
            slot_levels = [start]

        for level in slot_levels:
            for run_num in range(1, runs_per_slot + 1):
                try:
                    # Build context
                    t0 = time.perf_counter()
                    ctx = build_context(
                        slot.slot_id,
                        level,
                        resolver=resolver,
                        counter=counter,
                        caps=caps,
                        graph=graph,
                        index=index,
                    )
                    build_ms = (time.perf_counter() - t0) * 1000

                    # Run detection
                    t1 = time.perf_counter()
                    finding = detector.run(ctx, run_num)
                    detect_ms = (time.perf_counter() - t1) * 1000

                    slot_result = SlotResult(
                        slot_id=slot.slot_id,
                        level=level,
                        origin=slot.origin,
                        finding=finding,
                        context_tokens=ctx["tokens"],
                        context_items=ctx["items"],
                        build_time_ms=round(build_ms, 2),
                        detect_time_ms=round(detect_ms, 2),
                    )
                    result.slot_results.append(slot_result)

                    # Accumulate totals
                    if finding["verdict"]:
                        result.total_findings += 1
                    result.total_input_tokens += finding["input_tokens"]
                    result.total_output_tokens += finding["output_tokens"]
                    result.total_build_time_ms += build_ms
                    result.total_detect_time_ms += detect_ms

                except Exception as e:
                    error_msg = f"{slot.slot_id}@{level}:run{run_num}: {e}"
                    logger.error("Slot error: %s", error_msg)
                    result.errors.append(error_msg)

    logger.info(
        "Experiment complete: %d slots, %d results, %d findings, %d errors",
        len(slots),
        len(result.slot_results),
        result.total_findings,
        len(result.errors),
    )

    return result


# ---------------------------------------------------------------------------
# Token statistics (PRD task 5.3, 5.7)
# ---------------------------------------------------------------------------


def compute_token_stats(result: RunResult) -> dict[str, dict[str, float]]:
    """Compute per-level token statistics from a run result.

    Returns a dict of level -> {min, max, mean, median, count}.
    """
    from collections import defaultdict

    by_level: dict[str, list[int]] = defaultdict(list)
    for sr in result.slot_results:
        by_level[sr.level].append(sr.context_tokens)

    stats: dict[str, dict[str, float]] = {}
    for level, tokens in sorted(by_level.items()):
        sorted_tokens = sorted(tokens)
        n = len(sorted_tokens)
        mid = n // 2
        median = (
            sorted_tokens[mid]
            if n % 2 == 1
            else (sorted_tokens[mid - 1] + sorted_tokens[mid]) / 2
        )
        stats[level] = {
            "count": float(n),
            "min": float(min(sorted_tokens)),
            "max": float(max(sorted_tokens)),
            "mean": round(sum(sorted_tokens) / n, 1),
            "median": float(median),
        }

    return stats


# ---------------------------------------------------------------------------
# Escalation loop (PRD task 6.7)
# ---------------------------------------------------------------------------

_LEVEL_ORDER: list[Level] = ["L1", "L2", "L3"]


def _next_level(current: Level) -> Level | None:
    """Get the next level up, or None if already at max."""
    idx = _LEVEL_ORDER.index(current)
    if idx + 1 < len(_LEVEL_ORDER):
        return _LEVEL_ORDER[idx + 1]
    return None


def escalate_scan(
    slot_id: str,
    origin: Origin,
    detector: DetectorAdapter,
    counter: TokenCounter,
    resolver: SlotResolver | None = None,
    graph: CallGraph | None = None,
    index: RepoIndex | None = None,
    policy: dict[str, Level] | None = None,
    caps: dict[str, int] | None = None,
    tau: float = 0.7,
    max_level: Level = "L3",
    budget: int = 50000,
) -> list[SlotResult]:
    """Run detection with escalation.

    Starts at the policy-chosen level. If confidence < tau, escalates
    to the next level. Stops when confidence >= tau, max_level reached,
    or total tokens exceed budget.

    Args:
        slot_id: Function identifier.
        origin: Code provenance label.
        detector: Detector adapter.
        counter: Token counter.
        resolver: SlotResolver for build_context.
        graph: CallGraph for L3.
        index: RepoIndex for L3.
        policy: Policy dict for choose_start.
        caps: Token cap overrides per level.
        tau: Confidence threshold for escalation.
        max_level: Maximum level to escalate to.
        budget: Total token budget.

    Returns:
        List of SlotResults from each escalation step.
    """
    start = choose_start(origin, policy=policy)
    current_level: Level = start
    results: list[SlotResult] = []
    total_tokens = 0
    max_idx = _LEVEL_ORDER.index(max_level)

    while True:
        t0 = time.perf_counter()
        ctx = build_context(
            slot_id, current_level,
            resolver=resolver,
            counter=counter,
            caps=caps,
            graph=graph,
            index=index,
        )
        build_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        finding = detector.run(ctx, run=len(results) + 1)
        detect_ms = (time.perf_counter() - t1) * 1000

        sr = SlotResult(
            slot_id=slot_id,
            level=current_level,
            origin=origin,
            finding=finding,
            context_tokens=ctx["tokens"],
            context_items=ctx["items"],
            build_time_ms=round(build_ms, 2),
            detect_time_ms=round(detect_ms, 2),
        )
        results.append(sr)
        total_tokens += finding["input_tokens"]

        # Check stop conditions
        if finding["confidence"] >= tau:
            logger.info(
                "%s@%s: confidence %.2f >= tau %.2f, stopping",
                slot_id, current_level, finding["confidence"], tau,
            )
            break

        next_lvl = _next_level(current_level)
        if next_lvl is None or _LEVEL_ORDER.index(next_lvl) > max_idx:
            logger.info(
                "%s@%s: max level reached, stopping",
                slot_id, current_level,
            )
            break

        if total_tokens + (caps or {}).get(next_lvl, 15000) > budget:
            logger.info(
                "%s: budget %d would be exceeded, stopping",
                slot_id, budget,
            )
            break

        current_level = next_lvl
        logger.info(
            "%s: escalating to %s (confidence %.2f < tau %.2f)",
            slot_id, current_level, finding["confidence"], tau,
        )

    return results
