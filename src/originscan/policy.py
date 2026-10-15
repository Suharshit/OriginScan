"""Policy loader — reads policy.yaml for level selection rules.

Loads a YAML policy file that maps origin labels (and optionally CWE
families) to starting context levels and escalation parameters.

See PRD task 7.4.

Public API:
    load_policy(path) -> PolicyConfig
    PolicyConfig.choose_level(origin, cwe_family) -> Level
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from originscan.interfaces import Level


@dataclass
class PolicyConfig:
    """Policy configuration for level selection and escalation.

    Loaded from policy.yaml with the structure::

        levels:
          human: L1
          ai: L2
          unknown: L1
        escalation:
          tau: 0.7
          max_level: L3
          budget: 50000
        overrides:
          CWE-787:
            human: L2
            ai: L3
    """

    levels: dict[str, str] = field(
        default_factory=lambda: {"human": "L1", "ai": "L2", "unknown": "L1"}
    )
    escalation_tau: float = 0.7
    escalation_max_level: str = "L3"
    escalation_budget: int = 50000
    overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    def choose_level(
        self, origin: str, cwe_family: str | None = None
    ) -> Level:
        """Choose the starting level based on origin and CWE family.

        Checks CWE-specific overrides first, then the default levels.
        Falls back to L1 if origin is not found.
        """
        # Check CWE-specific overrides
        if cwe_family and cwe_family in self.overrides:
            override = self.overrides[cwe_family]
            if origin in override:
                return override[origin]  # type: ignore[return-value]

        return self.levels.get(origin, "L1")  # type: ignore[return-value]


def load_policy(path: str | Path) -> PolicyConfig:
    """Load a policy from a YAML file.

    Args:
        path: Path to policy.yaml.

    Returns:
        PolicyConfig with levels, escalation params, and overrides.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    import yaml

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Policy file not found: {p}")

    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return PolicyConfig()

    config = PolicyConfig()

    if "levels" in data and isinstance(data["levels"], dict):
        config.levels.update(data["levels"])

    if "escalation" in data and isinstance(data["escalation"], dict):
        esc = data["escalation"]
        if "tau" in esc:
            config.escalation_tau = float(esc["tau"])
        if "max_level" in esc:
            config.escalation_max_level = str(esc["max_level"])
        if "budget" in esc:
            config.escalation_budget = int(esc["budget"])

    if "overrides" in data and isinstance(data["overrides"], dict):
        config.overrides = data["overrides"]

    return config


def default_policy() -> PolicyConfig:
    """Return the default policy (confidence-only, no overrides)."""
    return PolicyConfig()
