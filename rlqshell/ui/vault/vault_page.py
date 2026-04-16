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

from rlqshell.app.constants import Colors
from rlqshell.core.connection_pool import ConnectionPool
from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.host_manager import HostManager
from rlqshell.core.keychain import Keychain
from rlqshell.core.known_hosts import KnownHostsManager
from rlqshell.core.history_manager import HistoryManager
from rlqshell.core.port_forward_manager import PortForwardManager
from rlqshell.core.snippet_manager import SnippetManager
from rlqshell.ui.vault.history_view import HistoryView
from rlqshell.ui.vault.host_editor import HostEditorContent
from rlqshell.ui.vault.host_list import HostListWidget
from rlqshell.ui.vault.identities_view import IdentitiesView
from rlqshell.ui.vault.keychain_view import KeychainView
from rlqshell.ui.vault.known_hosts_view import KnownHostsView
from rlqshell.ui.vault.port_forward_view import PortForwardView
from rlqshell.ui.vault.sidebar import Sidebar
from rlqshell.ui.vault.snippet_list import SnippetListView
from rlqshell.ui.widgets.slide_panel import SlidePanel

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
    sftp_requested = Signal(int)  # host_id
    snippet_run_requested = Signal(str)  # script content
    snippet_broadcast_requested = Signal(str)  # script content

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore | None = None,
        keychain: Keychain | None = None,
        known_hosts: KnownHostsManager | None = None,
        snippet_manager: SnippetManager | None = None,
        history_manager: HistoryManager | None = None,
        pf_manager: PortForwardManager | None = None,
        connection_pool: ConnectionPool | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._known_hosts = known_hosts
        self._snippet_manager = snippet_manager
        self._history_manager = history_manager
        self._pf_manager = pf_manager
        self._vault_locked = not (credential_store is not None and credential_store.is_unlocked)

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
        self._host_list = HostListWidget(
            host_manager, connection_pool=connection_pool, vault_locked=self._vault_locked
        )
        self._host_list.host_selected.connect(self._on_host_selected)
        self._host_list.host_connect_requested.connect(self._on_host_connect)
        self._host_list.sftp_requested.connect(self._on_sftp_requested)
        self._content_stack.addWidget(self._host_list)

        # Snippets
        if snippet_manager is not None:
            self._snippets_section: QWidget = SnippetListView(
                snippet_manager, vault_locked=self._vault_locked
            )
            self._snippets_section.snippet_run_requested.connect(
                self.snippet_run_requested.emit
            )
            self._snippets_section.snippet_broadcast_requested.connect(
                self.snippet_broadcast_requested.emit
            )
        else:
            self._snippets_section = _PlaceholderSection("Snippets")
        self._content_stack.addWidget(self._snippets_section)

        # Keychain view (real widget if keychain provided)
        if keychain is not None:
            self._keychain_section: QWidget = KeychainView(
                keychain, vault_locked=self._vault_locked
            )
        else:
            self._keychain_section = _PlaceholderSection("Keychain")
        self._content_stack.addWidget(self._keychain_section)

        # Identities view
        if credential_store is not None and keychain is not None:
            self._identities_section: QWidget = IdentitiesView(
                credential_store, keychain
            )
        else:
            self._identities_section = _PlaceholderSection("Identities")
        self._content_stack.addWidget(self._identities_section)

        # Trusted Hosts view
        if known_hosts is not None:
            self._known_hosts_section: QWidget = KnownHostsView(
                known_hosts, vault_locked=self._vault_locked
            )
        else:
            self._known_hosts_section = _PlaceholderSection("Trusted Hosts")

        if pf_manager is not None:
            self._port_fwd_section: QWidget = PortForwardView(
                pf_manager, host_manager, vault_locked=self._vault_locked
            )
        else:
            self._port_fwd_section = _PlaceholderSection("Port Forwarding")

        if history_manager is not None:
            self._history_section: QWidget = HistoryView(
                history_manager, vault_locked=self._vault_locked
            )
        else:
            self._history_section = _PlaceholderSection("History")

        self._content_stack.addWidget(self._known_hosts_section)
        self._content_stack.addWidget(self._port_fwd_section)
        self._content_stack.addWidget(self._history_section)

        self._section_map = {
            "hosts": 0,
            "snippets": 1,
            "keychain": 2,
            "identities": 3,
            "known_hosts": 4,
            "port_forward": 5,
            "history": 6,
        }

        # Host editor (slide-in panel — added to layout so it appears on the right)
        self._editor_panel = SlidePanel(self, width=420)
        self._editor_content = HostEditorContent(
            host_manager, credential_store=credential_store, keychain=keychain,
        )
        self._editor_content.host_saved.connect(self._host_list.refresh)
        self._editor_content.host_deleted.connect(self._on_host_deleted)
        self._editor_content.connect_requested.connect(self._on_host_connect)
        self._editor_content.identity_created.connect(self._refresh_identities)
        self._editor_panel.set_content(self._editor_content)
        layout.addWidget(self._editor_panel)

    def _on_section_changed(self, section: str) -> None:
        idx = self._section_map.get(section, 0)
        self._content_stack.setCurrentIndex(idx)
        # Close editor if switching sections
        if self._editor_panel.is_open:
            self._editor_panel.close()
        # Refresh history when switching to that section
        if section == "history" and isinstance(self._history_section, HistoryView):
            self._history_section.refresh()
        # Refresh identities so inline-created entries appear without restart
        if section == "identities" and isinstance(self._identities_section, IdentitiesView):
            self._identities_section.refresh()

    def _refresh_identities(self) -> None:
        """Refresh the IdentitiesView (e.g. after inline identity create from host editor)."""
        if isinstance(self._identities_section, IdentitiesView):
            self._identities_section.refresh()

    def _on_host_selected(self, host_id: int) -> None:
        if self._vault_locked:
            return
        self._editor_content.load_host(host_id)
        if not self._editor_panel.is_open:
            self._editor_panel.open()

    def _on_host_connect(self, host_id: int) -> None:
        self.connect_requested.emit(host_id)

    def _on_sftp_requested(self, host_id: int) -> None:
        self.sftp_requested.emit(host_id)

    def _on_host_deleted(self) -> None:
        self._editor_panel.close()
        self._host_list.refresh()

    def go_to_section(self, section: str) -> None:
        """Programmatically switch to a vault section."""
        # This will also trigger _on_section_changed via the signal
        self._sidebar.select_section(section)

