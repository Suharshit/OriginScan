"""OriginScan CLI — Typer application.

Commands:
  originscan scan    — scan a diff for vulnerabilities
  originscan context — print context for a function at a given level
  originscan index   — build/refresh the repo index

See design.md §8.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="originscan",
    help="OriginScan — vulnerability scanner that adapts context depth based on code provenance.",
    no_args_is_help=True,
)


@app.command()
def scan(
    repo: str = typer.Option(".", help="Path to the repository root"),
    diff: str = typer.Option(..., help="Diff file or git range (e.g. origin/main...HEAD)"),
    policy: str | None = typer.Option(None, help="Path to policy.yaml"),
    budget: int | None = typer.Option(None, help="Per-PR token budget cap"),
    out: str | None = typer.Option(None, help="Output directory for reports"),
    output_format: str = typer.Option(
        "json,md", "--format", help="Output formats (comma-separated: json, md)"
    ),
    fail_on_findings: bool = typer.Option(False, "--fail-on-findings", help="Exit 1 if findings"),
) -> None:
    """Scan a diff or PR for vulnerabilities."""
    # Implementation in Phase 6-7
    typer.echo("scan: not yet implemented (Phase 6)")
    raise typer.Exit(2)


@app.command()
def context(
    repo: str = typer.Option(".", help="Path to the repository root"),
    function: str = typer.Option(..., help="Function ID (e.g. func:foo@src/a.c:10-42)"),
    level: str = typer.Option(..., help="Context level: L1, L2, or L3"),
) -> None:
    """Print the context for a function at a given level."""
    # Implementation in Phase 3
    typer.echo("context: not yet implemented (Phase 3)")
    raise typer.Exit(2)


@app.command()
def index(
    repo: str = typer.Option(".", help="Path to the repository root"),
) -> None:
    """Build or refresh the repo index."""
    # Implementation in Phase 4
    typer.echo("index: not yet implemented (Phase 4)")
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
