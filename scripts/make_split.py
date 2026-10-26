"""Write data/split.csv from the SecRepoBench task file and report the dev share.

Rule (docs/decisions.md, 2026-10-26): a repo is dev if
SHA-256(lowercase owner/name) mod 5 == 0. Refuses to run once
``split.frozen`` is true in config/experiment.yaml.

Usage:
    python scripts/make_split.py [--tasks data/raw/secrepobench/code_completion.parquet]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

from originscan.exp.corpus import make_split, normalize_repo, write_split

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASKS = ROOT / "data" / "raw" / "secrepobench" / "code_completion.parquet"
CONFIG = ROOT / "config" / "experiment.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    args = parser.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    split_cfg = cfg["split"]
    out = ROOT / cfg["paths"]["split"]
    if split_cfg.get("frozen"):
        print(f"split is frozen in {CONFIG.name}; not rewriting {out}", file=sys.stderr)
        return 2

    tasks = pd.read_parquet(args.tasks, columns=["repo_addr"])
    repos = tasks["repo_addr"].map(normalize_repo)
    slots_per_repo = Counter(repos)
    if len(slots_per_repo) != tasks["repo_addr"].nunique():
        print("two repo addresses normalise to the same owner/name", file=sys.stderr)
        return 1

    split = make_split(slots_per_repo, split_cfg["modulus"], split_cfg["dev_remainder"])
    write_split(split, out)

    print(f"{'repo':<36} {'split':<5} {'slots':>5}")
    for repo, s in split.items():
        print(f"{repo:<36} {s:<5} {slots_per_repo[repo]:>5}")
    dev = [r for r, s in split.items() if s == "dev"]
    dev_slots = sum(slots_per_repo[r] for r in dev)
    n_repos, n_slots = len(split), sum(slots_per_repo.values())
    print()
    print(f"dev repos: {len(dev)}/{n_repos} ({len(dev) / n_repos:.1%})")
    print(f"dev slots: {dev_slots}/{n_slots} ({dev_slots / n_slots:.1%})")
    print(f"wrote {out.relative_to(ROOT)}  sha256={hashlib.sha256(out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
