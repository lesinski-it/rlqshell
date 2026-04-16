"""Terminal settings — font, cursor, scrollback, color scheme."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch


class TerminalSettings(QWidget):
    """Terminal configuration panel."""

    terminal_settings_changed = Signal()

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Terminal")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Font family
        self._font_combo = QComboBox()
        self._font_combo.addItems([
            "Cascadia Code", "Consolas", "Courier New",
            "Fira Code", "JetBrains Mono",
        ])
        self._font_combo.setCurrentText(config.get("terminal.font_family", "JetBrains Mono"))
        self._font_combo.currentTextChanged.connect(
            lambda v: self._save("terminal.font_family", v)
        )
        form.addRow(self._make_label("Font Family"), self._font_combo)

        # Font size
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 32)
        self._font_size.setValue(config.get("terminal.font_size", 13))
        self._font_size.valueChanged.connect(
            lambda v: self._save("terminal.font_size", v)
        )
        form.addRow(self._make_label("Font Size"), self._font_size)

        # Cursor style
        self._cursor_style = QComboBox()
        self._cursor_style.addItems(["block", "underline", "bar"])
        self._cursor_style.setCurrentText(config.get("terminal.cursor_style", "block"))
        self._cursor_style.currentTextChanged.connect(
            lambda v: self._save("terminal.cursor_style", v)
        )
        form.addRow(self._make_label("Cursor Style"), self._cursor_style)

        # Cursor blink
        self._cursor_blink = ToggleSwitch()
        self._cursor_blink.set_checked(config.get("terminal.cursor_blink", True))
        self._cursor_blink.toggled.connect(
            lambda v: self._save("terminal.cursor_blink", v)
        )
        form.addRow(self._make_label("Cursor Blink"), self._cursor_blink)

        # Scrollback lines
        self._scrollback = QSpinBox()
        self._scrollback.setRange(100, 100000)
        self._scrollback.setSingleStep(1000)
        self._scrollback.setValue(config.get("terminal.scrollback", 10000))
        self._scrollback.valueChanged.connect(
            lambda v: self._save("terminal.scrollback", v)
        )
        form.addRow(self._make_label("Scrollback Lines"), self._scrollback)

        # Color scheme
        self._scheme = QComboBox()
        self._scheme.addItems([
            "rlqDefault", "rlqDeepTide", "rlqNeonJungle", "rlqPurpleHaze",
            "rlqDawnLight", "rlqSilverMist",
        ])
        self._scheme.setCurrentText(config.get("terminal.color_scheme", "rlqDefault"))
        self._scheme.currentTextChanged.connect(
            lambda v: self._save("terminal.color_scheme", v)
        )
        form.addRow(self._make_label("Color Scheme"), self._scheme)

        layout.addLayout(form)
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
        self.terminal_settings_changed.emit()
