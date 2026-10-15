"""Repo-wide symbol index with commit-keyed caching.

Walks source files, parses each with tree-sitter, and stores symbols
indexed by name and by file. Persists to disk keyed by commit hash
for fast reloads.

See design.md §4 (Index section).

Public API:
    RepoIndex.build(root, commit)  -> RepoIndex
    RepoIndex.symbols_by_file      -> dict[str, list[Symbol]]
    RepoIndex.symbols_by_name      -> dict[str, list[Symbol]]
    RepoIndex.all_symbols          -> list[Symbol]
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from originscan.context.parser import Symbol, parse_file

logger = logging.getLogger(__name__)

# Extensions we know how to parse
_PARSEABLE_EXTS = {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"}

# Default ignore globs
_DEFAULT_IGNORE = ["build/", "third_party/", "vendor/", ".git/", ".originscan/"]


# ---------------------------------------------------------------------------
# RepoIndex
# ---------------------------------------------------------------------------


@dataclass
class RepoIndex:
    """Repo-wide symbol index.

    Stores all parsed symbols indexed by file path and by name.
    Can be persisted to disk and reloaded if the commit matches.
    """

    root: str
    commit: str
    symbols_by_file: dict[str, list[Symbol]] = field(default_factory=dict)
    symbols_by_name: dict[str, list[Symbol]] = field(default_factory=dict)
    files_parsed: int = 0
    files_failed: int = 0
    parse_warnings: int = 0

    @property
    def all_symbols(self) -> list[Symbol]:
        """All symbols across all files, sorted by (file, start_line)."""
        result: list[Symbol] = []
        for syms in self.symbols_by_file.values():
            result.extend(syms)
        result.sort(key=lambda s: (s.file, s.start_line, s.name))
        return result

    def functions(self) -> list[Symbol]:
        """All function symbols."""
        return [s for s in self.all_symbols if s.kind == "function"]

    def get_function(self, name: str, file: str | None = None) -> Symbol | None:
        """Look up a function by name, optionally filtered by file."""
        candidates = self.symbols_by_name.get(name, [])
        for s in candidates:
            if s.kind != "function":
                continue
            if file is None or s.file == file:
                return s
        return None

    def get_file_symbols(self, file: str) -> list[Symbol]:
        """Get all symbols from a specific file."""
        return self.symbols_by_file.get(file, [])

    # -------------------------------------------------------------------
    # Builder
    # -------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        root: str | Path,
        commit: str | None = None,
        ignore_globs: list[str] | None = None,
    ) -> RepoIndex:
        """Index a repository by parsing all recognized source files.

        Args:
            root: Path to the repository root.
            commit: Git commit hash. If None, attempts ``git rev-parse HEAD``.
            ignore_globs: Directory/file patterns to skip.

        Returns:
            A populated RepoIndex.
        """
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise ValueError(f"Repository root is not a directory: {root_path}")

        if commit is None:
            commit = _get_commit_hash(root_path)

        if ignore_globs is None:
            ignore_globs = list(_DEFAULT_IGNORE)

        # Try loading from cache
        cached = cls._load_cache(root_path, commit)
        if cached is not None:
            logger.info("Loaded index from cache for commit %s", commit[:8])
            return cached

        logger.info("Building index for %s at commit %s", root_path, commit[:8])

        index = cls(root=str(root_path), commit=commit)

        # Walk source files
        for source_file in _walk_source_files(root_path, ignore_globs):
            rel_path = source_file.relative_to(root_path).as_posix()
            try:
                symbols = parse_file(source_file)
                # Update file paths to be relative
                symbols = [
                    Symbol(
                        kind=s.kind,
                        name=s.name,
                        file=rel_path,
                        start_line=s.start_line,
                        end_line=s.end_line,
                        text=s.text,
                        is_static=s.is_static,
                    )
                    for s in symbols
                ]
                index.symbols_by_file[rel_path] = symbols
                index.files_parsed += 1

                # Index by name
                for sym in symbols:
                    if sym.name not in index.symbols_by_name:
                        index.symbols_by_name[sym.name] = []
                    index.symbols_by_name[sym.name].append(sym)

            except Exception:
                logger.warning("Failed to parse %s", rel_path, exc_info=True)
                index.files_failed += 1

        logger.info(
            "Indexed %d files (%d failed), %d symbols",
            index.files_parsed,
            index.files_failed,
            len(index.all_symbols),
        )

        # Save to cache
        index._save_cache(root_path)

        return index

    # -------------------------------------------------------------------
    # Cache (persist to .originscan/index-<commit>.json)
    # -------------------------------------------------------------------

    @classmethod
    def _load_cache(cls, root: Path, commit: str) -> RepoIndex | None:
        """Try to load a cached index for the given commit."""
        cache_path = root / ".originscan" / f"index-{commit[:12]}.json"
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return cls._from_dict(data)
        except Exception:
            logger.warning("Failed to load cache %s", cache_path, exc_info=True)
            return None

    def _save_cache(self, root: Path) -> None:
        """Save the index to disk."""
        cache_dir = root / ".originscan"
        cache_dir.mkdir(exist_ok=True)
        cache_path = cache_dir / f"index-{self.commit[:12]}.json"
        try:
            data = self._to_dict()
            cache_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Saved index cache to %s", cache_path)
        except Exception:
            logger.warning("Failed to save cache", exc_info=True)

    def _to_dict(self) -> dict:
        """Serialize the index to a dict."""
        files: dict[str, list[dict]] = {}
        for fpath, syms in self.symbols_by_file.items():
            files[fpath] = [
                {
                    "kind": s.kind,
                    "name": s.name,
                    "file": s.file,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "text": s.text,
                    "is_static": s.is_static,
                }
                for s in syms
            ]
        return {
            "root": self.root,
            "commit": self.commit,
            "files": files,
            "files_parsed": self.files_parsed,
            "files_failed": self.files_failed,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> RepoIndex:
        """Deserialize an index from a dict."""
        index = cls(
            root=data["root"],
            commit=data["commit"],
            files_parsed=data.get("files_parsed", 0),
            files_failed=data.get("files_failed", 0),
        )
        for fpath, sym_dicts in data.get("files", {}).items():
            symbols = [
                Symbol(
                    kind=d["kind"],
                    name=d["name"],
                    file=d["file"],
                    start_line=d["start_line"],
                    end_line=d["end_line"],
                    text=d["text"],
                    is_static=d.get("is_static", False),
                )
                for d in sym_dicts
            ]
            index.symbols_by_file[fpath] = symbols
            for sym in symbols:
                if sym.name not in index.symbols_by_name:
                    index.symbols_by_name[sym.name] = []
                index.symbols_by_name[sym.name].append(sym)
        return index


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_commit_hash(root: Path) -> str:
    """Get the current HEAD commit hash, or a fallback hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        # Not a git repo or git not available — use a hash of the root path
        return hashlib.sha256(str(root).encode()).hexdigest()


def _walk_source_files(root: Path, ignore_globs: list[str]) -> list[Path]:
    """Walk the repo and collect parseable source files.

    Skips directories matching ignore_globs. Returns sorted list for
    deterministic indexing.
    """
    files: list[Path] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        # Check if any parent directory matches an ignore glob
        rel = path.relative_to(root).as_posix()
        skip = False
        for glob in ignore_globs:
            if fnmatch.fnmatch(rel, glob + "*") or fnmatch.fnmatch(
                rel, "*/" + glob + "*"
            ):
                skip = True
                break
            # Also check directory components
            for part in path.relative_to(root).parts[:-1]:
                if fnmatch.fnmatch(part + "/", glob):
                    skip = True
                    break
            if skip:
                break

        if skip:
            continue

        if path.suffix.lower() in _PARSEABLE_EXTS:
            files.append(path)

    return files
