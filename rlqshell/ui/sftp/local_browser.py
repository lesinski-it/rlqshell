"""Local filesystem browser for the dual-pane SFTP file manager."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors

logger = logging.getLogger(__name__)

_SFTP_MIME = "application/x-rlqshell-sftp-paths"
_IS_WINDOWS = platform.system() == "Windows"


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


@dataclass
class LocalFileEntry:
    name: str
    path: str
    size: int
    is_dir: bool
    modified: datetime | None
    is_hidden: bool = False


def _is_hidden(entry: os.DirEntry) -> bool:
    if _IS_WINDOWS:
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(  # type: ignore[attr-defined]
                entry.path
            )
            return bool(attrs != -1 and attrs & 2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            return entry.name.startswith(".")
    return entry.name.startswith(".")


def _list_dir(path: Path) -> list[LocalFileEntry]:
    entries: list[LocalFileEntry] = []
    try:
        for de in os.scandir(str(path)):
            try:
                st = de.stat(follow_symlinks=False)
                mtime = datetime.fromtimestamp(st.st_mtime) if st.st_mtime else None
                entries.append(LocalFileEntry(
                    name=de.name,
                    path=de.path,
                    size=st.st_size if not de.is_dir(follow_symlinks=False) else 0,
                    is_dir=de.is_dir(follow_symlinks=False),
                    modified=mtime,
                    is_hidden=_is_hidden(de),
                ))
            except (OSError, PermissionError):
                continue
    except PermissionError:
        pass
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


class _LocalTable(QTableWidget):
    """Table widget with drag support for local files."""

    drag_started = Signal(list)  # list[str] local paths

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_start_pos = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
        ):
            from PySide6.QtCore import QPoint
            delta: QPoint = event.pos() - self._drag_start_pos
            if delta.manhattanLength() > 10:
                self._drag_start_pos = None
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def _start_drag(self) -> None:
        paths = [
            item.data(Qt.ItemDataRole.UserRole).path
            for item in self.selectedItems()
            if item.column() == 0 and item.data(Qt.ItemDataRole.UserRole) is not None
        ]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_SFTP_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_SFTP_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_SFTP_MIME):
            raw = bytes(event.mimeData().data(_SFTP_MIME)).decode()
            paths = json.loads(raw)
            # Bubble up to LocalBrowser via parent chain
            browser = self.parent()
            while browser and not isinstance(browser, LocalBrowser):
                browser = browser.parent()
            if isinstance(browser, LocalBrowser):
                browser.sftp_drop_requested.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class LocalBrowser(QWidget):
    """Local filesystem pane for the dual-pane file manager."""

    sftp_drop_requested = Signal(list)  # list[str] remote paths to download
    focused = Signal()

    def __init__(self, start_path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = start_path or (Path("C:\\") if _IS_WINDOWS else Path.home())
        self._entries: list[LocalFileEntry] = []
        self._show_hidden = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            f"background-color: {Colors.BG_PRIMARY}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 6, 12, 6)
        tb.setSpacing(8)

        self._back_btn = QPushButton("..")
        self._back_btn.setFixedSize(28, 28)
        self._back_btn.setToolTip("Go to parent directory")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ font-size: 13px; font-weight: 700; color: {Colors.TEXT_SECONDARY}; "
            f"background-color: {Colors.BG_HOVER}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; padding: 0; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
            f"background-color: {Colors.BG_ACTIVE}; }}"
        )
        self._back_btn.clicked.connect(self._go_up)
        tb.addWidget(self._back_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        tb.addWidget(refresh_btn)

        self._path_label = QLabel(str(self._path))
        self._path_label.setStyleSheet(
            f"font-size: 12px; font-family: 'JetBrains Mono', monospace; "
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; padding: 0 8px;"
        )
        tb.addWidget(self._path_label, 1)

        mkdir_btn = QPushButton("New Folder")
        mkdir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mkdir_btn.clicked.connect(self._on_mkdir)
        tb.addWidget(mkdir_btn)

        self._hidden_btn = QPushButton("Show Hidden")
        self._hidden_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hidden_btn.clicked.connect(self._toggle_hidden)
        tb.addWidget(self._hidden_btn)

        layout.addWidget(toolbar)

        self._table = _LocalTable(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Modified"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.setAcceptDrops(True)
        self._table.setStyleSheet(f"QTableWidget {{ gridline-color: {Colors.BORDER}; }}")
        self._table.keyPressEvent = self._on_table_key_press
        self._table.mousePressEvent = self._on_table_mouse_press_wrapped(  # type: ignore[method-assign]
            self._table.mousePressEvent
        )
        layout.addWidget(self._table)

        self.refresh()

    def _on_table_mouse_press_wrapped(self, original):
        def handler(event):
            self.focused.emit()
            original(event)
        return handler

    @property
    def current_path(self) -> Path:
        return self._path

    def selected_entries(self) -> list[LocalFileEntry]:
        seen: set[int] = set()
        result: list[LocalFileEntry] = []
        for item in self._table.selectedItems():
            row = item.row()
            if row in seen:
                continue
            seen.add(row)
            name_item = self._table.item(row, 0)
            if name_item:
                result.append(name_item.data(Qt.ItemDataRole.UserRole))
        return result

    def navigate(self, path: Path) -> None:
        try:
            self._path = path.resolve()
        except (OSError, ValueError):
            self._path = path
        self._path_label.setText(str(self._path))
        self.refresh()

    def refresh(self) -> None:
        self._entries = _list_dir(self._path)
        self._populate_table()

    def _populate_table(self) -> None:
        visible = [e for e in self._entries if self._show_hidden or not e.is_hidden]
        self._table.setRowCount(len(visible))
        for row, entry in enumerate(visible):
            icon = "📁 " if entry.is_dir else "📄 "
            name_item = QTableWidgetItem(icon + entry.name)
            name_item.setData(Qt.ItemDataRole.UserRole, entry)
            self._table.setItem(row, 0, name_item)

            size_text = "" if entry.is_dir else _human_size(entry.size)
            self._table.setItem(row, 1, QTableWidgetItem(size_text))

            mtime = entry.modified.strftime("%Y-%m-%d %H:%M") if entry.modified else ""
            self._table.setItem(row, 2, QTableWidgetItem(mtime))

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if not item:
            return
        entry: LocalFileEntry = item.data(Qt.ItemDataRole.UserRole)
        if entry.is_dir:
            self.navigate(Path(entry.path))

    def _go_up(self) -> None:
        parent = self._path.parent
        if parent != self._path:
            self.navigate(parent)

    def _toggle_hidden(self) -> None:
        self._show_hidden = not self._show_hidden
        self._hidden_btn.setText("Hide Hidden" if self._show_hidden else "Show Hidden")
        self._populate_table()

    def _on_table_key_press(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Delete:
            entries = self.selected_entries()
            if entries:
                self._delete_entries(entries)
        elif key == Qt.Key.Key_F2:
            entries = self.selected_entries()
            if len(entries) == 1:
                self._rename_entry(entries[0])
        elif key == Qt.Key.Key_Backspace:
            self._go_up()
        else:
            QTableWidget.keyPressEvent(self._table, event)

    def _on_mkdir(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            new_path = self._path / name.strip()
            try:
                os.makedirs(str(new_path), exist_ok=True)
                self.refresh()
            except Exception as exc:
                self._show_error(f"Cannot create folder: {exc}")

    def _show_context_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if not item:
            return
        entry: LocalFileEntry = self._table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        selected = self.selected_entries()
        multi = len(selected) > 1

        menu = QMenu(self)

        if not multi:
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename_entry(entry))
            menu.addSeparator()

        del_label = f"Delete ({len(selected)})" if multi else "Delete"
        del_action = menu.addAction(del_label)
        del_action.triggered.connect(lambda: self._delete_entries(selected))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _rename_entry(self, entry: LocalFileEntry) -> None:
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=entry.name)
        if ok and new_name.strip() and new_name != entry.name:
            new_path = self._path / new_name.strip()
            try:
                os.rename(entry.path, str(new_path))
                self.refresh()
            except Exception as exc:
                self._show_error(f"Rename failed: {exc}")

    def _delete_entries(self, entries: list[LocalFileEntry]) -> None:
        if len(entries) == 1:
            e = entries[0]
            msg = f"Delete {'directory' if e.is_dir else 'file'} '{e.name}'?"
        else:
            msg = f"Delete {len(entries)} selected items?"

        reply = QMessageBox.question(
            self, "Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for entry in entries:
            try:
                if entry.is_dir:
                    shutil.rmtree(entry.path)
                else:
                    os.remove(entry.path)
            except Exception as exc:
                self._show_error(f"Cannot delete '{entry.name}': {exc}")
        self.refresh()

    def _show_error(self, message: str) -> None:
        from rlqshell.ui.widgets.toast import ToastManager

        ToastManager.instance().show_toast(message, "error", duration_ms=5000)
