"""RLQShellApplication — QApplication singleton with font loading and config."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable

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

FontProgressCallback = Callable[[int, int, str], None]

logger = logging.getLogger(__name__)

# Unique AppUserModelID — must be set on Windows BEFORE any window is shown so
# the taskbar groups RLQShell under its own icon instead of the host python.exe.
# Format convention: CompanyName.ProductName.SubProduct.VersionInformation
_WINDOWS_APP_USER_MODEL_ID = "RLQ.RLQShell.Client.1"


def _set_windows_app_user_model_id() -> None:
    """Tell Windows this process is its own app, so the taskbar uses our icon.

    No-op on non-Windows platforms or if the call fails (e.g. Wine, very old
    Windows). Must be called before the first top-level window is shown.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            _WINDOWS_APP_USER_MODEL_ID
        )
    except Exception as exc:  # pragma: no cover - best-effort, OS-specific
        logger.debug("Could not set AppUserModelID: %s", exc)


class RLQShellApplication(QApplication):
    """Main application singleton."""

    _instance: RLQShellApplication | None = None

    def __init__(self, argv: list[str]) -> None:
        # Must run before QApplication is constructed so the very first window
        # picks up the right taskbar identity.
        _set_windows_app_user_model_id()

        super().__init__(argv)

        if RLQShellApplication._instance is not None:
            raise RuntimeError("RLQShellApplication is a singleton — use instance()")
        RLQShellApplication._instance = self

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(APP_VERSION)
        self.setOrganizationName(ORGANIZATION_NAME)

        # Heavy resources are deferred so the splash can appear immediately.
        # main.py calls load_window_icon(), load_fonts() and accesses .config
        # AFTER the splash is on screen.
        self._config: ConfigManager | None = None
        self._fonts_loaded = False

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
        if self._config is None:
            self._config = ConfigManager()
        return self._config

    def load_window_icon(self) -> None:
        """Apply the application-wide window icon (taskbar / dock / window list)."""
        images_dir = RESOURCES_DIR / "images"
        for icon_name in ("app_icon.ico", "app_icon.png", "logo.svg"):
            icon_path = images_dir / icon_name
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

    def load_fonts(self, progress_cb: FontProgressCallback | None = None) -> None:
        """Load bundled fonts from resources/fonts/.

        Args:
            progress_cb: Optional callback ``(index, total, font_name)`` invoked
                before each font is registered, so a splash screen can show
                granular progress.
        """
        if self._fonts_loaded:
            return
        self._fonts_loaded = True

        if not FONTS_DIR.exists():
            logger.debug("Fonts directory not found: %s", FONTS_DIR)
            return

        font_files = [
            f for f in FONTS_DIR.iterdir()
            if f.suffix.lower() in (".ttf", ".otf", ".woff2")
        ]

        loaded = 0
        for index, font_file in enumerate(font_files):
            if progress_cb is not None:
                progress_cb(index, len(font_files), font_file.name)
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                logger.debug("Loaded font: %s (%s)", font_file.name, families)
                loaded += 1
            else:
                logger.warning("Failed to load font: %s", font_file.name)

        logger.info("Loaded %d bundled fonts", loaded)
