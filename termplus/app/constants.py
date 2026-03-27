"""Application-wide constants."""

from pathlib import Path

# App metadata
APP_NAME = "Termplus"
APP_VERSION = "0.1.0"
ORGANIZATION_NAME = "Termplus"

# Paths
RESOURCES_DIR = Path(__file__).parent.parent / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
FONTS_DIR = RESOURCES_DIR / "fonts"
THEMES_DIR = Path(__file__).parent.parent / "ui" / "themes"
TRANSLATIONS_DIR = RESOURCES_DIR / "translations"

# Default terminal settings
DEFAULT_TERMINAL_FONT = "JetBrains Mono"
DEFAULT_TERMINAL_FONT_SIZE = 13
DEFAULT_TERMINAL_SCROLLBACK = 10000
DEFAULT_TERMINAL_CURSOR_STYLE = "block"

# Default UI settings
DEFAULT_UI_FONT = "Inter"
DEFAULT_UI_FONT_SIZE = 13

# Theme colors (Dark theme — primary palette)
class Colors:
    """Dark theme color palette."""

    BG_PRIMARY = "#1e1e2e"
    BG_SURFACE = "#2a2a3e"
    BG_DARKER = "#16162a"
    BG_HOVER = "#3a3a4e"
    BG_ACTIVE = "#4a4a5e"

    ACCENT = "#7c3aed"
    ACCENT_HOVER = "#6d28d9"
    ACCENT_LIGHT = "#a78bfa"

    TEXT_PRIMARY = "#cdd6f4"
    TEXT_SECONDARY = "#9399b2"
    TEXT_MUTED = "#6c7086"

    BORDER = "#3a3a4e"
    BORDER_FOCUS = "#7c3aed"

    SUCCESS = "#22c55e"
    WARNING = "#f59e0b"
    DANGER = "#e94560"
    INFO = "#3b82f6"

    # Status
    CONNECTED = "#22c55e"
    DISCONNECTED = "#6c7086"
    CONNECTING = "#f59e0b"
    ERROR = "#e94560"

# SSH defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_KEEP_ALIVE = 60

# Cloud sync OAuth client IDs (placeholders — user configurable)
OAUTH_ONEDRIVE_CLIENT_ID = ""
OAUTH_GOOGLE_CLIENT_ID = ""
OAUTH_DROPBOX_APP_KEY = ""
