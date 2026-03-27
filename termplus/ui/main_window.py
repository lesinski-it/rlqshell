"""Main application window with TopBar navigation and page stack."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import APP_NAME, APP_VERSION, Colors
from termplus.ui.top_bar import TopBar

logger = logging.getLogger(__name__)


class _PlaceholderPage(QWidget):
    """Temporary placeholder page until real pages are built."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 16px;")
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """Termplus main window — TopBar + QStackedWidget for pages."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(QSize(1024, 700))
        self.resize(1280, 800)

        # Central widget
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top navigation bar
        self._top_bar = TopBar()
        self._top_bar.page_changed.connect(self._on_page_changed)
        self._top_bar.settings_requested.connect(self._on_settings_requested)
        main_layout.addWidget(self._top_bar)

        # Page stack
        self._stack = QStackedWidget()
        self._vault_page = _PlaceholderPage("Vault — coming in Stage 4")
        self._connections_page = _PlaceholderPage("Connections — coming in Stage 6")
        self._sftp_page = _PlaceholderPage("SFTP — coming in Stage 7")
        self._pf_page = _PlaceholderPage("Port Forwarding — coming in Stage 8")

        self._stack.addWidget(self._vault_page)
        self._stack.addWidget(self._connections_page)
        self._stack.addWidget(self._sftp_page)
        self._stack.addWidget(self._pf_page)

        main_layout.addWidget(self._stack)
        self.setCentralWidget(central)

        logger.info("MainWindow created with TopBar navigation")

    @property
    def top_bar(self) -> TopBar:
        return self._top_bar

    @property
    def stack(self) -> QStackedWidget:
        return self._stack

    def set_vault_page(self, page: QWidget) -> None:
        """Replace the placeholder vault page with the real one."""
        self._stack.removeWidget(self._vault_page)
        self._vault_page.deleteLater()
        self._vault_page = page
        self._stack.insertWidget(TopBar.PAGE_VAULT, page)

    def set_connections_page(self, page: QWidget) -> None:
        """Replace the placeholder connections page."""
        self._stack.removeWidget(self._connections_page)
        self._connections_page.deleteLater()
        self._connections_page = page
        self._stack.insertWidget(TopBar.PAGE_CONNECTIONS, page)

    def set_sftp_page(self, page: QWidget) -> None:
        """Replace the placeholder SFTP page."""
        self._stack.removeWidget(self._sftp_page)
        self._sftp_page.deleteLater()
        self._sftp_page = page
        self._stack.insertWidget(TopBar.PAGE_SFTP, page)

    def _on_page_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        logger.debug("Switched to page %d", index)

    def _on_settings_requested(self) -> None:
        logger.info("Settings requested — dialog coming in Stage 8")

    def set_cleanup_callback(self, callback) -> None:
        """Register a callback to run on window close for resource cleanup."""
        self._cleanup_callback = callback

    def closeEvent(self, event) -> None:
        """Handle window close — run cleanup callback if set."""
        logger.info("MainWindow closing")
        if hasattr(self, "_cleanup_callback") and self._cleanup_callback:
            try:
                self._cleanup_callback()
            except Exception:
                logger.exception("Error during cleanup")
        event.accept()
