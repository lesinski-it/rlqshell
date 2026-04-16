"""Device Code Flow dialog — shows code + verification URL for OneDrive login."""

from __future__ import annotations

import logging
import webbrowser

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors

logger = logging.getLogger(__name__)


class _DeviceFlowWorker(QThread):
    """Worker thread that blocks until the user confirms in the browser."""

    completed = Signal(bool, str)  # (success, error_message)

    def __init__(self, provider, flow: dict) -> None:
        super().__init__()
        self._provider = provider
        self._flow = flow

    def run(self) -> None:
        try:
            self._provider.complete_device_flow(self._flow)
            self.completed.emit(True, "")
        except Exception as exc:
            self.completed.emit(False, str(exc))


class DeviceCodeDialog(QDialog):
    """Modal dialog for Microsoft Device Code Flow authentication.

    Shows the device code prominently, the verification URL, and an
    "Open Browser" button. Polls in a background thread until the user
    confirms (or the flow times out).
    """

    def __init__(
        self,
        provider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._worker: _DeviceFlowWorker | None = None
        self._verification_url: str = ""

        self.setWindowTitle("OneDrive Login")
        self.setFixedSize(440, 300)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")

        self._build_ui()
        self._start_flow()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self._status = QLabel("Connecting to Microsoft...")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        layout.addWidget(self._status)

        # Device code — large, centered, selectable
        self._code_label = QLabel("")
        self._code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._code_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; letter-spacing: 4px; "
            f"color: {Colors.ACCENT}; background: {Colors.BG_SURFACE}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 12px;"
        )
        layout.addWidget(self._code_label)

        # Verification URL
        self._url_label = QLabel("")
        self._url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_label.setWordWrap(True)
        self._url_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self._url_label)

        # Open Browser button
        self._browser_btn = QPushButton("Open Browser")
        self._browser_btn.setProperty("cssClass", "primary")
        self._browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browser_btn.setEnabled(False)
        self._browser_btn.clicked.connect(self._open_browser)
        layout.addWidget(self._browser_btn)

        # Waiting status
        self._waiting = QLabel("")
        self._waiting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waiting.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(self._waiting)

        layout.addStretch()

        # Cancel button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        btn_box.rejected.connect(self.reject)
        btn_box.setStyleSheet("background: transparent;")
        layout.addWidget(btn_box)

    def _start_flow(self) -> None:
        try:
            flow = self._provider.initiate_device_flow()
            code = flow["user_code"]
            url = flow["verification_uri"]
            self._verification_url = url

            self._status.setText(
                "Visit the URL below and enter this code to sign in:"
            )
            self._code_label.setText(code)
            self._url_label.setText(url)
            self._browser_btn.setEnabled(True)
            self._waiting.setText("Waiting for sign-in...")

            self._worker = _DeviceFlowWorker(self._provider, flow)
            self._worker.completed.connect(self._on_flow_complete)
            self._worker.start()

        except Exception as exc:
            self._status.setText(f"Failed to start authentication: {exc}")
            self._status.setStyleSheet(
                f"font-size: 13px; color: {Colors.DANGER}; background: transparent;"
            )

    def _open_browser(self) -> None:
        if self._verification_url:
            webbrowser.open(self._verification_url)

    def _on_flow_complete(self, success: bool, error: str) -> None:
        if success:
            self._waiting.setText("Signed in successfully!")
            self._waiting.setStyleSheet(
                f"font-size: 12px; color: {Colors.SUCCESS}; background: transparent;"
            )
            self.accept()
        else:
            self._waiting.setText(f"Sign-in failed: {error}")
            self._waiting.setStyleSheet(
                f"font-size: 12px; color: {Colors.DANGER}; background: transparent;"
            )
