"""Vault page — sidebar + host list + host editor."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.known_hosts import KnownHostsManager
from termplus.ui.vault.host_editor import HostEditorContent
from termplus.ui.vault.host_list import HostListWidget
from termplus.ui.vault.keychain_view import KeychainView
from termplus.ui.vault.known_hosts_view import KnownHostsView
from termplus.ui.vault.sidebar import Sidebar
from termplus.ui.widgets.slide_panel import SlidePanel

logger = logging.getLogger(__name__)


class _PlaceholderSection(QWidget):
    """Placeholder for sections not yet implemented."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(f"{name} — coming soon")
        label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 16px; background: transparent;"
        )
        label.setAlignment(label.alignment())
        layout.addWidget(label)


class VaultPage(QWidget):
    """Main vault page: sidebar + content area + slide-in host editor."""

    connect_requested = Signal(int)  # host_id

    def __init__(
        self,
        host_manager: HostManager,
        keychain: Keychain | None = None,
        known_hosts: KnownHostsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._keychain = keychain
        self._known_hosts = known_hosts

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.section_changed.connect(self._on_section_changed)
        layout.addWidget(self._sidebar)

        # Content area (stacked widget for different sections)
        self._content_stack = QStackedWidget()
        layout.addWidget(self._content_stack, 1)

        # Host list (default section)
        self._host_list = HostListWidget(host_manager)
        self._host_list.host_selected.connect(self._on_host_selected)
        self._host_list.host_connect_requested.connect(self._on_host_connect)
        self._content_stack.addWidget(self._host_list)

        # Snippets placeholder
        self._snippets_section = _PlaceholderSection("Snippets")
        self._content_stack.addWidget(self._snippets_section)

        # Keychain view (real widget if keychain provided)
        if keychain is not None:
            self._keychain_section: QWidget = KeychainView(keychain)
        else:
            self._keychain_section = _PlaceholderSection("Keychain")
        self._content_stack.addWidget(self._keychain_section)

        # Known Hosts view
        if known_hosts is not None:
            self._known_hosts_section: QWidget = KnownHostsView(known_hosts)
        else:
            self._known_hosts_section = _PlaceholderSection("Known Hosts")

        self._port_fwd_section = _PlaceholderSection("Port Forwarding")
        self._history_section = _PlaceholderSection("History")

        self._content_stack.addWidget(self._known_hosts_section)
        self._content_stack.addWidget(self._port_fwd_section)
        self._content_stack.addWidget(self._history_section)

        self._section_map = {
            "hosts": 0,
            "snippets": 1,
            "keychain": 2,
            "known_hosts": 3,
            "port_forward": 4,
            "history": 5,
        }

        # Host editor (slide-in panel)
        self._editor_panel = SlidePanel(self, width=420)
        self._editor_content = HostEditorContent(host_manager)
        self._editor_content.host_saved.connect(self._host_list.refresh)
        self._editor_content.host_deleted.connect(self._on_host_deleted)
        self._editor_content.connect_requested.connect(self._on_host_connect)
        self._editor_panel.set_content(self._editor_content)

    def _on_section_changed(self, section: str) -> None:
        idx = self._section_map.get(section, 0)
        self._content_stack.setCurrentIndex(idx)
        # Close editor if switching sections
        if self._editor_panel.is_open:
            self._editor_panel.close()

    def _on_host_selected(self, host_id: int) -> None:
        self._editor_content.load_host(host_id)
        if not self._editor_panel.is_open:
            self._editor_panel.open()

    def _on_host_connect(self, host_id: int) -> None:
        self.connect_requested.emit(host_id)

    def _on_host_deleted(self) -> None:
        self._editor_panel.close()
        self._host_list.refresh()

    def resizeEvent(self, event) -> None:
        """Keep the slide panel anchored to the right edge."""
        super().resizeEvent(event)
        self._editor_panel.setFixedHeight(self.height())
        self._editor_panel.move(
            self.width() - self._editor_panel.width(), 0
        )
