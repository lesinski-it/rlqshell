"""TermplusApplication — QApplication singleton with font loading and config."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from termplus.app.config import ConfigManager
from termplus.app.constants import APP_NAME, APP_VERSION, FONTS_DIR, ORGANIZATION_NAME

logger = logging.getLogger(__name__)


class TermplusApplication(QApplication):
    """Main application singleton."""

    _instance: TermplusApplication | None = None

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)

        if TermplusApplication._instance is not None:
            raise RuntimeError("TermplusApplication is a singleton — use instance()")
        TermplusApplication._instance = self

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(APP_VERSION)
        self.setOrganizationName(ORGANIZATION_NAME)

        self._config = ConfigManager()
        self._load_fonts()

        logger.info("TermplusApplication initialized (v%s)", APP_VERSION)

    @classmethod
    def instance(cls) -> TermplusApplication:
        """Return the singleton instance."""
        inst = cls._instance
        if inst is None:
            raise RuntimeError("TermplusApplication not yet created")
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
