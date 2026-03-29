"""Transfer queue — tracks SFTP uploads/downloads with progress."""

from __future__ import annotations

import asyncio
import logging
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.protocols.ssh.sftp_session import SFTPSession

logger = logging.getLogger(__name__)


class _TransferItem(QWidget):
    """Single transfer progress row."""

    cancel_requested = Signal(str)  # transfer_id

    def __init__(
        self, transfer_id: str, filename: str, direction: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_id = transfer_id
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Direction indicator
        arrow = "↑" if direction == "upload" else "↓"
        dir_label = QLabel(arrow)
        dir_label.setFixedWidth(16)
        dir_label.setStyleSheet(
            f"font-size: 14px; color: {Colors.ACCENT_LIGHT}; background: transparent;"
        )
        layout.addWidget(dir_label)

        # Filename
        name_label = QLabel(filename)
        name_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        layout.addWidget(name_label, 1)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedWidth(120)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # Status label
        self._status = QLabel("Queued")
        self._status.setFixedWidth(80)
        self._status.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self._status)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setToolTip("Cancel transfer")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ font-size: 10px; color: {Colors.TEXT_SECONDARY}; "
            f"background-color: {Colors.BG_HOVER}; border: 1px solid {Colors.BORDER}; border-radius: 3px; "
            f"padding: 0 6px; }}"
            f"QPushButton:hover {{ background-color: {Colors.DANGER}; color: white; border-color: {Colors.DANGER}; }}"
        )
        cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._transfer_id))
        layout.addWidget(cancel_btn)

    def set_progress(self, pct: int) -> None:
        self._progress.setValue(pct)
        self._status.setText(f"{pct}%")

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def mark_complete(self) -> None:
        self._progress.setValue(100)
        self._status.setText("Done")
        self._status.setStyleSheet(
            f"font-size: 11px; color: {Colors.SUCCESS}; background: transparent;"
        )

    def mark_error(self, msg: str = "Error") -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(
            f"font-size: 11px; color: {Colors.DANGER}; background: transparent;"
        )


class TransferQueue(QWidget):
    """Collapsible panel showing active transfers."""

    upload_completed = Signal(object)  # SFTPSession — emitted after successful upload

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = True
        # Per-session locks: only 1 active transfer per SFTPSession (paramiko is not thread-safe)
        self._session_locks: dict[int, asyncio.Lock] = {}
        # Pending upload count per session — refresh only after last upload finishes
        self._pending_uploads: dict[int, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (toggle)
        header = QWidget()
        header.setFixedHeight(32)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(
            f"background-color: {Colors.BG_DARKER}; "
            f"border-top: 1px solid {Colors.BORDER};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 4, 12, 4)

        self._title = QLabel("Transfers (0)")
        self._title.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        h_layout.addWidget(self._title)

        # Global progress bar (visible only during active transfers)
        self._global_progress = QProgressBar()
        self._global_progress.setFixedSize(160, 12)
        self._global_progress.setMaximum(100)
        self._global_progress.setValue(0)
        self._global_progress.setTextVisible(False)
        self._global_progress.setStyleSheet(
            f"QProgressBar {{ background-color: {Colors.BG_HOVER}; border: none; border-radius: 6px; }}"
            f"QProgressBar::chunk {{ background-color: {Colors.ACCENT}; border-radius: 6px; }}"
        )
        self._global_progress.setVisible(False)
        h_layout.addWidget(self._global_progress)

        self._global_pct_label = QLabel("")
        self._global_pct_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.ACCENT_LIGHT}; background: transparent; min-width: 36px;"
        )
        self._global_pct_label.setVisible(False)
        h_layout.addWidget(self._global_pct_label)

        h_layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("cssClass", "flat")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"border: none; padding: 2px 6px;"
        )
        clear_btn.clicked.connect(self._clear_completed)
        h_layout.addWidget(clear_btn)

        header.mousePressEvent = lambda e: self._toggle()
        layout.addWidget(header)

        # Scroll area for transfers
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(200)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(self._scroll)

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._container)

        self._transfers: dict[str, _TransferItem] = {}
        self._scroll.setVisible(False)
        self._active_count = 0      # currently running transfers
        self._total_count = 0       # total in current batch (resets when all done)
        self._done_count = 0        # completed in current batch
        self._current_file_pct = 0  # progress of the currently active file (0-100)

    def add_transfer(
        self,
        sftp: SFTPSession,
        direction: str,
        local_path: str,
        remote_path: str,
    ) -> str:
        """Queue a new transfer. Returns the transfer ID."""
        transfer_id = str(uuid.uuid4())[:8]
        filename = local_path.replace("\\", "/").split("/")[-1]

        item = _TransferItem(transfer_id, filename, direction)
        item.cancel_requested.connect(self._cancel_transfer)
        self._transfers[transfer_id] = item
        self._list_layout.addWidget(item)

        self._update_title()

        if not self._collapsed:
            self._scroll.setVisible(True)

        if direction == "upload":
            session_key = id(sftp)
            self._pending_uploads[session_key] = self._pending_uploads.get(session_key, 0) + 1

        self._active_count += 1
        self._total_count += 1
        self._update_global_progress()

        # Start the transfer task
        asyncio.ensure_future(
            self._run_transfer(transfer_id, sftp, direction, local_path, remote_path)
        )

        return transfer_id

    async def _run_transfer(
        self,
        transfer_id: str,
        sftp: SFTPSession,
        direction: str,
        local_path: str,
        remote_path: str,
    ) -> None:
        item = self._transfers.get(transfer_id)
        if not item:
            return

        session_key = id(sftp)
        if session_key not in self._session_locks:
            self._session_locks[session_key] = asyncio.Lock()

        async with self._session_locks[session_key]:
            item.set_status("Transferring")
            loop = asyncio.get_running_loop()

            def _progress(transferred: int, total: int) -> None:
                if total > 0:
                    pct = int(transferred / total * 100)
                    def _update(p=pct):
                        item.set_progress(p)
                        self._current_file_pct = p
                        self._update_global_progress()
                    loop.call_soon_threadsafe(_update)

            try:
                if direction == "download":
                    await sftp.download(remote_path, local_path, _progress)
                else:
                    await sftp.upload(local_path, remote_path, _progress)
                item.mark_complete()
                if direction == "upload":
                    session_key = id(sftp)
                    self._pending_uploads[session_key] = max(0, self._pending_uploads.get(session_key, 1) - 1)
                    if self._pending_uploads[session_key] == 0:
                        self.upload_completed.emit(sftp)
            except PermissionError:
                logger.error("Transfer %s failed: permission denied", transfer_id)
                item.mark_error("Permission denied")
                self._show_error(f"Permission denied: {local_path.split('/')[-1]}")
            except Exception as exc:
                logger.exception("Transfer %s failed", transfer_id)
                item.mark_error(str(exc)[:30])
                self._show_error(f"Transfer failed: {exc}")
            finally:
                self._active_count = max(0, self._active_count - 1)
                self._done_count += 1
                self._current_file_pct = 0
                self._update_global_progress()

        self._update_title()

    def _cancel_transfer(self, transfer_id: str) -> None:
        item = self._transfers.pop(transfer_id, None)
        if item:
            self._list_layout.removeWidget(item)
            item.deleteLater()
            self._update_title()

    def _clear_completed(self) -> None:
        for tid in list(self._transfers):
            item = self._transfers[tid]
            if item._progress.value() == 100 or "Error" in (item._status.text() or ""):
                self._list_layout.removeWidget(item)
                item.deleteLater()
                del self._transfers[tid]
        self._update_title()

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._scroll.setVisible(not self._collapsed)

    def _show_error(self, message: str) -> None:
        from termplus.ui.widgets.toast import ToastManager

        ToastManager.instance().show_toast(message, "error", duration_ms=5000)

    def _update_global_progress(self) -> None:
        if self._active_count == 0:
            self._global_progress.setVisible(False)
            self._global_pct_label.setVisible(False)
            self._total_count = 0
            self._done_count = 0
            self._current_file_pct = 0
        else:
            # Include fractional progress of current file
            effective = self._done_count + self._current_file_pct / 100
            pct = int(effective / self._total_count * 100) if self._total_count else 0
            self._global_progress.setValue(pct)
            self._global_pct_label.setText(
                f"{self._done_count}/{self._total_count}  {pct}%"
            )
            self._global_progress.setVisible(True)
            self._global_pct_label.setVisible(True)

    def _update_title(self) -> None:
        count = len(self._transfers)
        self._title.setText(f"Transfers ({count})")
