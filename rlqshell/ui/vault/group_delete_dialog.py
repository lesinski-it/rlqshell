"""Group delete confirmation dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from rlqshell.app.constants import Colors
from rlqshell.core.models.host import Group


class GroupDeleteDialog(QDialog):
    """Confirm deletion of a group and optionally pick a destination for its hosts."""

    def __init__(
        self,
        group_name: str,
        host_count: int,
        other_groups: list[Group],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.destination_group_id: int | None = None

        self.setWindowTitle("Delete Group")
        self.setFixedSize(420, 220 if host_count > 0 else 170)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"Delete group '{group_name}'?")
        title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        self._combo: QComboBox | None = None
        if host_count > 0:
            info = QLabel(f"{host_count} host(s) will be moved to:")
            info.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; "
                f"background: transparent;"
            )
            layout.addWidget(info)

            self._combo = QComboBox()
            self._combo.addItem("No group", None)
            for g in other_groups:
                self._combo.addItem(g.name, g.id)
            layout.addWidget(self._combo)
        else:
            info = QLabel("This group is empty.")
            info.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; "
                f"background: transparent;"
            )
            layout.addWidget(info)

        layout.addStretch()

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        buttons_row.addWidget(cancel_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setProperty("cssClass", "primary")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_accept)
        buttons_row.addWidget(delete_btn)

        layout.addLayout(buttons_row)

    def _on_accept(self) -> None:
        if self._combo is not None:
            self.destination_group_id = self._combo.currentData()
        self.accept()
