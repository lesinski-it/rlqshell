"""Appearance settings — theme, UI font, window opacity."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.themes.palettes import DEFAULT_PALETTE, PALETTES


class AppearanceSettings(QWidget):
    """Appearance configuration panel."""

    appearance_settings_changed = Signal()

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Appearance")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Color palette (4 named palettes — see rlqshell/ui/themes/palettes.py)
        self._palette = QComboBox()
        self._palette.addItems(sorted(PALETTES.keys()))
        self._palette.setCurrentText(
            config.get("appearance.palette", DEFAULT_PALETTE)
        )
        self._palette.currentTextChanged.connect(
            lambda v: self._save("appearance.palette", v)
        )
        form.addRow(self._make_label("Palette"), self._palette)

        # Theme — "auto" follows the OS color scheme
        self._theme = QComboBox()
        self._theme.addItems(["auto", "dark", "light"])
        self._theme.setCurrentText(config.get("appearance.theme", "auto"))
        self._theme.currentTextChanged.connect(
            lambda v: self._save("appearance.theme", v)
        )
        form.addRow(self._make_label("Theme"), self._theme)

        # UI font family
        self._ui_font = QComboBox()
        self._ui_font.addItems(["Inter", "Segoe UI", "Helvetica Neue", "System Default"])
        self._ui_font.setCurrentText(config.get("appearance.ui_font", "Inter"))
        self._ui_font.currentTextChanged.connect(
            lambda v: self._save("appearance.ui_font", v)
        )
        form.addRow(self._make_label("UI Font"), self._ui_font)

        # UI font size
        self._ui_size = QSpinBox()
        self._ui_size.setRange(10, 20)
        self._ui_size.setValue(config.get("appearance.ui_font_size", 13))
        self._ui_size.valueChanged.connect(
            lambda v: self._save("appearance.ui_font_size", v)
        )
        form.addRow(self._make_label("UI Font Size"), self._ui_size)

        # Window opacity
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(50, 100)
        self._opacity.setValue(config.get("appearance.opacity", 100))
        self._opacity.valueChanged.connect(
            lambda v: self._save("appearance.opacity", v)
        )
        form.addRow(self._make_label("Window Opacity"), self._opacity)

        layout.addLayout(form)

        # Restart hint — inline-styled widgets keep their old colors until restart
        restart_hint = QLabel(
            "⚠ Restart recommended for palette/theme changes to fully apply."
        )
        restart_hint.setStyleSheet(
            f"font-size: 12px; color: {Colors.WARNING}; background: transparent; "
            f"padding-top: 8px;"
        )
        layout.addWidget(restart_hint)

        layout.addStretch()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        return lbl

    def _save(self, key: str, value) -> None:
        self._config.set(key, value)
        self._config.save()
        self.appearance_settings_changed.emit()
