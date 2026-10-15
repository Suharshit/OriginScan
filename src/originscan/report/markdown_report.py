"""Markdown report generator — RunResult → PR comment body.

Produces a Markdown summary table with a hidden ``<!-- originscan -->``
marker for comment updates, a disclaimer line, and per-function details.

See PRD task 7.3 and design.md §9.

Public API:
    generate_markdown_report(result) -> str
    save_markdown_report(result, path) -> Path
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from originscan.runner import RunResult


# Hidden marker for comment updates (PRD 7.3)
_MARKER = "<!-- originscan -->"


def generate_markdown_report(result: RunResult) -> str:
    """Generate a Markdown PR comment body from a RunResult.

    Includes:
      - Hidden marker for update-in-place
      - Summary statistics
      - Per-function findings table
      - Token cost breakdown
      - Disclaimer

    Returns:
        Markdown string ready for posting as a PR comment.
    """
    from originscan.runner import compute_token_stats

    lines: list[str] = []

    # Hidden marker
    lines.append(_MARKER)
    lines.append("")

    # Header
    lines.append("## OriginScan Results")
    lines.append("")

    # Summary
    findings_count = result.total_findings
    total_results = len(result.slot_results)
    emoji = "**:warning:**" if findings_count > 0 else ":white_check_mark:"
    lines.append(
        f"{emoji} **{findings_count} finding(s)** "
        f"across {total_results} function(s) scanned."
    )
    lines.append("")

    # Findings table
    if result.slot_results:
        lines.append("### Findings")
        lines.append("")
        lines.append(
            "| Function | File | Level | Verdict | CWE | Confidence | Tokens |"
        )
        lines.append("|---|---|---|---|---|---|---|")

        for sr in result.slot_results:
            # Extract function name and file from slot_id
            if "@" in sr.slot_id:
                func_name, file_path = sr.slot_id.split("@", 1)
            else:
                func_name = sr.slot_id
                file_path = ""

            verdict = ":x: Yes" if sr.finding["verdict"] else ":white_check_mark: No"
            cwe = sr.finding["cwe"] or "-"
            conf = f"{sr.finding['confidence']:.0%}"

            lines.append(
                f"| `{func_name}` | `{file_path}` | {sr.level} "
                f"| {verdict} | {cwe} | {conf} | {sr.context_tokens} |"
            )

        lines.append("")

    # Token cost breakdown
    stats = compute_token_stats(result)
    if stats:
        lines.append("### Token Usage")
        lines.append("")
        lines.append("| Level | Count | Min | Max | Mean | Median |")
        lines.append("|---|---|---|---|---|---|")
        for level, s in sorted(stats.items()):
            lines.append(
                f"| {level} | {int(s['count'])} | {int(s['min'])} "
                f"| {int(s['max'])} | {s['mean']:.0f} | {int(s['median'])} |"
            )
        lines.append("")
        lines.append(
            f"**Total:** {result.total_input_tokens} input tokens, "
            f"{result.total_output_tokens} output tokens"
        )
        lines.append("")

    # Timing
    lines.append(
        f"Build: {result.total_build_time_ms:.0f}ms | "
        f"Detect: {result.total_detect_time_ms:.0f}ms"
    )
    lines.append("")

    # Errors
    if result.errors:
        lines.append(
            f"<details><summary>:warning: {len(result.errors)} error(s)</summary>"
        )
        lines.append("")
        for err in result.errors:
            lines.append(f"- `{err}`")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Metadata
    lines.append(
        f"<sub>Config: `{result.config_hash}` | "
        f"Tokenizer: `{result.tokenizer_name}` | "
        f"{result.timestamp}</sub>"
    )
    lines.append("")

    # Disclaimer
    lines.append(
        "---\n"
        "*OriginScan is a research prototype. Findings are approximate "
        "and should be reviewed by a human.*"
    )

    return "\n".join(lines)


def save_markdown_report(result: RunResult, path: str | Path) -> Path:
    """Save a Markdown report to a file.

    Args:
        result: The RunResult to format.
        path: Output file path.

    Returns:
        The path the report was written to.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_markdown_report(result), encoding="utf-8")
    return out
