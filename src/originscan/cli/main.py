"""OriginScan CLI — Typer application.

Commands:
  originscan scan    — scan a diff for vulnerabilities
  originscan context — print context for a function at a given level
  originscan index   — build/refresh the repo index

See design.md §8.
"""

from __future__ import annotations

import json

import typer

app = typer.Typer(
    name="originscan",
    help=(
        "OriginScan -- vulnerability scanner that adapts "
        "context depth based on code provenance."
    ),
    no_args_is_help=True,
)


@app.command()
def scan(
    repo: str = typer.Option(".", help="Path to the repository root"),
    diff: str = typer.Option(
        ..., help="Diff file or git range (e.g. origin/main...HEAD)"
    ),
    policy: str | None = typer.Option(None, help="Path to policy.yaml"),
    budget: int | None = typer.Option(
        None, help="Per-PR token budget cap"
    ),
    out: str | None = typer.Option(
        None, help="Output directory for reports"
    ),
    output_format: str = typer.Option(
        "json,md", "--format",
        help="Output formats (comma-separated: json, md)",
    ),
    fail_on_findings: bool = typer.Option(
        False, "--fail-on-findings", help="Exit 1 if findings"
    ),
) -> None:
    """Scan a diff or PR for vulnerabilities."""
    from pathlib import Path

    from originscan.context.builders import PathResolver, build_context
    from originscan.context.callgraph import CallGraph
    from originscan.context.diff import map_hunks_to_functions, parse_diff
    from originscan.context.index import RepoIndex
    from originscan.context.parser import parse_file
    from originscan.detectors import FakeDetector
    from originscan.runner import choose_start

    repo_path = Path(repo).resolve()

    # Read diff
    diff_path = Path(diff)
    if diff_path.exists():
        diff_text = diff_path.read_text(encoding="utf-8")
    else:
        typer.echo(f"Diff file not found: {diff}", err=True)
        raise typer.Exit(2)

    # Parse diff and find affected functions
    hunks = parse_diff(diff_text)
    if not hunks:
        typer.echo("No hunks found in diff.")
        raise typer.Exit(0)

    # Build index
    typer.echo(f"Indexing {repo_path}...")
    idx = RepoIndex.build(repo_path)
    graph = CallGraph.build(idx)

    # Map hunks to functions
    affected_files = {h.file for h in hunks}
    all_symbols = []
    for f in affected_files:
        fp = repo_path / f
        if fp.exists():
            all_symbols.extend(parse_file(fp))

    changed_funcs = map_hunks_to_functions(hunks, all_symbols)
    if not changed_funcs:
        typer.echo("No functions affected by diff.")
        raise typer.Exit(0)

    typer.echo(f"Found {len(changed_funcs)} affected function(s).")

    # Scan each function
    detector = FakeDetector()
    findings_count = 0
    results = []

    for cf in changed_funcs:
        slot_id = f"{cf.name}@{cf.file}"
        level = choose_start("unknown", policy=None)

        try:
            ctx = build_context(
                slot_id, level,
                resolver=PathResolver(),
                graph=graph, index=idx,
            )
            finding = detector.run(ctx, run=1)
            results.append({
                "function": cf.name,
                "file": cf.file,
                "level": level,
                "change_type": cf.change_type,
                "verdict": finding["verdict"],
                "cwe": finding["cwe"],
                "confidence": finding["confidence"],
                "tokens": ctx["tokens"],
            })
            if finding["verdict"]:
                findings_count += 1
        except Exception as e:
            typer.echo(f"  Error scanning {slot_id}: {e}", err=True)

    # Output results
    if "json" in output_format:
        typer.echo(json.dumps(results, indent=2))

    typer.echo(
        f"\nScan complete: {len(results)} functions, "
        f"{findings_count} finding(s)."
    )

    if fail_on_findings and findings_count > 0:
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command()
def context(
    function: str = typer.Option(
        ..., help="Function ID (e.g. func_name@path/to/file.c)"
    ),
    level: str = typer.Option("L1", help="Context level: L1, L2, or L3"),
    repo: str = typer.Option(".", help="Path to the repository root"),
) -> None:
    """Print the context for a function at a given level."""
    from originscan.context.builders import PathResolver, build_context
    from originscan.context.callgraph import CallGraph
    from originscan.context.index import RepoIndex

    if level not in ("L1", "L2", "L3"):
        typer.echo(f"Invalid level: {level}. Must be L1, L2, or L3.", err=True)
        raise typer.Exit(2)

    try:
        graph = None
        idx = None
        if level == "L3":
            from pathlib import Path

            idx = RepoIndex.build(Path(repo).resolve())
            graph = CallGraph.build(idx)

        ctx = build_context(
            function, level,  # type: ignore[arg-type]
            resolver=PathResolver(),
            graph=graph, index=idx,
        )
        typer.echo(ctx["text"])
        typer.echo(f"\n--- {ctx['tokens']} tokens, {len(ctx['items'])} items ---")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2) from e


@app.command()
def index(
    repo: str = typer.Option(".", help="Path to the repository root"),
) -> None:
    """Build or refresh the repo index."""
    from pathlib import Path

    from originscan.context.index import RepoIndex

    repo_path = Path(repo).resolve()
    typer.echo(f"Indexing {repo_path}...")

    try:
        idx = RepoIndex.build(repo_path)
        typer.echo(
            f"Done: {idx.files_parsed} files, "
            f"{len(idx.all_symbols)} symbols indexed."
        )
        if idx.files_failed > 0:
            typer.echo(f"  ({idx.files_failed} files failed to parse)")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2) from e


if __name__ == "__main__":
    app()
