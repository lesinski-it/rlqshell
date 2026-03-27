"""Host key verification dialog — first-connect fingerprint check."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from termplus.app.constants import Colors


class HostKeyDialog(QDialog):
    """Dialog shown on first SSH connection to verify the host fingerprint.

    Modes:
    - NOT_FOUND: new host, ask to trust
    - MISMATCH: key changed — MITM warning
    """

    def __init__(
        self,
        hostname: str,
        port: int,
        key_type: str,
        fingerprint: str,
        is_mismatch: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Host Key Verification")
        self.setFixedSize(500, 320 if is_mismatch else 260)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )

        self._build_ui(hostname, port, key_type, fingerprint, is_mismatch)
        self._apply_style(is_mismatch)

    def _build_ui(
        self,
        hostname: str,
        port: int,
        key_type: str,
        fingerprint: str,
        is_mismatch: bool,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        if is_mismatch:
            # MITM warning
            warning = QLabel("⚠  WARNING: HOST KEY HAS CHANGED!")
            warning.setObjectName("warning")
            layout.addWidget(warning)

            desc = QLabel(
                f"The host key for {hostname}:{port} has changed.\n"
                "This could indicate a man-in-the-middle attack.\n"
                "If you did not expect this change, do NOT connect."
            )
            desc.setObjectName("mismatchDesc")
            desc.setWordWrap(True)
            layout.addWidget(desc)
        else:
            title = QLabel("New Host Key")
            title.setObjectName("title")
            layout.addWidget(title)

            desc = QLabel(
                f"The authenticity of host '{hostname}:{port}' can't be established."
            )
            desc.setObjectName("desc")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        # Fingerprint display
        fp_label = QLabel(f"{key_type} key fingerprint:")
        fp_label.setObjectName("fpLabel")
        layout.addWidget(fp_label)

        fp_value = QLabel(fingerprint)
        fp_value.setObjectName("fpValue")
        fp_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(fp_value)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("rejectBtn")
        reject_btn.clicked.connect(self.reject)
        btn_row.addWidget(reject_btn)

        accept_btn = QPushButton("Accept & Connect" if not is_mismatch else "Connect Anyway")
        accept_btn.setObjectName("acceptBtn" if not is_mismatch else "dangerBtn")
        accept_btn.clicked.connect(self.accept)
        btn_row.addWidget(accept_btn)

        layout.addLayout(btn_row)

    def _apply_style(self, is_mismatch: bool) -> None:
        danger_bg = "#3d1c1c" if is_mismatch else Colors.BG_PRIMARY
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {danger_bg};
            }}
            QLabel#warning {{
                color: {Colors.DANGER};
                font-size: 16px;
                font-weight: 800;
            }}
            QLabel#mismatchDesc {{
                color: {Colors.WARNING};
                font-size: 12px;
            }}
            QLabel#title {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#desc {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#fpLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: 11px;
            }}
            QLabel#fpValue {{
                color: {Colors.ACCENT_LIGHT};
                font-size: 13px;
                font-family: monospace;
                background-color: {Colors.BG_SURFACE};
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QPushButton#rejectBtn {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton#rejectBtn:hover {{
                background-color: {Colors.BG_HOVER};
            }}
            QPushButton#acceptBtn {{
                background-color: {Colors.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#acceptBtn:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton#dangerBtn {{
                background-color: {Colors.DANGER};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#dangerBtn:hover {{
                background-color: #d6304a;
            }}
        """)
