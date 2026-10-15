"""Mockable git wrapper for provenance detection.

Provides a thin abstraction over ``git log`` and ``git blame`` so that
tests can inject synthetic git repos without touching the filesystem.

See PRD task 6.2 and design.md §6.

Public API:
    GitWrapper (protocol)
    SubprocessGit  — real git via subprocess
    MockGit        — in-memory fake for tests
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitInfo:
    """Metadata about a single git commit."""

    sha: str
    author_name: str
    author_email: str
    message: str
    trailers: list[str]  # e.g. ["Co-authored-by: bot[bot] <bot@github.com>"]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class GitWrapper(Protocol):
    """Abstraction over git operations for provenance detection."""

    def commits_for_lines(
        self, file: str, start_line: int, end_line: int
    ) -> list[CommitInfo]:
        """Get commits that last touched the given line range."""
        ...

    def file_log(self, file: str, max_commits: int = 50) -> list[CommitInfo]:
        """Get recent commits that touched a file."""
        ...


# ---------------------------------------------------------------------------
# Real implementation
# ---------------------------------------------------------------------------


class SubprocessGit:
    """Git wrapper using subprocess calls."""

    def __init__(self, repo_root: str = ".") -> None:
        self.repo_root = repo_root

    def commits_for_lines(
        self, file: str, start_line: int, end_line: int
    ) -> list[CommitInfo]:
        """Use ``git log -L`` to find commits touching specific lines."""
        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"-L{start_line},{end_line}:{file}",
                    "--format=%H%n%an%n%ae%n%B%n---END---",
                    "--no-patch",
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return self._parse_log_output(result.stdout)
        except subprocess.CalledProcessError:
            return []

    def file_log(self, file: str, max_commits: int = 50) -> list[CommitInfo]:
        """Use ``git log`` to get recent commits for a file."""
        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"-n{max_commits}",
                    "--format=%H%n%an%n%ae%n%B%n---END---",
                    "--", file,
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return self._parse_log_output(result.stdout)
        except subprocess.CalledProcessError:
            return []

    def _parse_log_output(self, output: str) -> list[CommitInfo]:
        """Parse the custom git log format."""
        commits: list[CommitInfo] = []
        blocks = output.split("---END---")

        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            if len(lines) < 3:
                continue

            sha = lines[0].strip()
            author_name = lines[1].strip()
            author_email = lines[2].strip()
            message = "\n".join(lines[3:]).strip()

            # Extract trailers (lines matching "Key: Value" at end of message)
            trailers = [
                line.strip()
                for line in message.split("\n")
                if _is_trailer(line.strip())
            ]

            commits.append(CommitInfo(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                message=message,
                trailers=trailers,
            ))

        return commits


# ---------------------------------------------------------------------------
# Mock implementation for tests
# ---------------------------------------------------------------------------


@dataclass
class MockGit:
    """In-memory git wrapper for testing provenance detection.

    Pre-loaded with commit data; no filesystem access.
    """

    # file -> list of commits
    _file_commits: dict[str, list[CommitInfo]] = field(default_factory=dict)
    # (file, start, end) -> list of commits
    _line_commits: dict[tuple[str, int, int], list[CommitInfo]] = field(
        default_factory=dict
    )

    def add_file_commits(
        self, file: str, commits: list[CommitInfo]
    ) -> None:
        """Pre-load commits for a file."""
        self._file_commits[file] = commits

    def add_line_commits(
        self, file: str, start: int, end: int, commits: list[CommitInfo]
    ) -> None:
        """Pre-load commits for specific lines."""
        self._line_commits[(file, start, end)] = commits

    def commits_for_lines(
        self, file: str, start_line: int, end_line: int
    ) -> list[CommitInfo]:
        key = (file, start_line, end_line)
        if key in self._line_commits:
            return self._line_commits[key]
        # Fall back to file-level commits
        return self._file_commits.get(file, [])

    def file_log(self, file: str, max_commits: int = 50) -> list[CommitInfo]:
        return self._file_commits.get(file, [])[:max_commits]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_trailer(line: str) -> bool:
    """Check if a line looks like a git trailer (Key: Value)."""
    if not line or ":" not in line:
        return False
    key = line.split(":")[0]
    # Trailers have a capitalized key with no spaces
    return (
        len(key) > 1
        and key[0].isupper()
        and " " not in key.split("-")[0]
    )
