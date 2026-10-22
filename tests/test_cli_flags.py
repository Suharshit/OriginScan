"""Tests for Issue 2 — CLI flag validation and report writing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from originscan.cli.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MULTIFILE = FIXTURES / "multifile"

# A minimal diff that touches a function in the multifile fixture
MINIMAL_DIFF = """\
diff --git a/utils.c b/utils.c
--- a/utils.c
+++ b/utils.c
@@ -28,4 +28,5 @@ int compute_hash(Record* r) {
     int hash = r->id * 31;
     for (int i = 0; r->name[i]; i++) {
         hash = hash * 31 + r->name[i];
+        hash ^= (hash >> 16);
     }
"""


@pytest.fixture()
def diff_file(tmp_path: Path) -> Path:
    """Write a minimal diff file for CLI testing."""
    p = tmp_path / "test.diff"
    p.write_text(MINIMAL_DIFF, encoding="utf-8")
    return p


class TestFormatFlag:
    def test_valid_json(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "json",
            ],
        )
        assert result.exit_code == 0

    def test_valid_md(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "md",
            ],
        )
        assert result.exit_code == 0

    def test_valid_json_md(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "json,md",
            ],
        )
        assert result.exit_code == 0

    def test_invalid_format(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "xml",
            ],
        )
        assert result.exit_code == 2
        assert "Invalid format" in result.output

    def test_invalid_mixed_format(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "json,html",
            ],
        )
        assert result.exit_code == 2
        assert "html" in result.output


class TestBudgetFlag:
    def test_valid_budget(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--budget", "10000",
            ],
        )
        assert result.exit_code == 0

    def test_negative_budget(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--budget", "-1",
            ],
        )
        assert result.exit_code == 2
        assert "positive" in result.output

    def test_zero_budget(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--budget", "0",
            ],
        )
        assert result.exit_code == 2


class TestPolicyFlag:
    def test_missing_policy_file(self, diff_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--policy", "/nonexistent/policy.yaml",
            ],
        )
        assert result.exit_code == 2
        assert "not found" in result.output

    def test_valid_policy(self, diff_file: Path, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(
            "levels:\n  human: L1\n  ai: L3\n"
            "escalation:\n  tau: 0.8\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--policy", str(policy_file),
            ],
        )
        assert result.exit_code == 0


class TestOutFlag:
    def test_writes_json_report(self, diff_file: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", tmp,
                    "--format", "json",
                ],
            )
            assert result.exit_code == 0
            report_path = Path(tmp) / "report.json"
            assert report_path.exists()
            data = json.loads(
                report_path.read_text(encoding="utf-8")
            )
            assert "results" in data

    def test_writes_md_report(self, diff_file: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", tmp,
                    "--format", "md",
                ],
            )
            assert result.exit_code == 0
            report_path = Path(tmp) / "report.md"
            assert report_path.exists()
            content = report_path.read_text(encoding="utf-8")
            assert "<!-- originscan -->" in content

    def test_writes_both_reports(self, diff_file: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", tmp,
                    "--format", "json,md",
                ],
            )
            assert result.exit_code == 0
            assert (Path(tmp) / "report.json").exists()
            assert (Path(tmp) / "report.md").exists()

    def test_default_out_dir(self, diff_file: Path) -> None:
        """When --out is omitted, reports go to originscan_out/."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
            ],
        )
        assert result.exit_code == 0
        assert "originscan_out" in result.output

    def test_creates_out_dir(self, diff_file: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "deep" / "nested"
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", str(nested),
                ],
            )
            assert result.exit_code == 0
            assert nested.exists()


class TestJsonStdout:
    def test_no_json_to_stdout_when_out_given(
        self, diff_file: Path
    ) -> None:
        """When --out is given, JSON should NOT be dumped to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", tmp,
                    "--format", "json",
                ],
            )
            assert result.exit_code == 0
            # The full JSON blob should NOT be in stdout
            assert '"originscan_version"' not in result.output


class TestReportForAction:
    """Issue 3: CLI must produce report.md at the path the Action reads."""

    def test_default_out_produces_report_md(
        self, diff_file: Path, tmp_path: Path
    ) -> None:
        """Scan writes report.md to the output directory."""
        out_dir = tmp_path / "originscan_out"
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scan", "--diff", str(diff_file),
                "--repo", str(MULTIFILE),
                "--format", "md",
                "--out", str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert out_dir.exists()
        report_md = out_dir / "report.md"
        assert report_md.exists()
        content = report_md.read_text(encoding="utf-8")
        assert "<!-- originscan -->" in content

    def test_explicit_out_produces_report_md(
        self, diff_file: Path
    ) -> None:
        """Scan with explicit --out writes report.md there."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "scan", "--diff", str(diff_file),
                    "--repo", str(MULTIFILE),
                    "--out", tmp,
                    "--format", "json,md",
                ],
            )
            assert result.exit_code == 0
            assert (Path(tmp) / "report.md").exists()
            assert (Path(tmp) / "report.json").exists()

            # report.md must contain the originscan marker
            md = (Path(tmp) / "report.md").read_text(encoding="utf-8")
            assert "<!-- originscan -->" in md
