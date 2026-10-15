"""Provenance reader — determines if code was written by AI, human, or unknown.

Examines git commit metadata (Co-authored-by trailers, bot author patterns,
and tool metadata keys from agents.yaml) to label code provenance.

See PRD task 6.3 and design.md §6.

Public API:
    detect_origin(commits, agents_config) -> ProvenanceResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from originscan.provenance.git import CommitInfo

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceResult:
    """Result of provenance detection for a code region."""

    origin: str  # "ai", "human", "unknown"
    confidence: float  # 0.0 to 1.0
    evidence: list[str]  # Human-readable evidence strings


# ---------------------------------------------------------------------------
# Bot / AI detection patterns
# ---------------------------------------------------------------------------

# Common bot email patterns
_BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@.*", re.IGNORECASE),
    re.compile(r".*noreply.*github\.com", re.IGNORECASE),
    re.compile(r".*bot@.*", re.IGNORECASE),
]

# Common bot name patterns
_BOT_NAME_PATTERNS = [
    re.compile(r".*\[bot\]$", re.IGNORECASE),
    re.compile(r"^dependabot.*", re.IGNORECASE),
    re.compile(r"^renovate.*", re.IGNORECASE),
    re.compile(r"^github-actions.*", re.IGNORECASE),
]

# Co-authored-by trailer pattern
_COAUTHOR_RE = re.compile(
    r"Co-authored-by:\s*(.+?)(?:\s*<(.+?)>)?$", re.IGNORECASE
)

# Known AI tool trailer keys
_AI_TRAILER_KEYS = [
    "generated-by",
    "ai-generated",
    "copilot-generated",
    "tool",
]


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------


def detect_origin(
    commits: list[CommitInfo],
    agent_names: list[str] | None = None,
    agent_emails: list[str] | None = None,
) -> ProvenanceResult:
    """Determine the provenance of code from its commit history.

    Checks (in order of priority):
      1. Co-authored-by trailers matching known AI agents
      2. Bot author patterns (name or email)
      3. AI tool metadata trailers
      4. Configured agent identities from agents.yaml

    Args:
        commits: Git commits that touched the code region.
        agent_names: Known AI agent names from agents.yaml.
        agent_emails: Known AI agent emails from agents.yaml.

    Returns:
        ProvenanceResult with origin, confidence, and evidence.
    """
    if not commits:
        return ProvenanceResult(
            origin="unknown",
            confidence=0.0,
            evidence=["No commits found for this code region"],
        )

    if agent_names is None:
        agent_names = []
    if agent_emails is None:
        agent_emails = []

    evidence: list[str] = []
    ai_signals = 0
    human_signals = 0

    for commit in commits:
        # 1. Check Co-authored-by trailers
        for trailer in commit.trailers:
            match = _COAUTHOR_RE.match(trailer)
            if match:
                name = match.group(1).strip()
                email = match.group(2) or ""

                if _is_bot_name(name) or _is_bot_email(email):
                    ai_signals += 1
                    evidence.append(
                        f"Bot co-author in {commit.sha[:8]}: {trailer}"
                    )
                elif name.lower() in [a.lower() for a in agent_names]:
                    ai_signals += 1
                    evidence.append(
                        f"Known agent co-author in {commit.sha[:8]}: {name}"
                    )
                elif email.lower() in [e.lower() for e in agent_emails]:
                    ai_signals += 1
                    evidence.append(
                        f"Known agent email in {commit.sha[:8]}: {email}"
                    )

        # 2. Check commit author
        if _is_bot_name(commit.author_name):
            ai_signals += 1
            evidence.append(
                f"Bot author in {commit.sha[:8]}: {commit.author_name}"
            )
        elif _is_bot_email(commit.author_email):
            ai_signals += 1
            evidence.append(
                f"Bot email in {commit.sha[:8]}: {commit.author_email}"
            )
        elif commit.author_name.lower() in [a.lower() for a in agent_names]:
            ai_signals += 1
            evidence.append(
                f"Known agent author in {commit.sha[:8]}: {commit.author_name}"
            )
        else:
            human_signals += 1

        # 3. Check for AI tool trailers
        for trailer in commit.trailers:
            key = trailer.split(":")[0].strip().lower()
            if key in _AI_TRAILER_KEYS:
                ai_signals += 1
                evidence.append(
                    f"AI tool trailer in {commit.sha[:8]}: {trailer}"
                )

    # Determine origin
    total = ai_signals + human_signals
    if total == 0:
        return ProvenanceResult(
            origin="unknown",
            confidence=0.0,
            evidence=["No author signals found"],
        )

    if ai_signals > 0 and human_signals == 0:
        confidence = min(1.0, 0.7 + ai_signals * 0.1)
        return ProvenanceResult(
            origin="ai", confidence=confidence, evidence=evidence
        )

    if ai_signals > 0:
        # Mixed signals — still call it AI if majority
        ai_ratio = ai_signals / total
        if ai_ratio >= 0.5:
            return ProvenanceResult(
                origin="ai",
                confidence=round(ai_ratio, 2),
                evidence=evidence,
            )
        return ProvenanceResult(
            origin="human",
            confidence=round(1.0 - ai_ratio, 2),
            evidence=evidence + ["Mixed AI/human signals"],
        )

    return ProvenanceResult(
        origin="human",
        confidence=min(1.0, 0.6 + human_signals * 0.1),
        evidence=evidence or ["All commits from human authors"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_bot_name(name: str) -> bool:
    return any(p.match(name) for p in _BOT_NAME_PATTERNS)


def _is_bot_email(email: str) -> bool:
    return any(p.match(email) for p in _BOT_EMAIL_PATTERNS)
