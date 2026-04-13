"""Top navigation bar — Vault | Connections | SFTP | Port Forwarding."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QSequentialAnimationGroup, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from rlqshell.app.constants import ICONS_DIR, RESOURCES_DIR, Colors


class TopBar(QWidget):
    """Horizontal top navigation bar with page buttons and status area."""

    page_changed = Signal(int)
    settings_requested = Signal()
    sync_requested = Signal()

    # Page indices
    PAGE_VAULT = 0
    PAGE_CONNECTIONS = 1
    PAGE_SFTP = 2
    PAGE_PORT_FORWARD = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"background-color: {Colors.BG_DARKER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # Logo: SVG mark + wordmark
        logo_svg_path = RESOURCES_DIR / "images" / "logo.svg"
        if logo_svg_path.exists():
            logo_icon = QSvgWidget(str(logo_svg_path))
            logo_icon.setFixedSize(QSize(24, 24))
            logo_icon.setStyleSheet("background: transparent;")
            layout.addWidget(logo_icon)
            layout.addSpacing(8)

        logo_text = QLabel("RLQShell")
        logo_text.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 16px; font-weight: 800; "
            f"letter-spacing: 1px; background: transparent; padding-right: 24px;"
        )
        layout.addWidget(logo_text)

        # Navigation buttons
        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("Vault", self.PAGE_VAULT),
            ("Connections", self.PAGE_CONNECTIONS),
            ("SFTP", self.PAGE_SFTP),
            ("Tunneling", self.PAGE_PORT_FORWARD),
        ]
        for label, index in nav_items:
            btn = self._create_nav_button(label, index)
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Track counts for inline display
        self._connection_count = 0
        self._sftp_count = 0

        # Cloud sync button — visible when a cloud provider is connected
        self._cloud_btn = QPushButton()
        self._cloud_btn.setFixedSize(28, 28)
        self._cloud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cloud_btn.setToolTip("Synchronizuj teraz")
        self._cloud_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); border-radius: 4px; }"
        )
        cloud_icon_path = ICONS_DIR / "cloud_sync.svg"
        if cloud_icon_path.exists():
            self._cloud_btn.setIcon(QIcon(str(cloud_icon_path)))
            self._cloud_btn.setIconSize(QSize(20, 20))
        self._cloud_btn.clicked.connect(self.sync_requested.emit)
        self._cloud_btn.setVisible(False)

        # Fade-in / fade-out animation during sync
        self._cloud_opacity = QGraphicsOpacityEffect(self._cloud_btn)
        self._cloud_opacity.setOpacity(1.0)
        self._cloud_btn.setGraphicsEffect(self._cloud_opacity)

        _fade_out = QPropertyAnimation(self._cloud_opacity, b"opacity", self)
        _fade_out.setDuration(800)
        _fade_out.setStartValue(1.0)
        _fade_out.setEndValue(0.3)

        _fade_in = QPropertyAnimation(self._cloud_opacity, b"opacity", self)
        _fade_in.setDuration(800)
        _fade_in.setStartValue(0.3)
        _fade_in.setEndValue(1.0)

        self._cloud_anim = QSequentialAnimationGroup(self)
        self._cloud_anim.addAnimation(_fade_out)
        self._cloud_anim.addAnimation(_fade_in)
        self._cloud_anim.setLoopCount(-1)

        layout.addWidget(self._cloud_btn)
        layout.addSpacing(8)

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.setProperty("cssClass", "flat")
        settings_btn.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; "
            f"border: none; padding: 6px 12px; font-size: 12px;"
        )
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(settings_btn)

        # Set default selection
        self._current_index = 0
        self._update_button_styles()

    def _create_nav_button(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._nav_button_style(False))
        btn.clicked.connect(lambda checked=False, i=index: self._on_nav_click(i))
        return btn

    def navigate_to(self, index: int) -> None:
        """Programmatically switch to the given page index."""
        self._current_index = index
        self._update_button_styles()
        self.page_changed.emit(index)

    def _on_nav_click(self, index: int) -> None:
        if index != self._current_index:
            self.navigate_to(index)

    def _update_button_styles(self) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(self._nav_button_style(i == self._current_index))

    def set_connection_count(self, count: int) -> None:
        """Update the Connections button label with count."""
        self._connection_count = count
        btn = self._nav_buttons[self.PAGE_CONNECTIONS]
        btn.setText(f"Connections ({count})" if count > 0 else "Connections")

    def set_sftp_count(self, count: int) -> None:
        """Update the SFTP button label with count."""
        self._sftp_count = count
        btn = self._nav_buttons[self.PAGE_SFTP]
        btn.setText(f"SFTP ({count})" if count > 0 else "SFTP")

    def set_tunnel_count(self, count: int) -> None:
        """Update the Port Forwarding button label with active tunnel count."""
        btn = self._nav_buttons[self.PAGE_PORT_FORWARD]
        btn.setText(f"Tunneling ({count})" if count > 0 else "Tunneling")

    def set_vault_locked(self, locked: bool) -> None:
        """Show a lock indicator on the Vault button when the vault is locked."""
        btn = self._nav_buttons[self.PAGE_VAULT]
        if locked:
            btn.setText("\U0001f512 Vault")
            btn.setToolTip("Vault is locked \u2014 identity editing disabled")
        else:
            btn.setText("Vault")
            btn.setToolTip("")

    def set_cloud_visible(self, visible: bool) -> None:
        """Show or hide the cloud sync button."""
        self._cloud_btn.setVisible(visible)

    def set_cloud_syncing(self, syncing: bool) -> None:
        """Start or stop the cloud pulsing animation."""
        if syncing:
            self._cloud_anim.start()
        else:
            self._cloud_anim.stop()
            self._cloud_opacity.setOpacity(1.0)

    @staticmethod
    def _nav_button_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ "
                f"  background: transparent; border: none; "
                f"  color: {Colors.TEXT_PRIMARY}; font-weight: 600; "
                f"  padding: 12px 16px; font-size: 13px; "
                f"  border-bottom: 2px solid {Colors.ACCENT}; "
                f"}}"
            )
        return (
            f"QPushButton {{ "
            f"  background: transparent; border: none; "
            f"  color: {Colors.TEXT_SECONDARY}; font-weight: 500; "
            f"  padding: 12px 16px; font-size: 13px; "
            f"  border-bottom: 2px solid transparent; "
            f"}}"
            f"QPushButton:hover {{ "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"}}"
        )
