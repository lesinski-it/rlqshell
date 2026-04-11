"""Tests for ConfigManager."""

from __future__ import annotations

from pathlib import Path

from rlqshell.app.config import ConfigManager


def test_config_creates_defaults(tmp_path: Path) -> None:
    """First run creates config.json from defaults."""
    config = ConfigManager(data_dir=tmp_path)
    assert (tmp_path / "config.json").exists()
    assert config.get("terminal.font") == "JetBrains Mono"


def test_config_get_set_save(tmp_path: Path) -> None:
    """Get/set round-trips correctly and persists to disk."""
    config = ConfigManager(data_dir=tmp_path)
    config.set("terminal.font_size", 16)
    config.save()

    # Reload from disk
    config2 = ConfigManager(data_dir=tmp_path)
    assert config2.get("terminal.font_size") == 16


def test_config_get_default_fallback(tmp_path: Path) -> None:
    """Unknown keys return the provided default."""
    config = ConfigManager(data_dir=tmp_path)
    assert config.get("nonexistent.key", "fallback") == "fallback"


def test_config_dotted_key_access(tmp_path: Path) -> None:
    """Dotted keys access nested values."""
    config = ConfigManager(data_dir=tmp_path)
    assert config.get("appearance.theme") == "auto"
    assert config.get("ssh.default_port") == 22
    assert config.get("sync.enabled") is False


def test_config_reset(tmp_path: Path) -> None:
    """Reset restores defaults."""
    config = ConfigManager(data_dir=tmp_path)
    config.set("terminal.font_size", 99)
    config.save()
    config.reset()
    assert config.get("terminal.font_size") == 13


def test_config_paths(tmp_path: Path) -> None:
    """Data paths are derived correctly."""
    config = ConfigManager(data_dir=tmp_path)
    assert config.db_path == tmp_path / "rlqshell.db"
    assert config.vault_key_path == tmp_path / "vault.key"
    assert config.log_dir.exists()
    assert config.backups_dir.exists()


def test_config_deep_merge_preserves_new_keys(tmp_path: Path) -> None:
    """Existing config merges with new defaults — new keys appear."""
    config = ConfigManager(data_dir=tmp_path)
    config.set("terminal.font", "Fira Code")
    config.save()

    config2 = ConfigManager(data_dir=tmp_path)
    # Overridden value persists
    assert config2.get("terminal.font") == "Fira Code"
    # Default values from default_config still accessible
    assert config2.get("terminal.scrollback") == 10000
