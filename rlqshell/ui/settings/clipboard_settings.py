"""Clipboard settings — sync behavior, size limits, paste-as-typing delay."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.config import ConfigManager
from rlqshell.app.constants import Colors
from rlqshell.ui.widgets.toggle_switch import ToggleSwitch


class ClipboardSettings(QWidget):
    """Clipboard sync and paste-as-typing configuration."""

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Clipboard")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # --- Sync section ---
        section_label = QLabel("Synchronization")
        section_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(section_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Enable/disable clipboard globally
        self._enable_switch = ToggleSwitch()
        self._enable_switch.set_checked(config.get("clipboard.enabled", True))
        self._enable_switch.toggled.connect(
            lambda v: self._save("clipboard.enabled", v)
        )
        form.addRow(
            self._make_label("Enable clipboard sync"),
            self._enable_switch,
        )

        layout.addLayout(form)

        # --- Paste-as-typing section ---
        section_label = QLabel("Paste-as-Typing (VNC)")
        section_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 16px;"
        )
        layout.addWidget(section_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # VNC paste delay
        self._vnc_delay_spin = QSpinBox()
        self._vnc_delay_spin.setMinimum(0)
        self._vnc_delay_spin.setMaximum(200)
        self._vnc_delay_spin.setValue(config.get("clipboard.vnc_paste_delay_ms", 5))
        self._vnc_delay_spin.setSuffix(" ms")
        self._vnc_delay_spin.setSingleStep(1)
        self._vnc_delay_spin.valueChanged.connect(
            lambda v: self._save("clipboard.vnc_paste_delay_ms", v)
        )
        form.addRow(
            self._make_label("Delay between characters"),
            self._vnc_delay_spin,
        )

        layout.addLayout(form)

        # --- Size limits section ---
        section_label = QLabel("Size Limits")
        section_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 16px;"
        )
        layout.addWidget(section_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Text size limit
        self._text_limit_spin = QSpinBox()
        self._text_limit_spin.setMinimum(10)
        self._text_limit_spin.setMaximum(10000)
        self._text_limit_spin.setValue(config.get("clipboard.text_size_limit_kb", 500))
        self._text_limit_spin.setSuffix(" KB")
        self._text_limit_spin.setSingleStep(50)
        self._text_limit_spin.valueChanged.connect(
            lambda v: self._save("clipboard.text_size_limit_kb", v)
        )
        form.addRow(
            self._make_label("Max text to sync"),
            self._text_limit_spin,
        )

        # Image size limit
        self._image_limit_spin = QSpinBox()
        self._image_limit_spin.setMinimum(1)
        self._image_limit_spin.setMaximum(200)
        self._image_limit_spin.setValue(config.get("clipboard.image_size_limit_mb", 25))
        self._image_limit_spin.setSuffix(" MB")
        self._image_limit_spin.setSingleStep(5)
        self._image_limit_spin.valueChanged.connect(
            lambda v: self._save("clipboard.image_size_limit_mb", v)
        )
        form.addRow(
            self._make_label("Max image to sync (RDP)"),
            self._image_limit_spin,
        )

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
