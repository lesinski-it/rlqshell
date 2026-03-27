"""Group editor dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.models.host import Group


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

        self.setWindowTitle("New Group" if self._is_new else "Edit Group")
        self.setFixedSize(400, 280)

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

        # Color
        layout.addWidget(self._make_label("Color"))
        self._color_combo = QComboBox()
        self._color_combo.addItems(["None", "#e94560", "#22c55e", "#3b82f6", "#f59e0b", "#7c3aed"])
        if self._group.color:
            idx = self._color_combo.findText(self._group.color)
            if idx >= 0:
                self._color_combo.setCurrentIndex(idx)
        layout.addWidget(self._color_combo)

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

    def _save(self) -> None:
        self._group.name = self._name_edit.text().strip()
        if not self._group.name:
            return
        self._group.parent_id = self._parent_combo.currentData()
        color = self._color_combo.currentText()
        self._group.color = color if color != "None" else None

        if self._is_new:
            self._host_manager.create_group(self._group)
        else:
            self._host_manager.update_group(self._group)

        self.group_saved.emit()
        self.accept()
