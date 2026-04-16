"""Tag pill and tag selector widgets."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors


class TagPill(QWidget):
    """A small tag display: outline (default) or filled style.

    - ``outline`` (default): transparent background with a 1-px border in the
      tag color, a small color dot before the name, and the name in the tag
      color. This is the new design language used in host cards.
    - ``filled``: solid colored pill with white text — used by the editor's
      :class:`TagSelector` where pills are interactive (removable).
    """

    remove_clicked = Signal(int)  # tag_id

    def __init__(
        self,
        tag_id: int,
        name: str,
        color: str = "#6c757d",
        removable: bool = False,
        style: Literal["outline", "filled"] = "outline",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tag_id = tag_id
        self._style = style

        layout = QHBoxLayout(self)
        layout.setSpacing(5)

        if style == "outline":
            layout.setContentsMargins(7, 2, 6 if removable else 8, 2)
            # Color dot marker
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(
                f"background-color: {color}; border-radius: 3px;"
            )
            layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

            label = QLabel(name)
            label.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: 600; "
                f"background: transparent; letter-spacing: 0.3px;"
            )
            layout.addWidget(label)

            if removable:
                close_btn = QPushButton("\u00d7")  # ×
                close_btn.setFixedSize(13, 13)
                close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                close_btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; border: none; "
                    f"color: {color}; font-size: 13px; font-weight: 700; "
                    f"padding: 0; margin: 0; }}"
                    f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
                )
                close_btn.clicked.connect(lambda: self.remove_clicked.emit(self._tag_id))
                layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setStyleSheet(
                f"TagPill {{ background-color: transparent; "
                f"border: 1px solid {color}; border-radius: 4px; }}"
            )
            self.setFixedHeight(20)
        else:  # filled
            layout.setContentsMargins(8, 3, 8, 3)
            label = QLabel(name)
            label.setStyleSheet(
                f"color: #ffffff; font-size: 11px; font-weight: 600; "
                f"background: transparent;"
            )
            layout.addWidget(label)

            if removable:
                close_btn = QPushButton("\u00d7")
                close_btn.setFixedSize(14, 14)
                close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                close_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; "
                    "color: rgba(255,255,255,0.7); font-size: 12px; font-weight: 700; }"
                    "QPushButton:hover { color: #ffffff; }"
                )
                close_btn.clicked.connect(lambda: self.remove_clicked.emit(self._tag_id))
                layout.addWidget(close_btn)

            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
            f"  background-color: {Colors.BG_HOVER}; "
            f"  border: none; "
            f"  border-radius: 4px; padding: 2px 11px; "
            f"  color: {Colors.TEXT_MUTED}; font-size: 10px; font-weight: 600; "
            f"}}"
            f"QPushButton:hover {{ "
            f"  background-color: {Colors.BG_ACTIVE}; "
            f"  color: {Colors.TEXT_SECONDARY}; "
            f"}}"
        )
        self._add_btn.setFixedHeight(20)

        self._rebuild()

    def set_tags(self, tags: list[dict]) -> None:
        """Set the displayed tags: [{id, name, color}]."""
        self._tags = list(tags)
        self._rebuild()

    def _rebuild(self) -> None:
        # Remove all widgets from layout but keep _add_btn alive
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w and w is not self._add_btn:
                w.deleteLater()

        for tag in self._tags:
            pill = TagPill(
                tag["id"],
                tag["name"],
                tag.get("color", Colors.TEXT_MUTED),
                removable=True,
                style="outline",
            )
            pill.remove_clicked.connect(self._on_remove)
            self._layout.addWidget(pill)

        self._layout.addWidget(self._add_btn)
        self._layout.addStretch()

    def _on_remove(self, tag_id: int) -> None:
        self._tags = [t for t in self._tags if t["id"] != tag_id]
        self._rebuild()
        self.tags_changed.emit([t["id"] for t in self._tags])
