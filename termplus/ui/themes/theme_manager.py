"""Theme loading and application."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from termplus.app.constants import THEMES_DIR

logger = logging.getLogger(__name__)


class ThemeManager:
    """Loads and applies QSS themes to the application."""

    def __init__(self) -> None:
        self._current_theme: str = "dark"

    @property
    def current_theme(self) -> str:
        return self._current_theme

    def get_available_themes(self) -> list[str]:
        """Return names of available .qss theme files."""
        if not THEMES_DIR.exists():
            return []
        return [
            f.stem for f in THEMES_DIR.iterdir()
            if f.suffix == ".qss" and f.is_file()
        ]

    def load_theme(self, theme_name: str) -> str:
        """Load a QSS file and return its content."""
        qss_path = THEMES_DIR / f"{theme_name}.qss"
        if not qss_path.exists():
            logger.warning("Theme file not found: %s", qss_path)
            return ""
        return qss_path.read_text(encoding="utf-8")

    def apply_theme(self, app: QApplication, theme_name: str = "dark") -> None:
        """Apply a theme to the application."""
        stylesheet = self.load_theme(theme_name)
        if stylesheet:
            app.setStyleSheet(stylesheet)
            self._current_theme = theme_name
            logger.info("Applied theme: %s", theme_name)
        else:
            logger.warning("Could not apply theme: %s", theme_name)
