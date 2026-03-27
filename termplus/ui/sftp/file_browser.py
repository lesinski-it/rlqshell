"""SFTP file browser — breadcrumb navigation, file table, context menu."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.protocols.ssh.sftp_session import FileEntry, SFTPSession

logger = logging.getLogger(__name__)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


class FileBrowser(QWidget):
    """Single SFTP session file browser."""

    transfer_requested = Signal(str, str, str)  # direction, local, remote

    def __init__(self, sftp: SFTPSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sftp = sftp
        self._entries: list[FileEntry] = []
        self._show_hidden = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            f"background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        tb_layout.setSpacing(8)

        # Navigation buttons
        self._back_btn = QPushButton("<")
        self._back_btn.setFixedSize(28, 28)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._go_up)
        tb_layout.addWidget(self._back_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._refresh)
        tb_layout.addWidget(self._refresh_btn)

        # Breadcrumb / path display
        self._path_label = QLabel("/")
        self._path_label.setStyleSheet(
            f"font-size: 12px; font-family: 'JetBrains Mono', monospace; "
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; padding: 0 8px;"
        )
        tb_layout.addWidget(self._path_label, 1)

        # Actions
        mkdir_btn = QPushButton("New Folder")
        mkdir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mkdir_btn.clicked.connect(self._on_mkdir)
        tb_layout.addWidget(mkdir_btn)

        upload_btn = QPushButton("Upload")
        upload_btn.setProperty("cssClass", "primary")
        upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_btn.clicked.connect(self._on_upload)
        tb_layout.addWidget(upload_btn)

        hidden_btn = QPushButton("Toggle Hidden")
        hidden_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hidden_btn.clicked.connect(self._toggle_hidden)
        tb_layout.addWidget(hidden_btn)

        layout.addWidget(toolbar)

        # File table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Modified", "Permissions"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.setStyleSheet(
            f"QTableWidget {{ gridline-color: {Colors.BORDER}; }}"
        )
        layout.addWidget(self._table)

    async def navigate(self, path: str | None = None) -> None:
        """Navigate to a directory and refresh the listing."""
        if path:
            await self._sftp.cd(path)
        self._path_label.setText(self._sftp.cwd)
        self._entries = await self._sftp.list_dir()
        self._populate_table()

    def _populate_table(self) -> None:
        visible = [
            e for e in self._entries
            if self._show_hidden or not e.name.startswith(".")
        ]
        self._table.setRowCount(len(visible))

        for row, entry in enumerate(visible):
            # Name
            icon = "📁 " if entry.is_dir else "📄 "
            name_item = QTableWidgetItem(icon + entry.name)
            name_item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry.is_dir:
                name_item.setForeground(QLabel().palette().text().color())
            self._table.setItem(row, 0, name_item)

            # Size
            size_text = "" if entry.is_dir else _human_size(entry.size)
            self._table.setItem(row, 1, QTableWidgetItem(size_text))

            # Modified
            mtime = entry.modified.strftime("%Y-%m-%d %H:%M") if entry.modified else ""
            self._table.setItem(row, 2, QTableWidgetItem(mtime))

            # Permissions
            self._table.setItem(row, 3, QTableWidgetItem(entry.permissions))

    def _on_double_click(self, row: int, col: int) -> None:
        item = self._table.item(row, 0)
        if not item:
            return
        entry: FileEntry = item.data(Qt.ItemDataRole.UserRole)
        if entry.is_dir:
            asyncio.ensure_future(self.navigate(entry.path))

    def _go_up(self) -> None:
        asyncio.ensure_future(self.navigate(".."))

    def _refresh(self) -> None:
        asyncio.ensure_future(self.navigate())

    def _toggle_hidden(self) -> None:
        self._show_hidden = not self._show_hidden
        self._populate_table()

    def _on_mkdir(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            asyncio.ensure_future(self._do_mkdir(name.strip()))

    async def _do_mkdir(self, name: str) -> None:
        try:
            await self._sftp.mkdir(name)
            await self.navigate()
        except Exception:
            logger.exception("Failed to create directory: %s", name)

    def _on_upload(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Upload Files")
        if files:
            for local in files:
                filename = local.replace("\\", "/").split("/")[-1]
                remote = f"{self._sftp.cwd}/{filename}"
                self.transfer_requested.emit("upload", local, remote)

    def _show_context_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if not item:
            return
        row = item.row()
        name_item = self._table.item(row, 0)
        if not name_item:
            return
        entry: FileEntry = name_item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)

        if not entry.is_dir:
            dl_action = menu.addAction("Download")
            dl_action.triggered.connect(lambda: self._download_file(entry))

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_entry(entry))

        menu.addSeparator()

        del_action = menu.addAction("Delete")
        del_action.triggered.connect(lambda: self._delete_entry(entry))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _download_file(self, entry: FileEntry) -> None:
        local, _ = QFileDialog.getSaveFileName(self, "Save As", entry.name)
        if local:
            self.transfer_requested.emit("download", local, entry.path)

    def _rename_entry(self, entry: FileEntry) -> None:
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=entry.name
        )
        if ok and new_name.strip() and new_name != entry.name:
            from pathlib import PurePosixPath

            parent = str(PurePosixPath(entry.path).parent)
            new_path = f"{parent}/{new_name.strip()}"
            asyncio.ensure_future(self._do_rename(entry.path, new_path))

    async def _do_rename(self, old_path: str, new_path: str) -> None:
        try:
            await self._sftp.rename(old_path, new_path)
            await self.navigate()
        except Exception:
            logger.exception("Rename failed: %s → %s", old_path, new_path)

    def _delete_entry(self, entry: FileEntry) -> None:
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self, "Delete",
            f"Delete {'directory' if entry.is_dir else 'file'} '{entry.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            asyncio.ensure_future(self._do_delete(entry))

    async def _do_delete(self, entry: FileEntry) -> None:
        try:
            if entry.is_dir:
                await self._sftp.rmdir(entry.path)
            else:
                await self._sftp.delete(entry.path)
            await self.navigate()
        except Exception:
            logger.exception("Delete failed: %s", entry.path)
