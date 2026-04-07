"""Theme loading and application."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from rlqshell.app.constants import THEMES_DIR

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

    def apply_theme(
        self,
        app: QApplication,
        theme_name: str = "dark",
        ui_font: str | None = None,
        ui_font_size: int | None = None,
    ) -> None:
        """Apply a theme to the application, optionally overriding font settings.

        The theme file is a QSS template containing {KEY} placeholders that get
        substituted with the active palette before being applied. The palette
        must already be set on Colors via Colors.apply_palette() before this
        method runs (main() does this right after loading config).
        """
        stylesheet = self.load_theme(theme_name)
        if not stylesheet:
            logger.warning("Could not apply theme: %s", theme_name)
            return

        # Render palette placeholders. We use str.replace (not str.format)
        # because QSS uses { } for blocks and we don't want to escape them.
        from rlqshell.app.constants import Colors
        from rlqshell.ui.themes.palettes import PALETTE_KEYS

        for key in PALETTE_KEYS:
            stylesheet = stylesheet.replace("{" + key + "}", getattr(Colors, key))

        if ui_font or ui_font_size:
            import re

            def _replace_qwidget_block(m: re.Match) -> str:
                block = m.group(0)
                if ui_font:
                    font_val = f'"{ui_font}"' if ui_font != "System Default" else '"Segoe UI", sans-serif'
                    block = re.sub(
                        r'font-family:\s*[^;]+;',
                        f'font-family: {font_val};',
                        block,
                    )
                if ui_font_size:
                    block = re.sub(
                        r'font-size:\s*\d+px;',
                        f'font-size: {ui_font_size}px;',
                        block,
                        count=1,
                    )
                return block

            stylesheet = re.sub(
                r'QWidget\s*\{[^}]+\}',
                _replace_qwidget_block,
                stylesheet,
                count=1,
            )

        app.setStyleSheet(stylesheet)
        self._current_theme = theme_name
        logger.info("Applied theme: %s (font=%s, size=%s)", theme_name, ui_font, ui_font_size)
