"""Loaders for slots.csv / labels.csv / split.csv, plus CorpusResolver.

CorpusResolver implements context.builders.SlotResolver: human versions parse
the original file; AI versions parse a temp copy with the AI body swapped in.

Phase 1 (resolver) and Phase 2 (slots, split).
"""

from __future__ import annotations

import csv
import hashlib
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

Split = Literal["dev", "test"]

SPLIT_COLUMNS = ("repo", "split")


# ---------------------------------------------------------------------------
# Repo names
# ---------------------------------------------------------------------------


def normalize_repo(addr: str) -> str:
    """Turn a repo address into lowercase ``owner/name``.

    The last two path segments are owner and name, so the host is dropped
    (``gitlab.gnome.org/GNOME/libxml2.git`` -> ``gnome/libxml2``). A single
    segment is used as both (``git.ffmpeg.org/ffmpeg.git`` -> ``ffmpeg/ffmpeg``).
    Already-normalised names pass through unchanged.

    This is the only form written to the ``repo`` column of slots.csv and
    split.csv (docs/decisions.md, 2026-10-26).
    """
    addr = addr.strip()
    path = urlparse(addr).path if "://" in addr else addr
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    segments = [s for s in path.split("/") if s]
    if not segments:
        raise ValueError(f"cannot get owner/name from repo address {addr!r}")
    name = segments[-1]
    owner = segments[-2] if len(segments) >= 2 else name
    return f"{owner}/{name}".lower()


# ---------------------------------------------------------------------------
# Dev/test split
# ---------------------------------------------------------------------------


def split_of(repo: str, modulus: int = 5, dev_remainder: int = 0) -> Split:
    """Return ``dev`` if SHA-256(normalised repo) mod ``modulus`` == ``dev_remainder``.

    Python's built-in ``hash()`` is randomised per process, so it is not used.
    """
    if repo != normalize_repo(repo):
        raise ValueError(f"repo {repo!r} is not normalised; use normalize_repo() first")
    digest = int(hashlib.sha256(repo.encode("utf-8")).hexdigest(), 16)
    return "dev" if digest % modulus == dev_remainder else "test"


def make_split(
    repos: Iterable[str], modulus: int = 5, dev_remainder: int = 0
) -> dict[str, Split]:
    """Split each normalised repo; sorted by repo name for a stable file."""
    return {r: split_of(r, modulus, dev_remainder) for r in sorted(set(repos))}


def write_split(split: dict[str, Split], path: Path) -> None:
    """Write split.csv (``repo``, ``split``), one row per repo, sorted by repo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(SPLIT_COLUMNS)
        for repo in sorted(split):
            writer.writerow((repo, split[repo]))


def read_split(path: Path) -> dict[str, Split]:
    """Read split.csv into ``{repo: split}``."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != SPLIT_COLUMNS:
            raise ValueError(f"{path}: expected columns {SPLIT_COLUMNS}, got {reader.fieldnames}")
        out: dict[str, Split] = {}
        for row in reader:
            value = row["split"]
            if value not in ("dev", "test"):
                raise ValueError(f"{path}: bad split {value!r} for repo {row['repo']!r}")
            out[row["repo"]] = value  # type: ignore[assignment]
        return out
