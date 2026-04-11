"""Snippet package editor dialog — create or rename a snippet package."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.models.snippet import SnippetPackage
from rlqshell.core.snippet_manager import SnippetManager


class SnippetPackageEditor(QDialog):
    """Dialog for creating or renaming a snippet package."""

    def __init__(
        self,
        snippet_manager: SnippetManager,
        package_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = snippet_manager
        self._package_id = package_id
        self._loaded: SnippetPackage | None = None
        self._saved_id: int | None = None

        self.setWindowTitle("Rename Package" if package_id else "New Package")
        self.setFixedSize(420, 200)

        self._build_ui()
        self._apply_style()

        if package_id is not None:
            self._load_package(package_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        layout.addWidget(self._make_label("Name"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Nginx")
        layout.addWidget(self._name_edit)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(
            f"color: {Colors.DANGER}; font-size: 12px; background: transparent;"
        )
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addStretch()

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

    def _load_package(self, package_id: int) -> None:
        for pkg in self._manager.list_packages():
            if pkg.id == package_id:
                self._loaded = pkg
                self._name_edit.setText(pkg.name)
                return

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Name is required.")
            return

        if self._package_id is not None:
            if self._loaded is None:
                self.reject()
                return
            self._loaded.name = name
            self._manager.update_package(self._loaded)
            self._saved_id = self._package_id
        else:
            self._saved_id = self._manager.create_package(SnippetPackage(name=name))

        self.accept()

    @property
    def saved_id(self) -> int | None:
        return self._saved_id

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
            QLineEdit {{
                background-color: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT};
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
