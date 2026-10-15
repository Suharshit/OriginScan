"""Unified diff parser — maps new-side hunks to changed functions.

Parses unified diff format (``diff -u`` / ``git diff``) and identifies
which functions were modified, added, or are near changes.

See PRD task 6.1 and design.md §7.

Public API:
    parse_diff(diff_text)       -> list[DiffHunk]
    map_hunks_to_functions(hunks, symbols) -> list[ChangedFunction]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiffHunk:
    """A single hunk from a unified diff."""

    file: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: list[int]
    deleted_lines: list[int]
    context_text: str  # Raw hunk text


@dataclass(frozen=True)
class ChangedFunction:
    """A function affected by a diff hunk."""

    name: str
    file: str
    start_line: int
    end_line: int
    change_type: str  # "modified", "added", "near_change"
    hunk_lines: list[int]  # Lines from the diff that fall within this function


# ---------------------------------------------------------------------------
# Diff parsing
# ---------------------------------------------------------------------------

# Matches: --- a/path/to/file.c or --- /dev/null
_DIFF_FILE_OLD = re.compile(r"^--- (?:a/)?(.+)$")
_DIFF_FILE_NEW = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
# Matches: @@ -old_start,old_count +new_start,new_count @@
_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


def parse_diff(diff_text: str) -> list[DiffHunk]:
    """Parse a unified diff into a list of DiffHunk objects.

    Handles standard ``git diff`` output with ``---``/``+++``/``@@`` markers.

    Args:
        diff_text: Full unified diff text.

    Returns:
        List of DiffHunk objects, one per hunk.
    """
    hunks: list[DiffHunk] = []
    lines = diff_text.split("\n")
    current_file = ""
    i = 0

    while i < len(lines):
        line = lines[i]

        # New file header
        new_match = _DIFF_FILE_NEW.match(line)
        if new_match:
            current_file = new_match.group(1)
            if current_file == "/dev/null":
                current_file = ""
            i += 1
            continue

        # Old file header (skip, we use the new path)
        if _DIFF_FILE_OLD.match(line):
            i += 1
            continue

        # Hunk header
        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match and current_file:
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2) or "1")
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4) or "1")

            # Collect hunk body
            added_lines: list[int] = []
            deleted_lines: list[int] = []
            hunk_lines: list[str] = [line]
            new_line = new_start
            old_line = old_start
            i += 1

            while i < len(lines):
                bline = lines[i]
                if bline.startswith("+") and not bline.startswith("+++"):
                    added_lines.append(new_line)
                    new_line += 1
                elif bline.startswith("-") and not bline.startswith("---"):
                    deleted_lines.append(old_line)
                    old_line += 1
                elif bline.startswith(" "):
                    new_line += 1
                    old_line += 1
                elif bline.startswith("@@") or bline.startswith("diff "):
                    break
                elif bline.startswith("\\"):
                    # "\ No newline at end of file"
                    pass
                else:
                    # Unknown line or end of hunk
                    if not bline.strip():
                        # Could be empty context line
                        new_line += 1
                        old_line += 1
                    else:
                        break
                hunk_lines.append(bline)
                i += 1

            hunks.append(DiffHunk(
                file=current_file,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                added_lines=added_lines,
                deleted_lines=deleted_lines,
                context_text="\n".join(hunk_lines),
            ))
            continue

        i += 1

    return hunks


# ---------------------------------------------------------------------------
# Hunk → function mapping
# ---------------------------------------------------------------------------


def map_hunks_to_functions(
    hunks: list[DiffHunk],
    symbols: list,  # list[Symbol] — avoid circular import
) -> list[ChangedFunction]:
    """Map diff hunks to the functions they affect.

    A function is affected if:
      - Any added line falls within [start_line, end_line] → "modified"
      - The function didn't exist before (all lines are added) → "added"
      - A change is within 3 lines of the function boundary → "near_change"

    Args:
        hunks: Parsed diff hunks.
        symbols: All symbols from the affected file(s).

    Returns:
        List of ChangedFunction objects, deduplicated by (name, file).
    """
    functions = [s for s in symbols if s.kind == "function"]
    result: list[ChangedFunction] = []
    seen: set[tuple[str, str]] = set()

    near_margin = 3  # Lines of proximity to count as "near"

    for hunk in hunks:
        hunk_file = hunk.file
        all_changed = set(hunk.added_lines)

        for func in functions:
            if func.file != hunk_file:
                continue

            key = (func.name, func.file)
            if key in seen:
                continue

            # Lines within the function
            func_lines = set(range(func.start_line, func.end_line + 1))
            overlap = all_changed & func_lines

            if overlap:
                # Determine if this is a new function or a modification
                if len(overlap) >= (func.end_line - func.start_line + 1):
                    change_type = "added"
                else:
                    change_type = "modified"
                seen.add(key)
                result.append(ChangedFunction(
                    name=func.name,
                    file=func.file,
                    start_line=func.start_line,
                    end_line=func.end_line,
                    change_type=change_type,
                    hunk_lines=sorted(overlap),
                ))
            else:
                # Check if change is near the function
                expanded = set(range(
                    func.start_line - near_margin,
                    func.end_line + near_margin + 1,
                ))
                near_overlap = all_changed & expanded
                if near_overlap:
                    seen.add(key)
                    result.append(ChangedFunction(
                        name=func.name,
                        file=func.file,
                        start_line=func.start_line,
                        end_line=func.end_line,
                        change_type="near_change",
                        hunk_lines=sorted(near_overlap),
                    ))

    # Sort deterministically
    result.sort(key=lambda cf: (cf.file, cf.start_line, cf.name))
    return result
