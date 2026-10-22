"""OriginScan CLI — Typer application.

Commands:
  originscan scan    — scan a diff for vulnerabilities
  originscan context — print context for a function at a given level
  originscan index   — build/refresh the repo index

See design.md §8.
"""

from __future__ import annotations

import logging

import typer

logger = logging.getLogger(__name__)

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
        ...,
        help="Path to a diff file, or a git range "
        "(e.g. origin/main...HEAD) resolved in --repo",
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
    import time
    from pathlib import Path

    from originscan.context.builders import PathResolver
    from originscan.context.callgraph import CallGraph
    from originscan.context.diff import map_hunks_to_functions, parse_diff
    from originscan.context.index import RepoIndex
    from originscan.context.parser import parse_file
    from originscan.context.tokens import create_counter
    from originscan.detectors import FakeDetector
    from originscan.policy import PolicyConfig, default_policy, load_policy
    from originscan.provenance.git import (
        GitDiffError,
        SubprocessGit,
        git_diff_range,
    )
    from originscan.provenance.reader import detect_origin
    from originscan.report.json_report import (
        generate_json_report,
        save_json_report,
    )
    from originscan.report.markdown_report import save_markdown_report
    from originscan.runner import RunResult, escalate_scan

    repo_path = Path(repo).resolve()

    # ── Validate --format ────────────────────────────────────────
    allowed_formats = {"json", "md"}
    requested_formats = {f.strip() for f in output_format.split(",")}
    invalid = requested_formats - allowed_formats
    if invalid:
        typer.echo(
            f"Invalid format(s): {', '.join(sorted(invalid))}. "
            f"Allowed: json, md",
            err=True,
        )
        raise typer.Exit(2)

    # ── Validate --budget ────────────────────────────────────────
    if budget is not None and budget <= 0:
        typer.echo("--budget must be a positive integer.", err=True)
        raise typer.Exit(2)

    # ── Load policy ──────────────────────────────────────────────
    pol: PolicyConfig
    if policy is not None:
        try:
            pol = load_policy(policy)
        except FileNotFoundError:
            typer.echo(f"Policy file not found: {policy}", err=True)
            raise typer.Exit(2) from None
    else:
        pol = default_policy()

    # ── Read diff (file path or git range) ────────────────────────
    diff_path = Path(diff)
    if diff_path.exists():
        diff_text = diff_path.read_text(encoding="utf-8")
    else:
        # Treat as a git range
        try:
            diff_text = git_diff_range(str(repo_path), diff)
        except GitDiffError as e:
            typer.echo(f"Cannot read diff: {e}", err=True)
            raise typer.Exit(2) from None

    # ── Parse diff and find affected functions ───────────────────
    hunks = parse_diff(diff_text)
    if not hunks:
        typer.echo("No hunks found in diff.")
        raise typer.Exit(0)

    # Build index and call graph
    typer.echo(f"Indexing {repo_path}...")
    idx = RepoIndex.build(repo_path)
    graph = CallGraph.build(idx)

    # Map hunks to functions — normalize symbol paths to match diff
    from dataclasses import replace as dc_replace

    affected_files = {h.file for h in hunks}
    all_symbols = []
    for f in sorted(affected_files):
        fp = repo_path / f
        if fp.exists():
            raw_syms = parse_file(fp)
            # Normalize file paths to relative (matching diff paths)
            for sym in raw_syms:
                try:
                    rel = Path(sym.file).relative_to(
                        repo_path.as_posix()
                    ).as_posix()
                except ValueError:
                    rel = f
                all_symbols.append(dc_replace(sym, file=rel))

    changed_funcs = map_hunks_to_functions(hunks, all_symbols)
    if not changed_funcs:
        typer.echo("No functions affected by diff.")
        raise typer.Exit(0)

    typer.echo(f"Found {len(changed_funcs)} affected function(s).")

    # ── Provenance + escalation per function ─────────────────────
    detector = FakeDetector()
    counter = create_counter()
    resolver = PathResolver()
    git = SubprocessGit(str(repo_path))

    effective_budget = budget if budget is not None else pol.escalation_budget

    run_result = RunResult(
        config_hash="",
        tokenizer_name=counter.name,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        total_slots=len(changed_funcs),
    )

    for cf in changed_funcs:
        # slot_id needs absolute path for PathResolver
        abs_file = (repo_path / cf.file).as_posix()
        slot_id = f"{cf.name}@{abs_file}"

        # 1. Provenance: detect origin
        try:
            commits = git.commits_for_lines(
                cf.file, cf.start_line, cf.end_line
            )
            prov = detect_origin(commits)
            origin = prov.origin
        except Exception:
            logger.warning(
                "Git metadata unavailable for %s, "
                "falling back to unknown",
                slot_id,
            )
            origin = "unknown"

        # 2. Start level from policy
        start_level = pol.choose_level(origin)

        typer.echo(
            f"  {cf.name} ({cf.file}): origin={origin}, "
            f"start={start_level}"
        )

        # 3. Escalation scan
        try:
            slot_results = escalate_scan(
                slot_id=slot_id,
                origin=origin,
                detector=detector,
                counter=counter,
                resolver=resolver,
                graph=graph,
                index=idx,
                policy=pol.levels,
                tau=pol.escalation_tau,
                max_level=pol.escalation_max_level,
                budget=effective_budget,
            )
            for sr in slot_results:
                run_result.slot_results.append(sr)
                if sr.finding["verdict"]:
                    run_result.total_findings += 1
                run_result.total_input_tokens += (
                    sr.finding["input_tokens"]
                )
                run_result.total_output_tokens += (
                    sr.finding["output_tokens"]
                )
                run_result.total_build_time_ms += sr.build_time_ms
                run_result.total_detect_time_ms += sr.detect_time_ms
        except Exception as e:
            error_msg = f"{slot_id}: {e}"
            logger.error("Scan error: %s", error_msg)
            run_result.errors.append(error_msg)
            typer.echo(
                f"  Error scanning {slot_id}: {e}", err=True
            )

    # ── Write reports ────────────────────────────────────────────
    out_dir = Path(out) if out is not None else Path("originscan_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    if "json" in requested_formats:
        json_path = save_json_report(
            run_result, out_dir / "report.json"
        )
        typer.echo(f"JSON report: {json_path}")

    if "md" in requested_formats:
        md_path = save_markdown_report(
            run_result, out_dir / "report.md"
        )
        typer.echo(f"Markdown report: {md_path}")

    # If no --out was given and format includes json, also print
    # to stdout for scripting
    if out is None and "json" in requested_formats:
        typer.echo(generate_json_report(run_result))

    # ── Summary to stdout ────────────────────────────────────────
    typer.echo(
        f"\nScan complete: {len(changed_funcs)} functions, "
        f"{run_result.total_findings} finding(s), "
        f"{run_result.total_input_tokens} tokens used."
    )

    if fail_on_findings and run_result.total_findings > 0:
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
        typer.echo(
            f"Invalid level: {level}. Must be L1, L2, or L3.", err=True
        )
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
        typer.echo(
            f"\n--- {ctx['tokens']} tokens, "
            f"{len(ctx['items'])} items ---"
        )
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
            typer.echo(
                f"  ({idx.files_failed} files failed to parse)"
            )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2) from e


if __name__ == "__main__":
    app()
