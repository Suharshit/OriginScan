"""Thin git wrapper for blame/log queries.

Mockable in tests — no direct subprocess calls from other modules.

See design.md §7.
"""

from __future__ import annotations

# Implementation in Phase 6
