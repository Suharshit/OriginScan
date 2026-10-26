"""Loaders for slots.csv / labels.csv / split.csv, plus CorpusResolver.

CorpusResolver implements context.builders.SlotResolver: human versions parse
the original file; AI versions parse a temp copy with the AI body swapped in.
P4's builders, parser and Finding are used as they are, not changed.

Phase 1 (resolver) and Phase 2 (slots, split).
"""

from __future__ import annotations

import csv
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from tree_sitter import Parser

from originscan.context.callgraph import CallGraph
from originscan.context.index import RepoIndex
from originscan.context.parser import detect_language, parse_source

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from tree_sitter import Language, Node

    from originscan.context.parser import Symbol
    from originscan.interfaces import Origin

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


# ---------------------------------------------------------------------------
# CorpusResolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionSource:
    """Where one version's code lives, as CorpusResolver needs it."""

    origin: Origin
    function: str
    """Target function name."""
    file: str
    """Repo-relative POSIX path (slots.csv ``file``). Used as ``Symbol.file``, so
    function IDs match a RepoIndex / CallGraph built over the same repo."""
    source_path: Path
    """The original source file on disk."""
    ai_body: str | None = None
    """AI-written function body, braces included. Required for AI versions only."""

    def __post_init__(self) -> None:
        if (self.origin == "ai") != (self.ai_body is not None):
            raise ValueError(
                f"{self.function}@{self.file}: ai_body is required for AI versions "
                f"and not allowed otherwise (origin={self.origin!r})"
            )
        if self.ai_body is not None:
            body = self.ai_body.strip()
            if not (body.startswith("{") and body.endswith("}")):
                raise ValueError(f"{self.function}@{self.file}: ai_body must be a {{...}} block")


class CorpusResolver:
    """SlotResolver for corpus versions, keyed by ``version_id``.

    Human versions parse the original file. AI versions write a temp copy of
    the file with the AI body swapped in (signature and the rest of the file
    unchanged) and parse that. Temp copies are removed by :meth:`close`.

    For L3, pass build_context the index and graph from :meth:`graphs_for`,
    not the repo's own: a graph built over the original repo does not see an
    AI body.
    """

    def __init__(self, versions: Mapping[str, VersionSource]) -> None:
        self._versions = dict(versions)
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        # version_id -> (base index it was built from, swapped index, graph)
        self._graphs: dict[str, tuple[RepoIndex, RepoIndex, CallGraph]] = {}

    def resolve(self, slot_id: str) -> tuple[Symbol, list[Symbol]]:
        """Return (target function, all symbols in its file) for a version_id."""
        version = self._version(slot_id)
        path = version.source_path if version.ai_body is None else self.swapped_copy(slot_id)
        symbols = parse_source(path.read_bytes(), _language(version), version.file)
        return _only_function(symbols, version), symbols

    def swapped_copy(self, version_id: str) -> Path:
        """Write (or reuse) the temp copy of an AI version's file and return its path."""
        version = self._version(version_id)
        if version.ai_body is None:
            raise ValueError(f"{version_id!r} is not an AI version")
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="originscan-corpus-")
        key = hashlib.sha256(version_id.encode("utf-8")).hexdigest()[:16]
        path = Path(self._tmp.name) / key / Path(version.file).name
        if not path.exists():
            source = version.source_path.read_bytes()
            path.parent.mkdir(parents=True)
            path.write_bytes(swap_body(source, _language(version), version, version.ai_body))
        return path

    def graphs_for(
        self, version_id: str, index: RepoIndex, graph: CallGraph
    ) -> tuple[RepoIndex, CallGraph]:
        """Index and call graph to pass to build_context for this version.

        *index* and *graph* are the repo's own, built at the version's commit.
        Human versions get them back unchanged, after checking the target is in
        the graph with the same text (catches an index from the wrong commit).
        AI versions get a copy of *index* with only their file's symbols
        swapped, and a CallGraph built from it, so L3 callers and callees come
        from the AI body. Built once per version and cached.
        """
        version = self._version(version_id)
        target, file_symbols = self.resolve(version_id)

        if version.ai_body is None:
            found = graph.get_symbol(graph.fn_id_for(target))
            if found is None or found.text != target.text:
                raise ValueError(
                    f"{version_id!r}: {version.function}@{version.file} is not in the "
                    "call graph as resolved; was the index built at this version's commit?"
                )
            return index, graph

        cached = self._graphs.get(version_id)
        if cached is not None and cached[0] is index:
            return cached[1], cached[2]

        if version.file not in index.symbols_by_file:
            raise ValueError(f"{version_id!r}: {version.file} is not in the repo index")
        by_file = dict(index.symbols_by_file)  # keeps file order, so name resolution is unchanged
        by_file[version.file] = file_symbols
        by_name: dict[str, list[Symbol]] = {}
        for symbols in by_file.values():
            for s in symbols:
                by_name.setdefault(s.name, []).append(s)
        swapped = RepoIndex(
            root=index.root,
            commit=f"{index.commit}+{version_id}",
            symbols_by_file=by_file,
            symbols_by_name=by_name,
            files_parsed=index.files_parsed,
            files_failed=index.files_failed,
            parse_warnings=index.parse_warnings,
        )
        swapped_graph = CallGraph.build(swapped)
        self._graphs[version_id] = (index, swapped, swapped_graph)
        return swapped, swapped_graph

    def close(self) -> None:
        """Remove all temp copies and cached graphs."""
        self._graphs.clear()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def __enter__(self) -> CorpusResolver:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _version(self, version_id: str) -> VersionSource:
        try:
            return self._versions[version_id]
        except KeyError:
            raise ValueError(f"unknown version_id {version_id!r}") from None


def swap_body(source: bytes, lang: Language, version: VersionSource, body: str) -> bytes:
    """Return *source* with the target function's ``{...}`` body replaced by *body*."""
    target = _only_function(parse_source(source, lang, version.file), version)
    node = _function_node(Parser(lang).parse(source).root_node, target)
    old = node.child_by_field_name("body") if node is not None else None
    if old is None:
        raise ValueError(f"{version.function}@{version.file}: function body not found")
    new = body.strip()
    if b"\r\n" in source:
        new = new.replace("\r\n", "\n").replace("\n", "\r\n")
    return source[: old.start_byte] + new.encode("utf-8") + source[old.end_byte :]


def _language(version: VersionSource) -> Language:
    lang = detect_language(Path(version.file))
    if lang is None:
        raise ValueError(f"unsupported file type: {version.file}")
    return lang


def _only_function(symbols: list[Symbol], version: VersionSource) -> Symbol:
    matches = [s for s in symbols if s.kind == "function" and s.name == version.function]
    if len(matches) != 1:
        raise ValueError(
            f"expected one definition of {version.function!r} in {version.file}, "
            f"found {len(matches)}"
        )
    return matches[0]


def _function_node(root: Node, target: Symbol) -> Node | None:
    """The function_definition node spanning exactly the target's lines."""
    stack = [root]
    while stack:
        node = stack.pop()
        if (
            node.type == "function_definition"
            and node.start_point[0] + 1 == target.start_line
            and node.end_point[0] + 1 == target.end_line
        ):
            return node
        stack.extend(node.children)
    return None
