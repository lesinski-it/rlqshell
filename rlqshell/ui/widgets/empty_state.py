"""Empty state placeholder with title, description, and CTA button."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors


class EmptyState(QWidget):
    """Centered empty state with optional action button."""

    action_clicked = Signal()

    def __init__(
        self,
        title: str = "Nothing here yet",
        description: str = "",
        action_text: str | None = None,
        icon_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(40, 40, 40, 40)

        if icon_text:
            icon_label = QLabel(icon_text)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(
                f"font-size: 48px; color: {Colors.TEXT_MUTED}; background: transparent;"
            )
            layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            f"font-size: 18px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_label.setWordWrap(True)
            # heightForWidth so wrapped lines aren't clipped by the parent layout
            sp = desc_label.sizePolicy()
            sp.setHeightForWidth(True)
            sp.setVerticalPolicy(QSizePolicy.Policy.MinimumExpanding)
            desc_label.setSizePolicy(sp)
            desc_label.setStyleSheet(
                f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; "
                f"background: transparent; line-height: 150%;"
            )
            layout.addWidget(desc_label)

        if action_text:
            btn = QPushButton(action_text)
            btn.setProperty("cssClass", "primary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(200)
            btn.clicked.connect(self.action_clicked.emit)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
