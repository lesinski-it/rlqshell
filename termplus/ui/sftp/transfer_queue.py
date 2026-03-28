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

# Max concurrent transfers
_MAX_CONCURRENT = 3


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
        cancel_btn = QPushButton("✕")
        cancel_btn.setFixedSize(20, 20)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ font-size: 11px; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {Colors.DANGER}; color: white; }}"
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = True
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

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

        async with self._semaphore:
            item.set_status("Transferring")
            try:
                if direction == "download":
                    await sftp.download(remote_path, local_path)
                else:
                    await sftp.upload(local_path, remote_path)
                item.mark_complete()
            except PermissionError:
                logger.error("Transfer %s failed: permission denied", transfer_id)
                item.mark_error("Permission denied")
                self._show_error(f"Permission denied: {local_path.split('/')[-1]}")
            except Exception as exc:
                logger.exception("Transfer %s failed", transfer_id)
                item.mark_error(str(exc)[:30])
                self._show_error(f"Transfer failed: {exc}")

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

    def _update_title(self) -> None:
        count = len(self._transfers)
        self._title.setText(f"Transfers ({count})")
