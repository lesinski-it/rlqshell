"""RLQShellApplication — QApplication singleton with font loading and config."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import (
    APP_NAME,
    APP_VERSION,
    FONTS_DIR,
    ORGANIZATION_NAME,
    RESOURCES_DIR,
)

logger = logging.getLogger(__name__)


class RLQShellApplication(QApplication):
    """Main application singleton."""

    _instance: RLQShellApplication | None = None

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)

        if RLQShellApplication._instance is not None:
            raise RuntimeError("RLQShellApplication is a singleton — use instance()")
        RLQShellApplication._instance = self

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(APP_VERSION)
        self.setOrganizationName(ORGANIZATION_NAME)

        # Application-wide icon (taskbar / dock / window list).
        images_dir = RESOURCES_DIR / "images"
        for icon_name in ("app_icon.ico", "app_icon.png", "logo.svg"):
            icon_path = images_dir / icon_name
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        self._config = ConfigManager()
        self._load_fonts()

        logger.info("RLQShellApplication initialized (v%s)", APP_VERSION)

    @classmethod
    def instance(cls) -> RLQShellApplication:
        """Return the singleton instance."""
        inst = cls._instance
        if inst is None:
            raise RuntimeError("RLQShellApplication not yet created")
        return inst

    @property
    def config(self) -> ConfigManager:
        return self._config

    def _load_fonts(self) -> None:
        """Load bundled fonts from resources/fonts/."""
        if not FONTS_DIR.exists():
            logger.debug("Fonts directory not found: %s", FONTS_DIR)
            return

        loaded = 0
        for font_file in FONTS_DIR.iterdir():
            if font_file.suffix.lower() in (".ttf", ".otf", ".woff2"):
                font_id = QFontDatabase.addApplicationFont(str(font_file))
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    logger.debug("Loaded font: %s (%s)", font_file.name, families)
                    loaded += 1
                else:
                    logger.warning("Failed to load font: %s", font_file.name)

        logger.info("Loaded %d bundled fonts", loaded)
