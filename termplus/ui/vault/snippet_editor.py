"""Snippet editor dialog — create/edit a saved command."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.models.snippet import Snippet
from termplus.core.snippet_manager import SnippetManager


class SnippetEditor(QDialog):
    """Dialog for creating or editing a snippet."""

    def __init__(
        self,
        snippet_manager: SnippetManager,
        snippet_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = snippet_manager
        self._snippet_id = snippet_id

        self.setWindowTitle("Edit Snippet" if snippet_id else "New Snippet")
        self.setFixedSize(500, 440)

        self._build_ui()
        self._apply_style()

        if snippet_id:
            self._load_snippet(snippet_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Name
        layout.addWidget(self._make_label("Name"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. restart-nginx")
        layout.addWidget(self._name_edit)

        # Package
        layout.addWidget(self._make_label("Package"))
        self._package_combo = QComboBox()
        self._package_combo.addItem("— None —", None)
        for pkg in self._manager.list_packages():
            self._package_combo.addItem(pkg.name, pkg.id)
        layout.addWidget(self._package_combo)

        # Script
        layout.addWidget(self._make_label("Script"))
        self._script_edit = QTextEdit()
        self._script_edit.setPlaceholderText("sudo systemctl restart nginx")
        self._script_edit.setMinimumHeight(100)
        self._script_edit.setStyleSheet(
            f"font-family: 'JetBrains Mono', monospace; font-size: 13px; "
            f"background-color: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; padding: 8px;"
        )
        layout.addWidget(self._script_edit)

        # Description
        layout.addWidget(self._make_label("Description (optional)"))
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Brief description of what this does")
        layout.addWidget(self._desc_edit)

        # Run as sudo
        self._sudo_check = QCheckBox("Run as sudo")
        self._sudo_check.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;"
        )
        layout.addWidget(self._sudo_check)

        # Error
        self._error_label = QLabel()
        self._error_label.setStyleSheet(
            f"color: {Colors.DANGER}; font-size: 12px; background: transparent;"
        )
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveBtn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _load_snippet(self, snippet_id: int) -> None:
        snippet = self._manager.get_snippet(snippet_id)
        if not snippet:
            return
        self._name_edit.setText(snippet.name)
        self._script_edit.setPlainText(snippet.script)
        self._desc_edit.setText(snippet.description or "")
        self._sudo_check.setChecked(snippet.run_as_sudo)
        if snippet.package_id:
            idx = self._package_combo.findData(snippet.package_id)
            if idx >= 0:
                self._package_combo.setCurrentIndex(idx)

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        script = self._script_edit.toPlainText().strip()

        if not name:
            self._show_error("Name is required.")
            return
        if not script:
            self._show_error("Script is required.")
            return

        snippet = Snippet(
            id=self._snippet_id,
            name=name,
            script=script,
            description=self._desc_edit.text().strip() or None,
            package_id=self._package_combo.currentData(),
            run_as_sudo=self._sudo_check.isChecked(),
        )

        if self._snippet_id:
            self._manager.update_snippet(snippet)
        else:
            self._manager.create_snippet(snippet)

        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        return lbl

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_PRIMARY};
            }}
            QLineEdit, QComboBox {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {Colors.ACCENT};
            }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT};
                border: 1px solid {Colors.BORDER};
            }}
            QPushButton#saveBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-size: 13px; font-weight: 600;
            }}
            QPushButton#saveBtn:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton#cancelBtn {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER}; border-radius: 6px;
                padding: 8px 16px; font-size: 13px;
            }}
            QPushButton#cancelBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
        """)
