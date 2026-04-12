"""Application-wide constants."""

from pathlib import Path

# App metadata
APP_NAME = "RLQShell"
APP_VERSION = "2.4.0-beta"
ORGANIZATION_NAME = "RLQShell"
APP_AUTHOR = "Ravczy"
APP_AUTHOR_WEBSITE = "https://www.lesinski.it"
APP_DONATE_URL = "https://lesinski.it/donate"
APP_PRIVACY_URL = "https://lesinski.it/privacy-policy"
APP_LICENSES_URL = "https://lesinski.it/rlqshell/licenses"

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

# Theme colors — populated at startup via Colors.apply_palette()
class Colors:
    """Active color palette. Class attributes are filled in by apply_palette().

    The defaults below are placeholders; the real values come from one of the
    palettes in rlqshell.ui.themes.palettes. apply_palette() must be called
    before any widget reads these attributes — main() does this right after
    loading the user config.
    """

    # Backgrounds
    BG_PRIMARY = ""
    BG_SURFACE = ""
    BG_DARKER = ""
    BG_HOVER = ""
    BG_ACTIVE = ""

    # Accent
    ACCENT = ""
    ACCENT_HOVER = ""
    ACCENT_LIGHT = ""

    # Text
    TEXT_PRIMARY = ""
    TEXT_SECONDARY = ""
    TEXT_MUTED = ""

    # Borders
    BORDER = ""
    BORDER_FOCUS = ""

    # Semantic
    SUCCESS = ""
    WARNING = ""
    DANGER = ""
    INFO = ""

    # Status (derived from semantic)
    CONNECTED = ""
    DISCONNECTED = ""
    CONNECTING = ""
    ERROR = ""

    @classmethod
    def apply_palette(cls, name: str, theme: str = "dark") -> None:
        """Apply a named palette by overwriting class attributes in place.

        `theme` selects between the dark and light variants of the palette.
        """
        from rlqshell.ui.themes.palettes import (
            DEFAULT_PALETTE,
            PALETTES,
            PALETTES_LIGHT,
        )

        palette_set = PALETTES_LIGHT if theme == "light" else PALETTES
        palette = palette_set.get(name) or palette_set[DEFAULT_PALETTE]
        for key, value in palette.items():
            setattr(cls, key, value)
        # Status colors are derived from the semantic palette
        cls.CONNECTED = palette["SUCCESS"]
        cls.DISCONNECTED = palette["TEXT_MUTED"]
        cls.CONNECTING = palette["WARNING"]
        cls.ERROR = palette["DANGER"]


# Apply the default palette at module import so widgets can read Colors.*
# even before main() runs (e.g. during tests). main() will overwrite this
# with the user-configured palette.
Colors.apply_palette("amber")

# SSH defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_KEEP_ALIVE = 60

# Cloud sync OAuth client IDs (placeholders — user configurable)
OAUTH_ONEDRIVE_CLIENT_ID = "b88283ef-9ffa-4923-b600-5624ea4f1a13"
OAUTH_GOOGLE_CLIENT_ID = ""
OAUTH_DROPBOX_APP_KEY = ""
