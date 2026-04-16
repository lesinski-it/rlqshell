"""Simple remote text file editor dialog."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.protocols.ssh.sftp_session import SFTPSession

logger = logging.getLogger(__name__)


class RemoteTextEditor(QDialog):
    """Modal dialog for editing a remote text file."""

    def __init__(
        self,
        sftp: SFTPSession,
        remote_path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sftp = sftp
        self._remote_path = remote_path
        self._original_content = ""

        filename = remote_path.rsplit("/", 1)[-1]
        self.setWindowTitle(f"Edit: {filename}")
        self.setMinimumSize(700, 500)
        self.resize(900, 600)

        self.setStyleSheet(
            f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet(
            f"background-color: {Colors.BG_DARKER}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        path_label = QLabel(remote_path)
        path_label.setStyleSheet(
            f"font-size: 12px; font-family: 'JetBrains Mono', monospace; "
            f"color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        h_layout.addWidget(path_label, 1)

        self._status_label = QLabel("Loading...")
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        h_layout.addWidget(self._status_label)

        layout.addWidget(header)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("JetBrains Mono", 12))
        self._editor.setStyleSheet(
            f"QPlainTextEdit {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"  border: none; "
            f"  selection-background-color: {Colors.ACCENT}; "
            f"  padding: 12px; "
            f"}}"
        )
        self._editor.setTabStopDistance(32)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setReadOnly(True)
        layout.addWidget(self._editor, 1)

        # Footer with buttons
        footer = QWidget()
        footer.setFixedHeight(48)
        footer.setStyleSheet(
            f"background-color: {Colors.BG_DARKER}; "
            f"border-top: 1px solid {Colors.BORDER};"
        )
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(16, 0, 16, 0)
        f_layout.setSpacing(8)

        f_layout.addStretch()

        self._cancel_btn = QPushButton("Close")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ padding: 6px 16px; font-size: 12px; "
            f"color: {Colors.TEXT_SECONDARY}; background-color: {Colors.BG_HOVER}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {Colors.BG_ACTIVE}; }}"
        )
        self._cancel_btn.clicked.connect(self.reject)
        f_layout.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ padding: 6px 16px; font-size: 12px; font-weight: 600; "
            f"color: white; background-color: {Colors.ACCENT}; "
            f"border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_HOVER}; }}"
            f"QPushButton:disabled {{ background-color: {Colors.BG_HOVER}; "
            f"color: {Colors.TEXT_MUTED}; }}"
        )
        self._save_btn.clicked.connect(self._on_save)
        f_layout.addWidget(self._save_btn)

        layout.addWidget(footer)

        # Ctrl+S shortcut
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._on_save)

        # Load file
        asyncio.ensure_future(self._load_file())

    async def _load_file(self) -> None:
        try:
            data = await self._sftp.read_file(self._remote_path)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
            self._original_content = text
            self._editor.setPlainText(text)
            self._editor.setReadOnly(False)
            self._save_btn.setEnabled(True)
            self._status_label.setText(f"{len(data)} bytes")
        except ValueError as exc:
            self._status_label.setText(str(exc))
            self._editor.setPlainText(f"Cannot open: {exc}")
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {Colors.DANGER}; background: transparent;"
            )
        except Exception as exc:
            logger.exception("Failed to read file: %s", self._remote_path)
            self._status_label.setText("Error")
            self._editor.setPlainText(f"Failed to read file:\n{exc}")
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {Colors.DANGER}; background: transparent;"
            )

    def _on_save(self) -> None:
        if self._editor.isReadOnly():
            return
        asyncio.ensure_future(self._save_file())

    async def _save_file(self) -> None:
        content = self._editor.toPlainText()
        self._save_btn.setEnabled(False)
        self._status_label.setText("Saving...")
        try:
            await self._sftp.write_file(
                self._remote_path, content.encode("utf-8")
            )
            self._original_content = content
            self._status_label.setText("Saved")
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {Colors.SUCCESS}; background: transparent;"
            )
        except Exception as exc:
            logger.exception("Failed to save file: %s", self._remote_path)
            self._status_label.setText("Save failed")
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {Colors.DANGER}; background: transparent;"
            )
            from rlqshell.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(
                f"Save failed: {exc}", "error", duration_ms=5000
            )
        finally:
            self._save_btn.setEnabled(True)
