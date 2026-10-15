"""Configuration loader for OriginScan.

Reads YAML config files and provides typed access to settings.
Config files:
  - config/context.yaml  — token caps, per-item limits, hops, ignore globs
  - config/agents.yaml   — known AI agent identities for provenance

See design.md §7 and architecture.md §7.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Default values (module-level constants so they're accessible for fallbacks)
# ---------------------------------------------------------------------------

_DEFAULT_IGNORE_GLOBS = ["build/", "third_party/", "vendor/", ".git/"]
_DEFAULT_TRAILER_KEYS = ["Co-authored-by", "Generated-by"]


# ---------------------------------------------------------------------------
# Config data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenCaps:
    """Token caps per context level."""

    L1: int = 2000
    L2: int = 6000
    L3: int = 15000


@dataclass(frozen=True)
class ContextConfig:
    """Settings for the context builder (from config/context.yaml)."""

    token_caps: TokenCaps = field(default_factory=TokenCaps)
    per_item_limit: int = 1500
    hops_max: int = 2
    tokenizer: str = "cl100k_base"
    ignore_globs: list[str] = field(default_factory=lambda: list(_DEFAULT_IGNORE_GLOBS))


@dataclass(frozen=True)
class AgentIdentity:
    """A known AI agent identity for provenance detection."""

    name: str
    emails: list[str] = field(default_factory=list)
    trailer_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentsConfig:
    """Known agent identities (from config/agents.yaml)."""

    agents: list[AgentIdentity] = field(default_factory=list)
    trailer_keys: list[str] = field(default_factory=lambda: list(_DEFAULT_TRAILER_KEYS))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict if the file doesn't exist."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_context_config(config_dir: Path | None = None) -> ContextConfig:
    """Load context configuration from config/context.yaml.

    Args:
        config_dir: Path to the config directory. Defaults to ``config/``
                     relative to the current working directory.

    Returns:
        Parsed ContextConfig with defaults for any missing values.
    """
    if config_dir is None:
        config_dir = Path("config")

    raw = _load_yaml(config_dir / "context.yaml")

    caps_raw = raw.get("token_caps", {})
    token_caps = TokenCaps(
        L1=int(caps_raw.get("L1", 2000)),
        L2=int(caps_raw.get("L2", 6000)),
        L3=int(caps_raw.get("L3", 15000)),
    )

    return ContextConfig(
        token_caps=token_caps,
        per_item_limit=int(raw.get("per_item_limit", 1500)),
        hops_max=int(raw.get("hops_max", 2)),
        tokenizer=str(raw.get("tokenizer", "cl100k_base")),
        ignore_globs=raw.get("ignore_globs", list(_DEFAULT_IGNORE_GLOBS)),
    )


def load_agents_config(config_dir: Path | None = None) -> AgentsConfig:
    """Load agent identities from config/agents.yaml.

    Args:
        config_dir: Path to the config directory. Defaults to ``config/``
                     relative to the current working directory.

    Returns:
        Parsed AgentsConfig with defaults for any missing values.
    """
    if config_dir is None:
        config_dir = Path("config")

    raw = _load_yaml(config_dir / "agents.yaml")

    agents: list[AgentIdentity] = []
    for agent_raw in raw.get("agents", []):
        agents.append(
            AgentIdentity(
                name=str(agent_raw.get("name", "")),
                emails=agent_raw.get("emails", []),
                trailer_keys=agent_raw.get("trailer_keys", []),
            )
        )

    return AgentsConfig(
        agents=agents,
        trailer_keys=raw.get("trailer_keys", list(_DEFAULT_TRAILER_KEYS)),
    )


# ---------------------------------------------------------------------------
# Config hashing (for reproducibility)
# ---------------------------------------------------------------------------


def config_hash(config: ContextConfig | AgentsConfig) -> str:
    """Compute a deterministic SHA-256 hash of a config object.

    Used to key caches and record which config produced a given run.
    """
    # dataclasses with frozen=True are safe to convert via __dict__
    # but we need to handle nested dataclasses
    raw = _config_to_dict(config)
    canonical = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _config_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to dicts."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _config_to_dict(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_config_to_dict(item) for item in obj]
    return obj
