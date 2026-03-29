"""Group editor dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.models.host import Group

GROUP_COLORS = [
    ("#e94560", "Red"),
    ("#22c55e", "Green"),
    ("#3b82f6", "Blue"),
    ("#f59e0b", "Yellow"),
    ("#7c3aed", "Purple"),
    ("#ec4899", "Pink"),
    ("#14b8a6", "Teal"),
    ("#f97316", "Orange"),
]


class GroupEditor(QDialog):
    """Dialog for creating or editing a group."""

    group_saved = Signal()

    def __init__(
        self,
        host_manager: HostManager,
        group: Group | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._group = group or Group()
        self._is_new = group is None or group.id is None
        self._selected_color: str | None = self._group.color

        self.setWindowTitle("New Group" if self._is_new else "Edit Group")
        self.setFixedSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Name
        layout.addWidget(self._make_label("Name"))
        self._name_edit = QLineEdit(self._group.name)
        self._name_edit.setPlaceholderText("e.g. Production")
        layout.addWidget(self._name_edit)

        # Parent group
        layout.addWidget(self._make_label("Parent Group"))
        self._parent_combo = QComboBox()
        self._parent_combo.addItem("None", None)
        for g in self._host_manager.list_groups():
            if g.id != self._group.id:
                self._parent_combo.addItem(g.name, g.id)
        if self._group.parent_id:
            idx = self._parent_combo.findData(self._group.parent_id)
            if idx >= 0:
                self._parent_combo.setCurrentIndex(idx)
        layout.addWidget(self._parent_combo)

        # Color swatches
        layout.addWidget(self._make_label("Color"))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)

        # "None" button
        self._none_btn = QPushButton("✕")
        self._none_btn.setFixedSize(28, 28)
        self._none_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._none_btn.setToolTip("No color")
        self._none_btn.clicked.connect(lambda: self._set_color(None))
        color_row.addWidget(self._none_btn)

        self._color_buttons: list[tuple[QPushButton, str]] = []
        for hex_color, name in GROUP_COLORS:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked=False, c=hex_color: self._set_color(c))
            self._color_buttons.append((btn, hex_color))
            color_row.addWidget(btn)

        color_row.addStretch()
        layout.addLayout(color_row)
        self._update_color_buttons()

        layout.addStretch()

        # Buttons
        save_btn = QPushButton("Save")
        save_btn.setProperty("cssClass", "primary")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return lbl

    def _set_color(self, color: str | None) -> None:
        self._selected_color = color
        self._update_color_buttons()

    def _update_color_buttons(self) -> None:
        active = self._selected_color

        # None button
        if active is None:
            self._none_btn.setStyleSheet(
                f"QPushButton {{ background-color: {Colors.BG_HOVER}; "
                f"border: 3px solid {Colors.TEXT_PRIMARY}; border-radius: 6px; "
                f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 700; }}"
            )
        else:
            self._none_btn.setStyleSheet(
                f"QPushButton {{ background-color: {Colors.BG_HOVER}; "
                f"border: 2px solid transparent; border-radius: 6px; "
                f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 700; }}"
                f"QPushButton:hover {{ border-color: {Colors.TEXT_PRIMARY}; }}"
            )

        for btn, hex_color in self._color_buttons:
            if hex_color == active:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {hex_color}; "
                    f"border: 3px solid {Colors.TEXT_PRIMARY}; border-radius: 6px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {hex_color}; "
                    f"border: 2px solid transparent; border-radius: 6px; }}"
                    f"QPushButton:hover {{ border-color: {Colors.TEXT_PRIMARY}; }}"
                )

    def _save(self) -> None:
        self._group.name = self._name_edit.text().strip()
        if not self._group.name:
            return
        self._group.parent_id = self._parent_combo.currentData()
        self._group.color = self._selected_color

        if self._is_new:
            self._host_manager.create_group(self._group)
        else:
            self._host_manager.update_group(self._group)

        self.group_saved.emit()
        self.accept()
