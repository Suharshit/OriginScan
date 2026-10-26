"""Integration tests for Issue 1 — scan uses provenance, policy, escalation."""

from __future__ import annotations

from pathlib import Path

from originscan.context.diff import parse_diff
from originscan.context.tokens import WhitespaceCounter
from originscan.detectors import FakeDetector
from originscan.policy import PolicyConfig, default_policy
from originscan.provenance.git import CommitInfo, MockGit
from originscan.provenance.reader import detect_origin
from originscan.runner import RunResult, escalate_scan

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MULTIFILE = FIXTURES / "multifile"


# ── Synthetic diff touching two functions in the multifile fixture ────

SYNTH_DIFF = """\
diff --git a/utils.c b/utils.c
--- a/utils.c
+++ b/utils.c
@@ -28,4 +28,5 @@ int compute_hash(Record* r) {
     int hash = r->id * 31;
     for (int i = 0; r->name[i]; i++) {
         hash = hash * 31 + r->name[i];
+        hash ^= (hash >> 16);
     }
diff --git a/main.c b/main.c
--- a/main.c
+++ b/main.c
@@ -14,4 +14,5 @@ void print_result(int code) {
     if (code == STATUS_OK) {
         log_message("Success");
     } else {
+        log_message("Error occurred");
         log_message("Failed");
"""


class TestScanProvenancePipeline:
    """Tests that the scan pipeline uses provenance + policy + escalation."""

    def test_provenance_detection_ai_vs_human(self) -> None:
        """AI commit → 'ai' origin; human commit → 'human' origin."""
        ai_commit = CommitInfo(
            sha="aaa111",
            author_name="copilot[bot]",
            author_email="copilot[bot]@users.noreply.github.com",
            message="AI-generated fix",
            trailers=["Co-authored-by: copilot[bot] <copilot@github.com>"],
        )
        human_commit = CommitInfo(
            sha="bbb222",
            author_name="Alice",
            author_email="alice@company.com",
            message="Manual fix",
            trailers=[],
        )

        ai_result = detect_origin([ai_commit])
        assert ai_result.origin == "ai"

        human_result = detect_origin([human_commit])
        assert human_result.origin == "human"

    def test_policy_level_selection(self) -> None:
        """Default policy is confidence-only: every origin starts at L1."""
        pol = default_policy()
        assert pol.choose_level("human") == "L1"
        assert pol.choose_level("ai") == "L1"
        assert pol.choose_level("unknown") == "L1"

    def test_escalation_ai_starts_at_l1_by_default(self) -> None:
        """AI-origin function starts at L1 via escalate_scan by default."""
        slot_id = f"compute_hash@{MULTIFILE / 'utils.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="ai",
            detector=FakeDetector(base_confidence=0.95),
            counter=WhitespaceCounter(),
            tau=0.7,
            max_level="L2",
        )
        assert len(results) >= 1
        assert results[0].level == "L1"  # default policy: all L1

    def test_escalation_ai_follows_policy(self) -> None:
        """escalate_scan starts at the level the policy sets for the origin."""
        slot_id = f"compute_hash@{MULTIFILE / 'utils.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="ai",
            detector=FakeDetector(base_confidence=0.95),
            counter=WhitespaceCounter(),
            policy={"human": "L1", "ai": "L2", "unknown": "L1"},
            tau=0.7,
            max_level="L2",
        )
        assert len(results) >= 1
        assert results[0].level == "L2"

    def test_escalation_human_starts_at_l1(self) -> None:
        """Human-origin function starts at L1 via escalate_scan."""
        slot_id = f"print_result@{MULTIFILE / 'main.c'}"
        results = escalate_scan(
            slot_id=slot_id,
            origin="human",
            detector=FakeDetector(base_confidence=0.95),
            counter=WhitespaceCounter(),
            tau=0.7,
            max_level="L2",
        )
        assert len(results) >= 1
        assert results[0].level == "L1"  # human starts at L1

    def test_integration_mock_provenance_in_scan(self) -> None:
        """Full integration: parse diff, provenance, policy → correct levels."""
        # Parse our synthetic diff
        hunks = parse_diff(SYNTH_DIFF)
        assert len(hunks) >= 2

        # Set up mock git with known commits per function
        git = MockGit()
        ai_commit = CommitInfo(
            sha="aaa111",
            author_name="copilot[bot]",
            author_email="copilot[bot]@users.noreply.github.com",
            message="AI fix",
            trailers=["Co-authored-by: copilot[bot] <copilot@github.com>"],
        )
        human_commit = CommitInfo(
            sha="bbb222",
            author_name="Alice",
            author_email="alice@company.com",
            message="Human fix",
            trailers=[],
        )

        # compute_hash is in utils.c lines 28-34 → AI commit
        git.add_line_commits("utils.c", 28, 34, [ai_commit])
        # print_result is in main.c lines 14-20 → human commit
        git.add_line_commits("main.c", 14, 20, [human_commit])

        default = default_policy()
        # An origin-aware policy, so the test shows origin reaching the level choice
        origin_aware = PolicyConfig(levels={"human": "L1", "ai": "L2", "unknown": "L1"})

        # Simulate what scan does: per function, detect origin, choose level
        origins = {}
        levels = {}
        default_levels = {}

        for file, start, end, name in [
            ("utils.c", 28, 34, "compute_hash"),
            ("main.c", 14, 20, "print_result"),
        ]:
            commits = git.commits_for_lines(file, start, end)
            prov = detect_origin(commits)
            origins[name] = prov.origin
            levels[name] = origin_aware.choose_level(prov.origin)
            default_levels[name] = default.choose_level(prov.origin)

        assert origins["compute_hash"] == "ai"
        assert origins["print_result"] == "human"
        assert levels["compute_hash"] == "L2"  # ai → L2 under the origin-aware policy
        assert levels["print_result"] == "L1"  # human → L1
        assert default_levels == {"compute_hash": "L1", "print_result": "L1"}

    def test_escalation_collects_into_run_result(self) -> None:
        """Escalation results can be collected into a RunResult."""
        slot_id = f"compute_hash@{MULTIFILE / 'utils.c'}"
        slot_results = escalate_scan(
            slot_id=slot_id,
            origin="ai",
            detector=FakeDetector(base_confidence=0.95),
            counter=WhitespaceCounter(),
            tau=0.7,
            max_level="L2",
        )

        run_result = RunResult(total_slots=1, tokenizer_name="whitespace")
        for sr in slot_results:
            run_result.slot_results.append(sr)
            if sr.finding["verdict"]:
                run_result.total_findings += 1
            run_result.total_input_tokens += sr.finding["input_tokens"]

        assert len(run_result.slot_results) >= 1
        assert run_result.total_input_tokens > 0

    def test_git_failure_falls_back_to_unknown(self) -> None:
        """When git metadata is unavailable, origin falls back to 'unknown'."""
        git = MockGit()
        # No commits registered — returns empty list
        commits = git.commits_for_lines("nonexistent.c", 1, 10)
        prov = detect_origin(commits)
        assert prov.origin == "unknown"
