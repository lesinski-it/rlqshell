"""Dialog for filling in snippet variables ({{name}} placeholders)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors


class SnippetVariableDialog(QDialog):
    """Prompt the user for values for each ``{{variable}}``."""

    def __init__(
        self,
        variable_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fill Variables")
        self.setMinimumWidth(400)
        self._inputs: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QLabel("Enter values for script variables:")
        header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(header)

        for name in variable_names:
            lbl = QLabel(f"{{{{{name}}}}}")
            lbl.setStyleSheet(
                f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
                f"font-family: monospace; background: transparent;"
            )
            layout.addWidget(lbl)

            edit = QLineEdit()
            edit.setPlaceholderText(f"Value for {name}")
            edit.setStyleSheet(
                f"background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
                f"padding: 8px 12px; font-size: 13px;"
            )
            layout.addWidget(edit)
            self._inputs[name] = edit

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 8px 16px; font-size: 13px;"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("Apply")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            f"background-color: {Colors.ACCENT}; color: #ffffff; "
            f"border: none; border-radius: 6px; "
            f"padding: 8px 20px; font-size: 13px; font-weight: 600;"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")

        if variable_names:
            self._inputs[variable_names[0]].setFocus()

    @property
    def values(self) -> dict[str, str]:
        return {name: edit.text() for name, edit in self._inputs.items()}
