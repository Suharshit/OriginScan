"""Tests for originscan.config — config loading, defaults, and hashing."""

from __future__ import annotations

from pathlib import Path

from originscan.config import (
    ContextConfig,
    TokenCaps,
    config_hash,
    load_agents_config,
    load_context_config,
)

# Use the project's config/ directory for integration tests
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class TestContextConfigDefaults:
    """Verify defaults when config file is missing."""

    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_context_config(tmp_path)
        assert cfg.token_caps.L1 == 2000
        assert cfg.token_caps.L2 == 6000
        assert cfg.token_caps.L3 == 15000
        assert cfg.per_item_limit == 1500
        assert cfg.hops_max == 2
        assert cfg.tokenizer == "cl100k_base"
        assert "build/" in cfg.ignore_globs

    def test_loads_real_config(self) -> None:
        cfg = load_context_config(CONFIG_DIR)
        assert cfg.token_caps.L1 == 2000
        assert cfg.tokenizer == "cl100k_base"
        assert ".originscan/" in cfg.ignore_globs


class TestContextConfigCustom:
    """Verify custom values are loaded correctly."""

    def test_custom_caps(self, tmp_path: Path) -> None:
        (tmp_path / "context.yaml").write_text(
            "token_caps:\n  L1: 1000\n  L2: 4000\n  L3: 10000\n"
            "per_item_limit: 500\nhops_max: 1\ntokenizer: gpt2\n"
        )
        cfg = load_context_config(tmp_path)
        assert cfg.token_caps.L1 == 1000
        assert cfg.token_caps.L2 == 4000
        assert cfg.token_caps.L3 == 10000
        assert cfg.per_item_limit == 500
        assert cfg.hops_max == 1
        assert cfg.tokenizer == "gpt2"

    def test_partial_config(self, tmp_path: Path) -> None:
        """Missing keys should fall back to defaults."""
        (tmp_path / "context.yaml").write_text("token_caps:\n  L1: 3000\n")
        cfg = load_context_config(tmp_path)
        assert cfg.token_caps.L1 == 3000
        assert cfg.token_caps.L2 == 6000  # default
        assert cfg.per_item_limit == 1500  # default


class TestAgentsConfig:
    """Verify agent identity loading."""

    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_agents_config(tmp_path)
        assert cfg.agents == []
        assert "Co-authored-by" in cfg.trailer_keys

    def test_loads_real_config(self) -> None:
        cfg = load_agents_config(CONFIG_DIR)
        assert len(cfg.agents) > 0
        names = [a.name for a in cfg.agents]
        assert "GitHub Copilot" in names

    def test_custom_agents(self, tmp_path: Path) -> None:
        (tmp_path / "agents.yaml").write_text(
            "trailer_keys:\n  - Generated-by\n"
            "agents:\n  - name: TestBot\n    emails:\n      - test@bot.com\n"
        )
        cfg = load_agents_config(tmp_path)
        assert len(cfg.agents) == 1
        assert cfg.agents[0].name == "TestBot"
        assert cfg.agents[0].emails == ["test@bot.com"]


class TestConfigHash:
    """Verify deterministic config hashing for reproducibility."""

    def test_same_config_same_hash(self) -> None:
        cfg1 = ContextConfig()
        cfg2 = ContextConfig()
        assert config_hash(cfg1) == config_hash(cfg2)

    def test_different_config_different_hash(self) -> None:
        cfg1 = ContextConfig(token_caps=TokenCaps(L1=2000))
        cfg2 = ContextConfig(token_caps=TokenCaps(L1=3000))
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_hash_is_deterministic(self) -> None:
        cfg = load_context_config(CONFIG_DIR)
        h1 = config_hash(cfg)
        h2 = config_hash(cfg)
        assert h1 == h2

    def test_hash_length(self) -> None:
        cfg = ContextConfig()
        h = config_hash(cfg)
        assert len(h) == 16  # truncated SHA-256
