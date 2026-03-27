"""Platform-specific utility functions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import appdirs

from termplus.app.constants import APP_NAME


def get_platform() -> str:
    """Return the current platform: 'windows', 'linux', or 'macos'."""
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    return "linux"


def get_data_dir() -> Path:
    """Return the user data directory for Termplus."""
    return Path(appdirs.user_data_dir(APP_NAME.lower()))


def get_default_shell() -> str:
    """Return the default shell for the current platform."""
    platform = get_platform()
    if platform == "windows":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/bash")


def open_url_in_browser(url: str) -> None:
    """Open a URL in the default system browser."""
    import webbrowser
    webbrowser.open(url)
