"""Tests for diff parser, provenance reader, and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.diff import (
    DiffHunk,
    map_hunks_to_functions,
    parse_diff,
)
from originscan.context.parser import Symbol
from originscan.provenance.git import CommitInfo, MockGit
from originscan.provenance.reader import detect_origin

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# -----------------------------------------------------------------------
# Sample diffs
# -----------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/src/utils.c b/src/utils.c
--- a/src/utils.c
+++ b/src/utils.c
@@ -10,6 +10,8 @@ void log_message(const char* msg) {
     printf("%s\\n", msg);
 }

+int new_helper(int x) {
+    return x * 2;
+}
+
 int process(int x) {
@@ -25,3 +27,4 @@ int process(int x) {
     int result = x + 1;
+    result = new_helper(result);
     return result;
 }
"""

DELETED_ONLY_DIFF = """\
diff --git a/src/old.c b/src/old.c
--- a/src/old.c
+++ b/src/old.c
@@ -5,4 +5,2 @@ void foo() {
     int x = 1;
-    int y = 2;
-    int z = 3;
     return;
"""


# -----------------------------------------------------------------------
# Diff parsing
# -----------------------------------------------------------------------


class TestParseDiff:
    def test_parses_hunks(self) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        assert len(hunks) >= 2
        assert all(isinstance(h, DiffHunk) for h in hunks)

    def test_extracts_file_path(self) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        for h in hunks:
            assert h.file == "src/utils.c"

    def test_extracts_added_lines(self) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        all_added = []
        for h in hunks:
            all_added.extend(h.added_lines)
        assert len(all_added) > 0

    def test_extracts_deleted_lines(self) -> None:
        hunks = parse_diff(DELETED_ONLY_DIFF)
        all_deleted = []
        for h in hunks:
            all_deleted.extend(h.deleted_lines)
        assert len(all_deleted) >= 2

    def test_empty_diff(self) -> None:
        hunks = parse_diff("")
        assert hunks == []

    def test_hunk_start_lines(self) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        for h in hunks:
            assert h.new_start > 0
            assert h.old_start > 0


# -----------------------------------------------------------------------
# Hunk → function mapping
# -----------------------------------------------------------------------


class TestMapHunks:
    @pytest.fixture()
    def symbols(self) -> list[Symbol]:
        return [
            Symbol(
                kind="function", name="log_message",
                file="src/utils.c", start_line=8, end_line=11,
                text="void log_message(const char* msg) {\n  printf(...);\n}",
            ),
            Symbol(
                kind="function", name="new_helper",
                file="src/utils.c", start_line=13, end_line=15,
                text="int new_helper(int x) {\n  return x * 2;\n}",
            ),
            Symbol(
                kind="function", name="process",
                file="src/utils.c", start_line=17, end_line=32,
                text="int process(int x) {\n  ...\n}",
            ),
        ]

    def test_maps_modified_function(self, symbols: list[Symbol]) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        changed = map_hunks_to_functions(hunks, symbols)
        names = [cf.name for cf in changed]
        assert "process" in names or "new_helper" in names

    def test_change_types(self, symbols: list[Symbol]) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        changed = map_hunks_to_functions(hunks, symbols)
        types = {cf.change_type for cf in changed}
        assert types.issubset({"modified", "added", "near_change"})

    def test_no_functions_no_results(self) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        changed = map_hunks_to_functions(hunks, [])
        assert changed == []

    def test_deterministic(self, symbols: list[Symbol]) -> None:
        hunks = parse_diff(SAMPLE_DIFF)
        r1 = map_hunks_to_functions(hunks, symbols)
        r2 = map_hunks_to_functions(hunks, symbols)
        assert r1 == r2


# -----------------------------------------------------------------------
# Git mock
# -----------------------------------------------------------------------


class TestMockGit:
    def test_file_log(self) -> None:
        git = MockGit()
        commit = CommitInfo(
            sha="abc123", author_name="Dev",
            author_email="dev@example.com",
            message="fix bug", trailers=[],
        )
        git.add_file_commits("src/a.c", [commit])
        result = git.file_log("src/a.c")
        assert len(result) == 1
        assert result[0].sha == "abc123"

    def test_line_commits(self) -> None:
        git = MockGit()
        commit = CommitInfo(
            sha="def456", author_name="Bot[bot]",
            author_email="bot@github.com",
            message="auto fix", trailers=[],
        )
        git.add_line_commits("src/a.c", 10, 20, [commit])
        result = git.commits_for_lines("src/a.c", 10, 20)
        assert len(result) == 1

    def test_empty_result(self) -> None:
        git = MockGit()
        assert git.file_log("nonexistent.c") == []
        assert git.commits_for_lines("nonexistent.c", 1, 5) == []


# -----------------------------------------------------------------------
# Provenance reader
# -----------------------------------------------------------------------


class TestProvenanceReader:
    def test_human_commits(self) -> None:
        commits = [
            CommitInfo(
                sha="aaa111", author_name="Alice Developer",
                author_email="alice@company.com",
                message="Fix buffer overflow", trailers=[],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin == "human"
        assert result.confidence > 0

    def test_bot_author(self) -> None:
        commits = [
            CommitInfo(
                sha="bbb222", author_name="dependabot[bot]",
                author_email="dependabot[bot]@users.noreply.github.com",
                message="Bump library", trailers=[],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin == "ai"
        assert len(result.evidence) > 0

    def test_coauthored_by_bot(self) -> None:
        commits = [
            CommitInfo(
                sha="ccc333", author_name="Dev",
                author_email="dev@example.com",
                message="Fix with help",
                trailers=[
                    "Co-authored-by: copilot[bot] <copilot@github.com>"
                ],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin == "ai"
        assert any("co-author" in e.lower() or "bot" in e.lower()
                    for e in result.evidence)

    def test_ai_tool_trailer(self) -> None:
        commits = [
            CommitInfo(
                sha="ddd444", author_name="Dev",
                author_email="dev@example.com",
                message="Generate code",
                trailers=["Generated-by: GitHub Copilot"],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin == "ai"

    def test_unknown_no_commits(self) -> None:
        result = detect_origin([])
        assert result.origin == "unknown"

    def test_known_agent_name(self) -> None:
        commits = [
            CommitInfo(
                sha="eee555", author_name="custom-agent",
                author_email="agent@tool.com",
                message="Auto-generated",
                trailers=[],
            ),
        ]
        result = detect_origin(commits, agent_names=["custom-agent"])
        assert result.origin == "ai"

    def test_squash_no_metadata(self) -> None:
        """Squashed commit with no metadata -> unknown or human."""
        commits = [
            CommitInfo(
                sha="fff666", author_name="Unknown Dev",
                author_email="unknown@company.com",
                message="squashed commit",
                trailers=[],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin == "human"

    def test_mixed_signals(self) -> None:
        commits = [
            CommitInfo(
                sha="aaa", author_name="Human",
                author_email="h@c.com",
                message="human commit", trailers=[],
            ),
            CommitInfo(
                sha="bbb", author_name="bot[bot]",
                author_email="bot@github.com",
                message="bot commit", trailers=[],
            ),
        ]
        result = detect_origin(commits)
        assert result.origin in ("ai", "human")
        assert len(result.evidence) > 0


# -----------------------------------------------------------------------
# CLI tests with CliRunner
# -----------------------------------------------------------------------


class TestCLI:
    def test_help(self) -> None:
        from typer.testing import CliRunner

        from originscan.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "OriginScan" in result.output

    def test_context_command(self) -> None:
        from typer.testing import CliRunner

        from originscan.cli.main import app

        runner = CliRunner()
        slot = f"process_record@{FIXTURES / 'simple.c'}"
        result = runner.invoke(
            app, ["context", "--function", slot, "--level", "L1"]
        )
        assert result.exit_code == 0
        assert "process_record" in result.output

    def test_context_invalid_level(self) -> None:
        from typer.testing import CliRunner

        from originscan.cli.main import app

        runner = CliRunner()
        slot = f"process_record@{FIXTURES / 'simple.c'}"
        result = runner.invoke(
            app, ["context", "--function", slot, "--level", "L9"]
        )
        assert result.exit_code == 2

    def test_index_command(self) -> None:
        from typer.testing import CliRunner

        from originscan.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["index", "--repo", str(FIXTURES / "multifile")]
        )
        assert result.exit_code == 0
        assert "symbols indexed" in result.output

    def test_scan_no_diff_file(self) -> None:
        from typer.testing import CliRunner

        from originscan.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["scan", "--diff", "nonexistent.diff"]
        )
        assert result.exit_code == 2
