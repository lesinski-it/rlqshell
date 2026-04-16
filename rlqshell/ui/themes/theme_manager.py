"""Theme loading and application."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from rlqshell.app.constants import THEMES_DIR

logger = logging.getLogger(__name__)


def resolve_theme_setting(theme_setting: str) -> str:
    """Resolve a configured theme value to a concrete 'dark' or 'light'.

    'auto' is mapped to the current system color scheme via
    QGuiApplication.styleHints().colorScheme(). If the scheme cannot be
    determined (older Qt, headless test, unknown), falls back to 'dark'.
    Any other input is returned as-is so callers can pass through 'dark'
    or 'light' directly.
    """
    if theme_setting != "auto":
        return theme_setting
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        if hints is not None:
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return "light"
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
    except Exception:  # noqa: BLE001 — best-effort detection
        logger.debug("Could not detect system color scheme", exc_info=True)
    return "dark"


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
        """Load a QSS file and return its content.

        The QSS files are templates with palette placeholders — light/dark
        variants share the same template, only the substituted palette
        differs. If `{theme_name}.qss` doesn't exist, fall back to dark.qss
        which acts as the canonical template.
        """
        qss_path = THEMES_DIR / f"{theme_name}.qss"
        if not qss_path.exists():
            qss_path = THEMES_DIR / "dark.qss"
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
