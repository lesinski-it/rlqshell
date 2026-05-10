"""Dual-pane file manager widget — local (left) + remote SFTP (right)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.protocols.ssh.sftp_session import FileEntry, SFTPSession
from rlqshell.ui.sftp.file_browser import FileBrowser
from rlqshell.ui.sftp.local_browser import LocalBrowser


def _is_downloadable(entry: FileEntry) -> bool:
    """Return True only for regular files and symlinks (skip sockets, FIFOs, devices)."""
    if entry.is_link:
        return True
    # permissions[0]: '-' regular, 'd' dir, 'l' link, 'p' FIFO, 's' socket, 'b'/'c' device
    if entry.permissions:
        return entry.permissions[0] == "-"
    # No permissions info — attempt download (fail gracefully in queue)
    return True

logger = logging.getLogger(__name__)

_ACTIVE_BORDER = f"2px solid {Colors.ACCENT}"
_INACTIVE_BORDER = f"2px solid {Colors.BORDER}"


def _panel_frame(active: bool) -> str:
    border = _ACTIVE_BORDER if active else _INACTIVE_BORDER
    return f"border: {border}; border-radius: 4px;"


class _PanelContainer(QWidget):
    """Wrapper that adds a header bar and coloured focus border around a browser."""

    def __init__(self, header_text: str, browser: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QLabel(header_text)
        self._header.setFixedHeight(28)
        self._header.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._header.setStyleSheet(
            f"background-color: {Colors.BG_SURFACE}; "
            f"color: {Colors.TEXT_SECONDARY}; "
            f"font-size: 11px; font-weight: 600; padding: 0 10px; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(self._header)
        layout.addWidget(browser, 1)

        self._set_active(False)

    def set_active(self, active: bool) -> None:
        self._set_active(active)

    def _set_active(self, active: bool) -> None:
        border_color = Colors.ACCENT if active else Colors.BORDER
        self._header.setStyleSheet(
            f"background-color: {Colors.BG_SURFACE}; "
            f"color: {'#FFFFFF' if active else Colors.TEXT_SECONDARY}; "
            f"font-size: 11px; font-weight: 600; padding: 0 10px; "
            f"border-bottom: 1px solid {Colors.BORDER}; "
            f"border-left: 3px solid {border_color};"
        )

    def set_header(self, text: str) -> None:
        self._header.setText(text)


class DualPaneWidget(QWidget):
    """Dual-pane SFTP file manager (local left, remote right)."""

    transfer_requested = Signal(str, str, str)  # direction, local_path, remote_path

    def __init__(
        self,
        sftp: SFTPSession,
        remote_label: str,
        local_start: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sftp = sftp
        self._active = "local"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter with two panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {Colors.BORDER}; }}")

        self._local = LocalBrowser(local_start)
        self._local_container = _PanelContainer(
            "Local: " + str(self._local.current_path), self._local
        )
        splitter.addWidget(self._local_container)

        self._remote = FileBrowser(sftp)
        self._remote_container = _PanelContainer(f"Remote: {remote_label}", self._remote)
        splitter.addWidget(self._remote_container)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

        # Action bar (NC-style F-key hints)
        action_bar = QWidget()
        action_bar.setFixedHeight(32)
        action_bar.setStyleSheet(
            f"background-color: {Colors.BG_SURFACE}; "
            f"border-top: 1px solid {Colors.BORDER};"
        )
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(12, 0, 12, 0)
        ab_layout.setSpacing(0)

        hints = [
            ("F2", "Rename"),
            ("F5", "Copy"),
            ("F6", "Move"),
            ("F7", "MkDir"),
            ("F8", "Delete"),
        ]
        for key, label in hints:
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet(
                f"background-color: {Colors.BG_HOVER}; color: {Colors.TEXT_PRIMARY}; "
                f"font-size: 11px; font-weight: 700; padding: 2px 6px; "
                f"border-radius: 3px; margin-right: 2px;"
            )
            desc_lbl = QLabel(label)
            desc_lbl.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; margin-right: 16px;"
            )
            ab_layout.addWidget(key_lbl)
            ab_layout.addWidget(desc_lbl)

        ab_layout.addStretch()
        layout.addWidget(action_bar)

        # Wire focus signals
        self._local.focused.connect(lambda: self._set_active("local"))
        self._remote.focused.connect(lambda: self._set_active("remote"))

        # Wire drag/drop between panels
        self._local.sftp_drop_requested.connect(self._on_sftp_drop_to_local)
        self._remote.local_drop_requested.connect(self._on_local_drop_to_remote)

        # Update local header when path changes (refresh after navigation)
        # We patch LocalBrowser.navigate to update header
        _orig_navigate = self._local.navigate

        def _patched_navigate(path: Path) -> None:
            _orig_navigate(path)
            self._local_container.set_header("Local: " + str(self._local.current_path))

        self._local.navigate = _patched_navigate  # type: ignore[method-assign]

        # Set initial active state
        self._local_container.set_active(True)
        self._remote_container.set_active(False)

        # Install event filter to catch F-keys from child widgets
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._local._table.installEventFilter(self)
        self._remote._table.installEventFilter(self)

    # ── Public API ────────────────────────────────────────────────────────────

    async def navigate_remote(self) -> None:
        await self._remote.navigate()

    def refresh_remote(self) -> None:
        asyncio.ensure_future(self._remote.navigate())

    def refresh_local(self) -> None:
        self._local.refresh()

    # ── Focus management ──────────────────────────────────────────────────────

    def _set_active(self, panel: str) -> None:
        self._active = panel
        self._local_container.set_active(panel == "local")
        self._remote_container.set_active(panel == "remote")

    def _toggle_active(self) -> None:
        self._set_active("remote" if self._active == "local" else "local")

    # ── Event filter for F-keys from child tables ─────────────────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            # Update active panel based on which table received the key
            if obj is self._local._table:
                self._set_active("local")
            elif obj is self._remote._table:
                self._set_active("remote")

            if key == Qt.Key.Key_F2:
                self._rename_in_active()
                return True
            elif key == Qt.Key.Key_F5:
                self._copy_active_to_other()
                return True
            elif key == Qt.Key.Key_F6:
                self._move_active_to_other()
                return True
            elif key == Qt.Key.Key_F7:
                self._mkdir_in_active()
                return True
            elif key == Qt.Key.Key_F8:
                self._delete_in_active()
                return True
            elif key == Qt.Key.Key_Tab:
                self._toggle_active()
                if self._active == "local":
                    self._local._table.setFocus()
                else:
                    self._remote._table.setFocus()
                return True
        return super().eventFilter(obj, event)

    # ── F-key operations ──────────────────────────────────────────────────────

    def _rename_in_active(self) -> None:
        if self._active == "local":
            entries = self._local.selected_entries()
            if len(entries) == 1:
                self._local._rename_entry(entries[0])
        else:
            entries = self._remote.selected_entries()
            if len(entries) == 1:
                self._remote._rename_entry(entries[0])

    def _copy_active_to_other(self) -> None:
        if self._active == "local":
            entries = self._local.selected_entries()
            if not entries:
                return
            for e in entries:
                if e.is_dir:
                    asyncio.ensure_future(
                        self._copy_dir_upload(Path(e.path), self._sftp.cwd)
                    )
                else:
                    remote = f"{self._sftp.cwd}/{e.name}"
                    self.transfer_requested.emit("upload", e.path, remote)
        else:
            entries = self._remote.selected_entries()
            if not entries:
                return
            for e in entries:
                if e.is_dir:
                    asyncio.ensure_future(
                        self._copy_dir_download(e.path, self._local.current_path)
                    )
                else:
                    local = str(self._local.current_path / e.name)
                    self.transfer_requested.emit("download", local, e.path)

    async def _copy_dir_upload(self, local_dir: Path, remote_parent: str) -> None:
        """Recursively upload a local directory into remote_parent."""
        from rlqshell.ui.sftp.local_browser import _list_dir

        remote_dir = f"{remote_parent}/{local_dir.name}"
        try:
            await self._sftp.mkdir(remote_dir)
        except Exception:
            pass  # directory may already exist
        try:
            for entry in _list_dir(local_dir):
                if entry.is_dir:
                    await self._copy_dir_upload(Path(entry.path), remote_dir)
                else:
                    self.transfer_requested.emit("upload", entry.path, f"{remote_dir}/{entry.name}")
        except Exception as exc:
            self._show_error(f"Upload failed in '{local_dir.name}': {exc}")
            logger.exception("Recursive upload failed: %s", local_dir)

    async def _copy_dir_download(self, remote_dir: str, local_parent: Path) -> None:
        """Recursively download a remote directory into local_parent."""
        dir_name = remote_dir.rstrip("/").split("/")[-1]
        local_dir = local_parent / dir_name
        try:
            os.makedirs(str(local_dir), exist_ok=True)
        except Exception as exc:
            self._show_error(f"Cannot create local folder '{dir_name}': {exc}")
            return
        try:
            entries = await self._sftp.list_dir(remote_dir)
            for entry in entries:
                if entry.is_dir:
                    await self._copy_dir_download(entry.path, local_dir)
                elif _is_downloadable(entry):
                    local_file = str(local_dir / entry.name)
                    self.transfer_requested.emit("download", local_file, entry.path)
                # else: skip sockets, FIFOs, block/char devices
        except Exception as exc:
            self._show_error(f"Download failed in '{dir_name}': {exc}")
            logger.exception("Recursive download failed: %s", remote_dir)

    def _move_active_to_other(self) -> None:
        entries = (
            self._local.selected_entries()
            if self._active == "local"
            else self._remote.selected_entries()
        )
        if not entries:
            return

        direction = "upload" if self._active == "local" else "download"
        names = ", ".join(e.name for e in entries[:3])
        suffix = f" (+{len(entries) - 3} more)" if len(entries) > 3 else ""
        reply = QMessageBox.question(
            self, "Move",
            f"Move {names}{suffix} to "
            f"{'remote' if direction == 'upload' else 'local'} and delete source?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        asyncio.ensure_future(self._do_move(entries, direction))

    async def _do_move(self, entries, direction: str) -> None:
        import shutil

        for entry in entries:
            try:
                if direction == "upload":
                    if entry.is_dir:
                        await self._move_dir_upload_direct(Path(entry.path), self._sftp.cwd)
                        shutil.rmtree(entry.path)
                    else:
                        remote = f"{self._sftp.cwd}/{entry.name}"
                        await self._sftp.upload(entry.path, remote)
                        os.remove(entry.path)
                else:
                    if entry.is_dir:
                        await self._move_dir_download_direct(
                            entry.path, self._local.current_path
                        )
                        await self._sftp.rmdir_recursive(entry.path)
                    else:
                        local = str(self._local.current_path / entry.name)
                        await self._sftp.download(entry.path, local)
                        await self._sftp.delete(entry.path)
            except Exception as exc:
                self._show_error(f"Move failed for '{entry.name}': {exc}")
                logger.exception("Move failed: %s", entry.name)

        self._local.refresh()
        await self._remote.navigate()

    async def _move_dir_upload_direct(self, local_dir: Path, remote_parent: str) -> None:
        """Upload directory contents directly (for move, not via TransferQueue)."""
        from rlqshell.ui.sftp.local_browser import _list_dir

        remote_dir = f"{remote_parent}/{local_dir.name}"
        try:
            await self._sftp.mkdir(remote_dir)
        except Exception:
            pass
        for entry in _list_dir(local_dir):
            if entry.is_dir:
                await self._move_dir_upload_direct(Path(entry.path), remote_dir)
            else:
                await self._sftp.upload(entry.path, f"{remote_dir}/{entry.name}")

    async def _move_dir_download_direct(self, remote_dir: str, local_parent: Path) -> None:
        """Download directory contents directly (for move, not via TransferQueue)."""
        dir_name = remote_dir.rstrip("/").split("/")[-1]
        local_dir = local_parent / dir_name
        os.makedirs(str(local_dir), exist_ok=True)
        entries = await self._sftp.list_dir(remote_dir)
        for entry in entries:
            if entry.is_dir:
                await self._move_dir_download_direct(entry.path, local_dir)
            else:
                await self._sftp.download(entry.path, str(local_dir / entry.name))

    def _mkdir_in_active(self) -> None:
        if self._active == "local":
            self._local._on_mkdir()
        else:
            self._remote._on_mkdir()

    def _delete_in_active(self) -> None:
        if self._active == "local":
            entries = self._local.selected_entries()
            if entries:
                self._local._delete_entries(entries)
        else:
            entries = self._remote.selected_entries()
            if entries:
                self._remote._delete_entries(entries)

    # ── Drag & drop coordination ──────────────────────────────────────────────

    def _on_sftp_drop_to_local(self, remote_paths: list[str]) -> None:
        asyncio.ensure_future(self._handle_sftp_drop(remote_paths))

    async def _handle_sftp_drop(self, remote_paths: list[str]) -> None:
        import stat as _stat

        for remote_path in remote_paths:
            attrs = await self._sftp.stat(remote_path)
            if attrs and _stat.S_ISDIR(attrs.st_mode):
                await self._copy_dir_download(remote_path, self._local.current_path)
            else:
                filename = remote_path.split("/")[-1]
                local = str(self._local.current_path / filename)
                self.transfer_requested.emit("download", local, remote_path)

    def _on_local_drop_to_remote(self, local_paths: list[str]) -> None:
        for local_path in local_paths:
            if os.path.isdir(local_path):
                asyncio.ensure_future(
                    self._copy_dir_upload(Path(local_path), self._sftp.cwd)
                )
            else:
                filename = local_path.replace("\\", "/").split("/")[-1]
                remote = f"{self._sftp.cwd}/{filename}"
                self.transfer_requested.emit("upload", local_path, remote)

    def _show_error(self, message: str) -> None:
        from rlqshell.ui.widgets.toast import ToastManager

        ToastManager.instance().show_toast(message, "error", duration_ms=5000)
