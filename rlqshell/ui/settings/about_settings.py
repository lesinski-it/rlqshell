"""About panel — information about the application, author, and support links."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import (
    APP_AUTHOR,
    APP_AUTHOR_WEBSITE,
    APP_DONATE_URL,
    APP_LICENSES_URL,
    APP_NAME,
    APP_PRIVACY_URL,
    APP_VERSION,
    RESOURCES_DIR,
    Colors,
)


class _LinkLabel(QLabel):
    """Clickable label that opens a URL in the system browser on click."""

    def __init__(self, text: str, url: str, parent=None) -> None:
        super().__init__(text, parent)
        self._url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"color: {Colors.ACCENT}; background: transparent; font-size: 13px;"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            webbrowser.open(self._url)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.setStyleSheet(
            f"color: {Colors.ACCENT_HOVER}; background: transparent; "
            f"font-size: 13px; text-decoration: underline;"
        )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.setStyleSheet(
            f"color: {Colors.ACCENT}; background: transparent; font-size: 13px;"
        )
        super().leaveEvent(event)


class AboutSettings(QWidget):
    """About panel — version, author, support, and legal links."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # --- Page title ---
        title = QLabel("About")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # --- Logo + app name/version row ---
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        logo_label = QLabel()
        logo_path = RESOURCES_DIR / "images" / "logo.svg"
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            pixmap = pixmap.scaledToHeight(
                64,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_label.setPixmap(pixmap)
        logo_label.setStyleSheet("background: transparent;")
        header_row.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignTop)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        app_name_label = QLabel(APP_NAME)
        app_name_label.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        name_col.addWidget(app_name_label)

        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        name_col.addWidget(version_label)

        header_row.addLayout(name_col, 1)
        layout.addLayout(header_row)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        separator.setStyleSheet(
            f"background-color: {Colors.BORDER}; border: none; max-height: 1px;"
        )
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # --- Author section ---
        author_label = QLabel(f"Created with passion by {APP_AUTHOR}.")
        author_label.setWordWrap(True)
        author_label.setStyleSheet(
            f"font-size: 14px; color: {Colors.TEXT_PRIMARY}; background: transparent;"
        )
        layout.addWidget(author_label)

        website_link = _LinkLabel("www.lesinski.it", APP_AUTHOR_WEBSITE)
        layout.addWidget(website_link)

        # --- Support section ---
        support_title = QLabel("Support")
        support_title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; margin-top: 8px;"
        )
        layout.addWidget(support_title)

        support_desc = QLabel(
            "If my work has made your life easier, you can support the project:"
        )
        support_desc.setWordWrap(True)
        support_desc.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(support_desc)

        donate_btn = QPushButton("Support the project ♥")
        donate_btn.setProperty("cssClass", "primary")
        donate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        donate_btn.setFixedWidth(220)
        donate_btn.clicked.connect(lambda: webbrowser.open(APP_DONATE_URL))
        layout.addWidget(donate_btn)

        layout.addStretch()

        # --- Built with: subtle credits for core libraries ---
        built_with_label = QLabel(
            "Built with PySide6 · paramiko · pyte · cryptography · "
            "qasync · keyring · aiohttp"
        )
        built_with_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        built_with_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(built_with_label)

        # --- Footer: privacy + licenses links ---
        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)
        footer_row.addStretch()

        privacy_link = _LinkLabel("Privacy Policy", APP_PRIVACY_URL)
        footer_row.addWidget(privacy_link)

        sep_label = QLabel("|")
        sep_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; background: transparent; font-size: 13px;"
        )
        footer_row.addWidget(sep_label)

        licenses_link = _LinkLabel("Open Source Licenses", APP_LICENSES_URL)
        footer_row.addWidget(licenses_link)

        footer_row.addStretch()
        layout.addLayout(footer_row)
