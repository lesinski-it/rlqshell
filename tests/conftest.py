"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from termplus.app.config import ConfigManager


@pytest.fixture
def tmp_config(tmp_path: Path) -> ConfigManager:
    """Create a ConfigManager backed by a temporary directory."""
    return ConfigManager(data_dir=tmp_path)
