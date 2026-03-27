"""Tag pill and tag selector widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors


class TagPill(QWidget):
    """A small rounded colored pill displaying a tag name."""

    remove_clicked = Signal(int)  # tag_id

    def __init__(
        self,
        tag_id: int,
        name: str,
        color: str = "#6c757d",
        removable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tag_id = tag_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(4)

        label = QLabel(name)
        label.setStyleSheet(
            f"color: #ffffff; font-size: 11px; font-weight: 600; "
            f"background: transparent;"
        )
        layout.addWidget(label)

        if removable:
            close_btn = QPushButton("x")
            close_btn.setFixedSize(14, 14)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; "
                "color: rgba(255,255,255,0.7); font-size: 10px; font-weight: 700; }"
                "QPushButton:hover { color: #ffffff; }"
            )
            close_btn.clicked.connect(lambda: self.remove_clicked.emit(self._tag_id))
            layout.addWidget(close_btn)

        self.setStyleSheet(
            f"TagPill {{ background-color: {color}; border-radius: 10px; }}"
        )
        self.setFixedHeight(22)

    @property
    def tag_id(self) -> int:
        return self._tag_id


class TagSelector(QWidget):
    """A flow layout of tag pills with an 'add' button."""

    tags_changed = Signal(list)  # list of tag_ids

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[dict] = []  # [{id, name, color}]

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._add_btn = QPushButton("+ Tag")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: 1px dashed {Colors.BORDER}; "
            f"  border-radius: 10px; padding: 3px 10px; "
            f"  color: {Colors.TEXT_MUTED}; font-size: 11px; "
            f"}}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; color: {Colors.ACCENT}; }}"
        )
        self._add_btn.setFixedHeight(22)

        self._rebuild()

    def set_tags(self, tags: list[dict]) -> None:
        """Set the displayed tags: [{id, name, color}]."""
        self._tags = list(tags)
        self._rebuild()

    def _rebuild(self) -> None:
        # Clear layout except add button
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for tag in self._tags:
            pill = TagPill(tag["id"], tag["name"], tag.get("color", "#6c757d"), removable=True)
            pill.remove_clicked.connect(self._on_remove)
            self._layout.addWidget(pill)

        self._layout.addWidget(self._add_btn)
        self._layout.addStretch()

    def _on_remove(self, tag_id: int) -> None:
        self._tags = [t for t in self._tags if t["id"] != tag_id]
        self._rebuild()
        self.tags_changed.emit([t["id"] for t in self._tags])
