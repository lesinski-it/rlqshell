"""Configuration manager — loads, saves, and provides access to app settings."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import appdirs

from termplus.app.constants import APP_NAME, RESOURCES_DIR


class ConfigManager:
    """Manages application configuration stored as JSON.

    Config is loaded from ~/.termplus/config.json (or platform equivalent).
    On first run, defaults are copied from resources/default_config.json.
    Supports dotted-key access: get("terminal.font_size").
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path(appdirs.user_data_dir(APP_NAME.lower()))
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._config_path = self._data_dir / "config.json"
        self._defaults = self._load_defaults()
        self._config: dict[str, Any] = self._load_config()

    # --- Public paths ---

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def db_path(self) -> Path:
        return self._data_dir / "termplus.db"

    @property
    def vault_key_path(self) -> Path:
        return self._data_dir / "vault.key"

    @property
    def log_dir(self) -> Path:
        d = self._data_dir / "logs"
        d.mkdir(exist_ok=True)
        return d

    @property
    def backups_dir(self) -> Path:
        d = self._data_dir / "backups"
        d.mkdir(exist_ok=True)
        return d

    # --- Access ---

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dotted key, e.g. 'terminal.font_size'."""
        keys = key.split(".")
        val: Any = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
            if val is None:
                return self._get_default(key, default)
        return val

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dotted key."""
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def save(self) -> None:
        """Persist config to disk."""
        self._config_path.write_text(
            json.dumps(self._config, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

    def reset(self) -> None:
        """Reset config to defaults."""
        self._config = json.loads(json.dumps(self._defaults))
        self.save()

    @property
    def all(self) -> dict[str, Any]:
        """Return the full config dict (read-only copy)."""
        return json.loads(json.dumps(self._config))

    # --- Private ---

    def _load_defaults(self) -> dict[str, Any]:
        default_path = RESOURCES_DIR / "default_config.json"
        if default_path.exists():
            return json.loads(default_path.read_text(encoding="utf-8"))
        return {}

    def _load_config(self) -> dict[str, Any]:
        if not self._config_path.exists():
            # First run — copy defaults
            default_path = RESOURCES_DIR / "default_config.json"
            if default_path.exists():
                shutil.copy2(default_path, self._config_path)
            return json.loads(json.dumps(self._defaults))

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
            # Merge with defaults (add missing keys)
            return self._deep_merge(self._defaults, config)
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self._defaults))

    def _get_default(self, key: str, fallback: Any) -> Any:
        keys = key.split(".")
        val: Any = self._defaults
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return fallback
            if val is None:
                return fallback
        return val

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge override into base. Override values take precedence."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
