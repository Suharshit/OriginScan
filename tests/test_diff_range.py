"""Tests for Issue 4 — --diff accepts both file paths and git ranges."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from originscan.cli.main import app
from originscan.provenance.git import GitDiffError, git_diff_range

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MULTIFILE = FIXTURES / "multifile"


# ── Helper: create a temp git repo with a diff ──────────────────────


def _make_git_repo(tmp: Path) -> Path:
    """Create a tiny git repo with two commits for range-based diff."""
    repo = tmp / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init"], cwd=str(repo),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True, check=True,
    )

    # First commit
    src = repo / "hello.c"
    src.write_text(
        "int add(int a, int b) {\n    return a + b;\n}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "."], cwd=str(repo),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo), capture_output=True, check=True,
    )

    # Second commit — modify the function
    src.write_text(
        "int add(int a, int b) {\n"
        "    // added a comment\n"
        "    return a + b;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "."], cwd=str(repo),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add comment"],
        cwd=str(repo), capture_output=True, check=True,
    )

    return repo


# ── Tests: git_diff_range function ──────────────────────────────────


class TestGitDiffRange:
    def test_valid_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_git_repo(Path(tmp))
            diff_text = git_diff_range(str(repo), "HEAD~1...HEAD")
            assert "hello.c" in diff_text
            assert "added a comment" in diff_text

    def test_invalid_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_git_repo(Path(tmp))
            with pytest.raises(GitDiffError, match="git diff failed"):
                git_diff_range(str(repo), "nonexistent_branch...HEAD")

    def test_not_a_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(GitDiffError):
            git_diff_range(tmp, "HEAD~1...HEAD")


# ── Tests: CLI --diff flag ──────────────────────────────────────────


class TestDiffFlag:
    def test_diff_from_file(self, tmp_path: Path) -> None:
        """--diff with a file path works (existing behavior)."""
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(
            "diff --git a/utils.c b/utils.c\n"
            "--- a/utils.c\n"
            "+++ b/utils.c\n"
            "@@ -28,4 +28,5 @@ int compute_hash(Record* r) {\n"
            "     int hash = r->id * 31;\n"
            "     for (int i = 0; r->name[i]; i++) {\n"
            "         hash = hash * 31 + r->name[i];\n"
            "+        hash ^= (hash >> 16);\n"
            "     }\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["scan", "--diff", str(diff_file), "--repo", str(MULTIFILE)],
        )
        assert result.exit_code == 0

    def test_diff_from_git_range(self) -> None:
        """--diff with a git range resolves via git diff."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_git_repo(Path(tmp))
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan",
                    "--diff", "HEAD~1...HEAD",
                    "--repo", str(repo),
                    "--format", "md",
                    "--out", str(Path(tmp) / "out"),
                ],
            )
            assert result.exit_code == 0
            assert "affected function" in result.output.lower() or \
                   "no functions" in result.output.lower() or \
                   "scan complete" in result.output.lower()

    def test_diff_invalid_range(self) -> None:
        """--diff with invalid range gives clear error, exit 2."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_git_repo(Path(tmp))
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan",
                    "--diff", "invalid_branch...also_invalid",
                    "--repo", str(repo),
                ],
            )
            assert result.exit_code == 2
            assert "cannot read diff" in result.output.lower()

    def test_diff_not_git_repo(self) -> None:
        """--diff with range on a non-git dir gives clear error, exit 2."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan",
                    "--diff", "HEAD~1...HEAD",
                    "--repo", tmp,
                ],
            )
            assert result.exit_code == 2
