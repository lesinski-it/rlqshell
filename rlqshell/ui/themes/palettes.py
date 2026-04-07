"""Color palettes for RLQShell themes.

Each palette is a flat dict of color name → hex string. The active palette is
chosen at startup via Colors.apply_palette() (see rlqshell.app.constants) and
is then used both by inline widget stylesheets (Colors.* attributes) and by
the QSS template renderer (rlqshell.ui.themes.theme_manager).

Changing palette in settings requires a restart — there is no hot-swap.
"""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "cyan": {  # DEFAULT — private-cloud / fresh / technical
        "BG_PRIMARY": "#0f172a",
        "BG_SURFACE": "#1e293b",
        "BG_DARKER": "#020617",
        "BG_HOVER": "#334155",
        "BG_ACTIVE": "#475569",
        "ACCENT": "#06b6d4",
        "ACCENT_HOVER": "#0891b2",
        "ACCENT_LIGHT": "#67e8f9",
        "TEXT_PRIMARY": "#e2e8f0",
        "TEXT_SECONDARY": "#94a3b8",
        "TEXT_MUTED": "#64748b",
        "BORDER": "#334155",
        "BORDER_FOCUS": "#06b6d4",
        "SUCCESS": "#22c55e",
        "WARNING": "#f59e0b",
        "DANGER": "#ef4444",
        "INFO": "#3b82f6",
    },
    "emerald": {  # terminal CRT vibe
        "BG_PRIMARY": "#1a1d1a",
        "BG_SURFACE": "#25292a",
        "BG_DARKER": "#0e1110",
        "BG_HOVER": "#2f3534",
        "BG_ACTIVE": "#3a413f",
        "ACCENT": "#10b981",
        "ACCENT_HOVER": "#059669",
        "ACCENT_LIGHT": "#6ee7b7",
        "TEXT_PRIMARY": "#e5e7eb",
        "TEXT_SECONDARY": "#9ca3af",
        "TEXT_MUTED": "#6b7280",
        "BORDER": "#374151",
        "BORDER_FOCUS": "#10b981",
        "SUCCESS": "#22c55e",
        "WARNING": "#f59e0b",
        "DANGER": "#ef4444",
        "INFO": "#3b82f6",
    },
    "amber": {  # warm, energetic
        "BG_PRIMARY": "#1c1917",
        "BG_SURFACE": "#292524",
        "BG_DARKER": "#0c0a09",
        "BG_HOVER": "#3a3431",
        "BG_ACTIVE": "#4a423e",
        "ACCENT": "#f97316",
        "ACCENT_HOVER": "#ea580c",
        "ACCENT_LIGHT": "#fdba74",
        "TEXT_PRIMARY": "#fafaf9",
        "TEXT_SECONDARY": "#a8a29e",
        "TEXT_MUTED": "#78716c",
        "BORDER": "#44403c",
        "BORDER_FOCUS": "#f97316",
        "SUCCESS": "#22c55e",
        "WARNING": "#eab308",
        "DANGER": "#ef4444",
        "INFO": "#3b82f6",
    },
    "azure": {  # corporate-blue
        "BG_PRIMARY": "#0f172a",
        "BG_SURFACE": "#1e293b",
        "BG_DARKER": "#020617",
        "BG_HOVER": "#334155",
        "BG_ACTIVE": "#475569",
        "ACCENT": "#3b82f6",
        "ACCENT_HOVER": "#2563eb",
        "ACCENT_LIGHT": "#93c5fd",
        "TEXT_PRIMARY": "#e2e8f0",
        "TEXT_SECONDARY": "#94a3b8",
        "TEXT_MUTED": "#64748b",
        "BORDER": "#334155",
        "BORDER_FOCUS": "#3b82f6",
        "SUCCESS": "#22c55e",
        "WARNING": "#f59e0b",
        "DANGER": "#ef4444",
        "INFO": "#0ea5e9",
    },
}

DEFAULT_PALETTE = "cyan"

PALETTE_KEYS: tuple[str, ...] = (
    "BG_PRIMARY", "BG_SURFACE", "BG_DARKER", "BG_HOVER", "BG_ACTIVE",
    "ACCENT", "ACCENT_HOVER", "ACCENT_LIGHT",
    "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED",
    "BORDER", "BORDER_FOCUS",
    "SUCCESS", "WARNING", "DANGER", "INFO",
)
