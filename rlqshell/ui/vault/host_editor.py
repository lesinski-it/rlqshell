"""Host editor slide-in panel with auto-save."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.core.credential_store import CredentialStore
from rlqshell.core.host_manager import HostManager
from rlqshell.core.keychain import Keychain
from rlqshell.core.models.host import Host, Tag
from rlqshell.ui.widgets.scroll_guard import install_scroll_guard
from rlqshell.ui.widgets.tag_widget import TagSelector

logger = logging.getLogger(__name__)


class HostEditorContent(QWidget):
    """Scrollable form content for editing a host."""

    host_saved = Signal()
    host_deleted = Signal()
    connect_requested = Signal(int)  # host_id
    identity_created = Signal()  # emitted after a new identity is added inline

    def __init__(
        self,
        host_manager: HostManager,
        credential_store: CredentialStore | None = None,
        keychain: Keychain | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._credential_store = credential_store
        self._keychain = keychain
        self._host: Host | None = None
        self._auto_save_timer = QTimer()
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(1000)
        self._auto_save_timer.timeout.connect(self._do_save)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        form = QWidget()
        self._form_layout = QVBoxLayout(form)
        self._form_layout.setContentsMargins(20, 16, 20, 16)
        self._form_layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Edit Host")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._save_indicator = QLabel("")
        self._save_indicator.setStyleSheet(
            f"color: {Colors.SUCCESS}; font-size: 11px; background: transparent;"
        )
        header_row.addWidget(self._save_indicator)
        self._form_layout.addLayout(header_row)

        # Label
        _, self._label_edit = self._add_field("Label", QLineEdit())
        self._label_edit.setPlaceholderText("e.g. web-server-1")

        # Address
        _, self._address_edit = self._add_field("Address", QLineEdit())
        self._address_edit.setPlaceholderText("IP or hostname")

        # Protocol
        self._protocol_combo = QComboBox()
        self._protocol_combo.addItems(["ssh", "rdp", "vnc", "telnet", "serial"])
        self._add_field("Protocol", self._protocol_combo)
        self._protocol_combo.currentTextChanged.connect(self._on_protocol_changed)

        # Port (default value depends on protocol)
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        self._add_field("Port", self._port_spin)

        # Default ports per protocol
        self._default_ports = {
            "ssh": 22, "rdp": 3389, "vnc": 5900, "telnet": 23, "serial": 0,
        }

        # Identity
        self._identity_combo = QComboBox()
        self._populate_identities()
        self._identity_combo.currentIndexChanged.connect(self._on_identity_changed)
        self._add_field("Identity", self._identity_combo)

        # Group
        self._group_combo = QComboBox()
        self._group_combo.addItem("No group", None)
        self._add_field("Group", self._group_combo)

        # Tags
        tags_label = QLabel("Tags")
        tags_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent; margin-bottom: 2px;"
        )
        self._form_layout.addWidget(tags_label)

        self._tag_selector = TagSelector()
        self._tag_selector.tags_changed.connect(self._on_tags_changed)
        self._tag_selector._add_btn.clicked.connect(self._on_add_tag)
        self._form_layout.addWidget(self._tag_selector)

        # SSH options section
        self._ssh_header = QLabel("SSH Options")
        self._ssh_header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; padding-top: 8px;"
        )
        self._form_layout.addWidget(self._ssh_header)

        # Keep Alive
        self._keep_alive_spin = QSpinBox()
        self._keep_alive_spin.setRange(0, 3600)
        self._keep_alive_spin.setValue(60)
        self._keep_alive_spin.setSuffix(" sec")
        self._keep_alive_lbl, _ = self._add_field("Keep Alive", self._keep_alive_spin)

        # Agent Forwarding
        self._agent_fwd_check = QCheckBox("Enable SSH Agent Forwarding")
        self._form_layout.addWidget(self._agent_fwd_check)

        # Compression
        self._compression_check = QCheckBox("Enable Compression")
        self._form_layout.addWidget(self._compression_check)

        # Collect SSH widgets for visibility toggling
        self._ssh_widgets: list[QWidget] = [
            self._ssh_header, self._keep_alive_lbl, self._keep_alive_spin,
            self._agent_fwd_check, self._compression_check,
        ]

        # RDP options section
        self._rdp_header = QLabel("RDP Options")
        self._rdp_header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; padding-top: 8px;"
        )
        self._form_layout.addWidget(self._rdp_header)

        # RDP Username
        self._rdp_username_edit = QLineEdit()
        self._rdp_username_edit.setPlaceholderText("RDP username (or use Identity)")
        self._rdp_username_lbl, _ = self._add_field("RDP Username", self._rdp_username_edit)

        # RDP Domain
        self._rdp_domain_edit = QLineEdit()
        self._rdp_domain_edit.setPlaceholderText("e.g. CORP")
        self._rdp_domain_lbl, _ = self._add_field("Domain", self._rdp_domain_edit)

        # Resolution
        self._rdp_resolution_combo = QComboBox()
        self._rdp_resolution_combo.addItems([
            "1920x1080", "1680x1050", "1440x900", "1366x768",
            "1280x1024", "1280x720", "1024x768", "dynamic",
        ])
        self._rdp_resolution_lbl, _ = self._add_field("Resolution", self._rdp_resolution_combo)

        # Color depth
        self._rdp_color_depth_combo = QComboBox()
        self._rdp_color_depth_combo.addItems(["32", "24", "16", "15"])
        self._rdp_color_depth_lbl, _ = self._add_field("Color Depth", self._rdp_color_depth_combo)

        # Audio
        self._rdp_audio_check = QCheckBox("Enable Audio Redirection")
        self._form_layout.addWidget(self._rdp_audio_check)

        # Clipboard
        self._rdp_clipboard_check = QCheckBox("Enable Clipboard Sharing")
        self._rdp_clipboard_check.setChecked(True)
        self._form_layout.addWidget(self._rdp_clipboard_check)

        # Local resources (RDPDR via FreeRDP)
        self._rdp_resources_header = QLabel("Local Resources")
        self._rdp_resources_header.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; padding-top: 8px;"
        )
        self._form_layout.addWidget(self._rdp_resources_header)

        self._rdp_smartcard_check = QCheckBox("Smart cards (e.g. electronic signature)")
        self._form_layout.addWidget(self._rdp_smartcard_check)

        self._rdp_drives_check = QCheckBox("Local drives / folders")
        self._form_layout.addWidget(self._rdp_drives_check)

        self._rdp_drive_mapping_edit = QLineEdit()
        self._rdp_drive_mapping_edit.setPlaceholderText(
            r"Paths separated by ;  e.g. C:\;D:\Projects   (empty = home folder)",
        )
        self._rdp_drive_mapping_lbl, _ = self._add_field(
            "Drive paths", self._rdp_drive_mapping_edit,
        )

        self._rdp_printers_check = QCheckBox("Local printers")
        self._form_layout.addWidget(self._rdp_printers_check)

        # Drive paths field is only meaningful when drive redirection is enabled
        self._rdp_drives_check.toggled.connect(self._rdp_drive_mapping_edit.setEnabled)
        self._rdp_drives_check.toggled.connect(self._rdp_drive_mapping_lbl.setEnabled)
        self._rdp_drive_mapping_edit.setEnabled(False)
        self._rdp_drive_mapping_lbl.setEnabled(False)

        # Collect RDP widgets for visibility toggling
        self._rdp_widgets: list[QWidget] = [
            self._rdp_header,
            self._rdp_username_lbl, self._rdp_username_edit,
            self._rdp_domain_lbl, self._rdp_domain_edit,
            self._rdp_resolution_lbl, self._rdp_resolution_combo,
            self._rdp_color_depth_lbl, self._rdp_color_depth_combo,
            self._rdp_audio_check, self._rdp_clipboard_check,
            self._rdp_resources_header,
            self._rdp_smartcard_check,
            self._rdp_drives_check,
            self._rdp_drive_mapping_lbl, self._rdp_drive_mapping_edit,
            self._rdp_printers_check,
        ]

        # VNC options section
        self._vnc_header = QLabel("VNC Options")
        self._vnc_header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; padding-top: 8px;"
        )
        self._form_layout.addWidget(self._vnc_header)

        self._vnc_clipboard_check = QCheckBox("Enable Clipboard Sharing")
        self._vnc_clipboard_check.setChecked(True)
        self._form_layout.addWidget(self._vnc_clipboard_check)

        self._vnc_widgets: list[QWidget] = [
            self._vnc_header,
            self._vnc_clipboard_check,
        ]

        # Notes
        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.setPlaceholderText("Optional notes…")
        self._add_field("Notes", self._notes_edit)

        # Color label
        self._color_row = QHBoxLayout()
        color_label = QLabel("Color")
        color_label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._color_row.addWidget(color_label)
        self._color_options = ["#e94560", "#22c55e", "#3b82f6", "#f59e0b", "#7c3aed", "#ec4899"]
        self._color_buttons: list[QPushButton] = []
        for color in self._color_options:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("color_value", color)
            btn.clicked.connect(lambda checked=False, c=color: self._set_color(c))
            self._color_buttons.append(btn)
            self._color_row.addWidget(btn)
        self._color_row.addStretch()
        self._update_color_buttons(None)
        self._form_layout.addLayout(self._color_row)

        self._form_layout.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        connect_btn = QPushButton("Connect")
        connect_btn.setProperty("cssClass", "primary")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(connect_btn)

        btn_row.addStretch()

        delete_btn = QPushButton("Delete")
        delete_btn.setProperty("cssClass", "danger")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(delete_btn)
        self._form_layout.addLayout(btn_row)

        install_scroll_guard(
            self._protocol_combo,
            self._port_spin,
            self._identity_combo,
            self._group_combo,
            self._keep_alive_spin,
            self._rdp_resolution_combo,
            self._rdp_color_depth_combo,
        )

        scroll.setWidget(form)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Connect signals for auto-save
        self._label_edit.textChanged.connect(self._schedule_save)
        self._address_edit.textChanged.connect(self._schedule_save)
        self._protocol_combo.currentIndexChanged.connect(self._schedule_save)
        self._port_spin.valueChanged.connect(self._schedule_save)
        self._keep_alive_spin.valueChanged.connect(self._schedule_save)
        self._agent_fwd_check.stateChanged.connect(self._schedule_save)
        self._compression_check.stateChanged.connect(self._schedule_save)
        self._notes_edit.textChanged.connect(self._schedule_save)
        self._group_combo.currentIndexChanged.connect(self._schedule_save)
        self._rdp_username_edit.textChanged.connect(self._schedule_save)
        self._rdp_domain_edit.textChanged.connect(self._schedule_save)
        self._rdp_resolution_combo.currentIndexChanged.connect(self._schedule_save)
        self._rdp_color_depth_combo.currentIndexChanged.connect(self._schedule_save)
        self._rdp_audio_check.stateChanged.connect(self._schedule_save)
        self._rdp_clipboard_check.stateChanged.connect(self._schedule_save)
        self._rdp_smartcard_check.stateChanged.connect(self._schedule_save)
        self._rdp_drives_check.stateChanged.connect(self._schedule_save)
        self._rdp_drive_mapping_edit.textChanged.connect(self._schedule_save)
        self._rdp_printers_check.stateChanged.connect(self._schedule_save)
        self._vnc_clipboard_check.stateChanged.connect(self._schedule_save)

        # Show correct protocol section initially
        self._update_protocol_sections("ssh")

    def load_host(self, host_id: int) -> None:
        """Load a host into the editor."""
        host = self._host_manager.get_host(host_id)
        if host is None:
            return
        self._host = host

        # Block signals during load
        for w in [self._label_edit, self._address_edit, self._port_spin,
                   self._keep_alive_spin, self._notes_edit,
                   self._rdp_username_edit, self._rdp_domain_edit,
                   self._rdp_drive_mapping_edit]:
            w.blockSignals(True)
        for w in [self._protocol_combo, self._group_combo,
                  self._rdp_resolution_combo, self._rdp_color_depth_combo]:
            w.blockSignals(True)
        self._agent_fwd_check.blockSignals(True)
        self._compression_check.blockSignals(True)
        self._rdp_audio_check.blockSignals(True)
        self._rdp_clipboard_check.blockSignals(True)
        self._rdp_smartcard_check.blockSignals(True)
        self._rdp_drives_check.blockSignals(True)
        self._rdp_printers_check.blockSignals(True)
        self._vnc_clipboard_check.blockSignals(True)

        self._label_edit.setText(host.label)
        self._address_edit.setText(host.address)
        self._protocol_combo.setCurrentText(host.protocol)
        self._port_spin.setValue(self._get_port_for_protocol(host))
        self._keep_alive_spin.setValue(host.ssh_keep_alive)
        self._agent_fwd_check.setChecked(host.ssh_agent_forwarding)
        self._compression_check.setChecked(host.ssh_compression)
        self._notes_edit.setPlainText(host.notes or "")

        # RDP fields
        self._rdp_username_edit.setText(host.rdp_username or "")
        self._rdp_domain_edit.setText(host.rdp_domain or "")
        idx = self._rdp_resolution_combo.findText(host.rdp_resolution)
        if idx >= 0:
            self._rdp_resolution_combo.setCurrentIndex(idx)
        idx = self._rdp_color_depth_combo.findText(str(host.rdp_color_depth))
        if idx >= 0:
            self._rdp_color_depth_combo.setCurrentIndex(idx)
        self._rdp_audio_check.setChecked(host.rdp_audio)
        self._rdp_clipboard_check.setChecked(host.rdp_clipboard)
        self._rdp_smartcard_check.setChecked(host.rdp_smartcard)
        self._rdp_drives_check.setChecked(host.rdp_drives_enabled)
        self._rdp_drive_mapping_edit.setText(host.rdp_drive_mapping or "")
        self._rdp_drive_mapping_edit.setEnabled(host.rdp_drives_enabled)
        self._rdp_drive_mapping_lbl.setEnabled(host.rdp_drives_enabled)
        self._rdp_printers_check.setChecked(host.rdp_printers)
        self._vnc_clipboard_check.setChecked(host.vnc_clipboard)

        # Load identities
        self._identity_combo.blockSignals(True)
        self._populate_identities()
        if host.ssh_identity_id:
            idx = self._identity_combo.findData(host.ssh_identity_id)
            if idx >= 0:
                self._identity_combo.setCurrentIndex(idx)
        self._identity_combo.blockSignals(False)

        # Load groups
        self._group_combo.clear()
        self._group_combo.addItem("No group", None)
        for group in self._host_manager.list_groups():
            self._group_combo.addItem(group.name, group.id)
        if host.group_id:
            idx = self._group_combo.findData(host.group_id)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)

        # Unblock
        for w in [self._label_edit, self._address_edit, self._port_spin,
                   self._keep_alive_spin, self._notes_edit,
                   self._rdp_username_edit, self._rdp_domain_edit,
                   self._rdp_drive_mapping_edit]:
            w.blockSignals(False)
        for w in [self._protocol_combo, self._group_combo,
                  self._rdp_resolution_combo, self._rdp_color_depth_combo]:
            w.blockSignals(False)
        self._agent_fwd_check.blockSignals(False)
        self._compression_check.blockSignals(False)
        self._rdp_audio_check.blockSignals(False)
        self._rdp_clipboard_check.blockSignals(False)
        self._rdp_smartcard_check.blockSignals(False)
        self._rdp_drives_check.blockSignals(False)
        self._rdp_printers_check.blockSignals(False)
        self._vnc_clipboard_check.blockSignals(False)

        # Load tags
        self._tag_selector.set_tags([
            {"id": t.id, "name": t.name, "color": t.color}
            for t in host.tags
        ])

        self._update_protocol_sections(host.protocol)
        self._update_color_buttons(host.color_label)
        self._save_indicator.setText("")

    def _populate_identities(self) -> None:
        """Fill the identity dropdown from CredentialStore."""
        self._identity_combo.clear()
        self._identity_combo.addItem("— None —", None)
        if self._credential_store:
            for ident in self._credential_store.list_identities():
                display = f"{ident.label} ({ident.username})"
                self._identity_combo.addItem(display, ident.id)
        if self._credential_store.is_unlocked:
            self._identity_combo.addItem("+ Create new…", "__new__")

    def _on_identity_changed(self) -> None:
        data = self._identity_combo.currentData()
        if data == "__new__":
            self._open_identity_editor()
        elif self._host is not None:
            self._host.ssh_identity_id = data
            self._schedule_save()

    def _open_identity_editor(self) -> None:
        if not self._credential_store or not self._keychain:
            self._identity_combo.setCurrentIndex(0)
            return
        if not self._credential_store.is_unlocked:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Vault Locked",
                "The vault is locked. Enter the master password at startup\n"
                "to create identities.",
            )
            self._identity_combo.setCurrentIndex(0)
            return
        from rlqshell.ui.vault.identity_editor import IdentityEditor
        editor = IdentityEditor(self._credential_store, self._keychain, self)
        if editor.exec() == IdentityEditor.DialogCode.Accepted:
            self._populate_identities()
            # Select the newly created identity (last before "+ Create new…")
            self._identity_combo.setCurrentIndex(self._identity_combo.count() - 2)
            self.identity_created.emit()
        else:
            self._identity_combo.setCurrentIndex(0)

    def _add_field(self, label: str, widget: QWidget) -> tuple[QLabel, QWidget]:
        """Add a labeled form field.  Returns ``(label_widget, field_widget)``."""
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent; margin-bottom: 2px;"
        )
        self._form_layout.addWidget(lbl)
        self._form_layout.addWidget(widget)
        return lbl, widget

    def _schedule_save(self) -> None:
        self._auto_save_timer.start()
        self._save_indicator.setText("Saving…")
        self._save_indicator.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent;"
        )

    def _do_save(self) -> None:
        if self._host is None:
            return
        self._host.label = self._label_edit.text()
        self._host.address = self._address_edit.text()
        self._host.protocol = self._protocol_combo.currentText()
        self._set_port_for_protocol(self._host, self._port_spin.value())
        self._host.ssh_keep_alive = self._keep_alive_spin.value()
        self._host.ssh_agent_forwarding = self._agent_fwd_check.isChecked()
        self._host.ssh_compression = self._compression_check.isChecked()
        self._host.rdp_username = self._rdp_username_edit.text() or None
        self._host.rdp_domain = self._rdp_domain_edit.text() or None
        self._host.rdp_resolution = self._rdp_resolution_combo.currentText()
        self._host.rdp_color_depth = int(self._rdp_color_depth_combo.currentText())
        self._host.rdp_audio = self._rdp_audio_check.isChecked()
        self._host.rdp_clipboard = self._rdp_clipboard_check.isChecked()
        self._host.rdp_smartcard = self._rdp_smartcard_check.isChecked()
        self._host.rdp_drives_enabled = self._rdp_drives_check.isChecked()
        self._host.rdp_drive_mapping = self._rdp_drive_mapping_edit.text() or None
        self._host.rdp_printers = self._rdp_printers_check.isChecked()
        self._host.vnc_clipboard = self._vnc_clipboard_check.isChecked()
        self._host.notes = self._notes_edit.toPlainText() or None
        self._host.group_id = self._group_combo.currentData()
        identity_data = self._identity_combo.currentData()
        self._host.ssh_identity_id = identity_data if identity_data != "__new__" else None

        self._host_manager.update_host(self._host)
        self._save_indicator.setText("Saved")
        self._save_indicator.setStyleSheet(
            f"color: {Colors.SUCCESS}; font-size: 11px; background: transparent;"
        )
        self.host_saved.emit()
        logger.debug("Auto-saved host %d: %s", self._host.id, self._host.label)

    def _set_color(self, color: str) -> None:
        if self._host:
            self._host.color_label = color
            self._update_color_buttons(color)
            self._schedule_save()

    def _update_color_buttons(self, active_color: str | None = None) -> None:
        for btn in self._color_buttons:
            c = btn.property("color_value")
            if c == active_color:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {c}; "
                    f"border: 3px solid {Colors.TEXT_PRIMARY}; border-radius: 12px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {c}; "
                    f"border: 2px solid transparent; border-radius: 12px; }}"
                    f"QPushButton:hover {{ border-color: {Colors.TEXT_PRIMARY}; }}"
                )

    def _update_protocol_sections(self, protocol: str) -> None:
        """Show/hide protocol-specific option sections."""
        for w in self._ssh_widgets:
            w.setVisible(protocol == "ssh")
        for w in self._rdp_widgets:
            w.setVisible(protocol == "rdp")
        for w in self._vnc_widgets:
            w.setVisible(protocol == "vnc")

    def _on_protocol_changed(self, protocol: str) -> None:
        """Update the port default and visible sections when protocol changes."""
        self._update_protocol_sections(protocol)
        if self._host is not None:
            current_port = self._get_port_for_protocol(self._host)
            # If port is still at old default, switch to new protocol's default
            old_protocol_default = self._default_ports.get(self._host.protocol, 22)
            if current_port == old_protocol_default:
                new_default = self._default_ports.get(protocol, 22)
                self._port_spin.blockSignals(True)
                self._port_spin.setValue(new_default)
                self._port_spin.blockSignals(False)

    @staticmethod
    def _get_port_for_protocol(host: Host) -> int:
        proto = host.protocol
        if proto == "vnc":
            return host.vnc_port
        if proto == "rdp":
            return host.rdp_port
        if proto == "telnet":
            return host.telnet_port
        return host.ssh_port

    @staticmethod
    def _set_port_for_protocol(host: Host, port: int) -> None:
        proto = host.protocol
        if proto == "vnc":
            host.vnc_port = port
        elif proto == "rdp":
            host.rdp_port = port
        elif proto == "telnet":
            host.telnet_port = port
        else:
            host.ssh_port = port

    def _on_tags_changed(self, tag_ids: list[int]) -> None:
        """Sync tag assignments when pills are removed."""
        if self._host is None or self._host.id is None:
            return
        # Get current tag ids from DB
        current = {t.id for t in self._host_manager.get_host_tags(self._host.id)}
        desired = set(tag_ids)
        for tid in current - desired:
            self._host_manager.remove_tag_from_host(self._host.id, tid)
        for tid in desired - current:
            self._host_manager.add_tag_to_host(self._host.id, tid)
        # Refresh host tags
        self._host.tags = self._host_manager.get_host_tags(self._host.id)
        self.host_saved.emit()

    def _on_add_tag(self) -> None:
        """Show a popup menu to pick an existing tag or create a new one."""
        if self._host is None or self._host.id is None:
            return
        all_tags = self._host_manager.list_tags()
        current_ids = {t.id for t in self._host.tags}

        menu = QMenu(self)

        # Existing tags not yet assigned
        available = [t for t in all_tags if t.id not in current_ids]
        for tag in available:
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(tag.color or "#6c757d"))
            action = menu.addAction(QIcon(pixmap), tag.name)
            action.setData(("assign", tag))

        if available:
            menu.addSeparator()

        create_action = menu.addAction("+ Create new tag…")
        create_action.setData(("create", None))

        action = menu.exec(self._tag_selector._add_btn.mapToGlobal(
            self._tag_selector._add_btn.rect().bottomLeft()
        ))

        if action is None:
            return

        kind, data = action.data()
        if kind == "assign" and data:
            tag: Tag = data
            self._host_manager.add_tag_to_host(self._host.id, tag.id)
            self._host.tags = self._host_manager.get_host_tags(self._host.id)
            self._tag_selector.set_tags([
                {"id": t.id, "name": t.name, "color": t.color}
                for t in self._host.tags
            ])
            self.host_saved.emit()
        elif kind == "create":
            self._create_new_tag()

    def _create_new_tag(self) -> None:
        """Open a simple dialog to create a new tag and assign it."""
        if self._host is None or self._host.id is None:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("New Tag")
        dialog.setFixedSize(320, 200)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(20, 20, 20, 20)
        dlg_layout.setSpacing(12)

        name_label = QLabel("Name")
        name_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        dlg_layout.addWidget(name_label)
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("e.g. production")
        dlg_layout.addWidget(name_edit)

        color_label = QLabel("Color")
        color_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent;"
        )
        dlg_layout.addWidget(color_label)

        color_row = QHBoxLayout()
        tag_colors = ["#e94560", "#22c55e", "#3b82f6", "#f59e0b", "#7c3aed", "#ec4899", "#14b8a6", "#6c757d"]
        selected_color = {"value": tag_colors[0]}
        color_btns: list[QPushButton] = []

        def _select_color(c: str) -> None:
            selected_color["value"] = c
            for b in color_btns:
                bc = b.property("color_value")
                if bc == c:
                    b.setStyleSheet(
                        f"QPushButton {{ background-color: {bc}; "
                        f"border: 3px solid {Colors.TEXT_PRIMARY}; border-radius: 12px; }}"
                    )
                else:
                    b.setStyleSheet(
                        f"QPushButton {{ background-color: {bc}; "
                        f"border: 2px solid transparent; border-radius: 12px; }}"
                    )

        for c in tag_colors:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("color_value", c)
            btn.clicked.connect(lambda checked=False, color=c: _select_color(color))
            color_btns.append(btn)
            color_row.addWidget(btn)
        color_row.addStretch()
        _select_color(tag_colors[0])
        dlg_layout.addLayout(color_row)

        dlg_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            if not name:
                return
            tag = Tag(name=name, color=selected_color["value"])
            tag_id = self._host_manager.create_tag(tag)
            self._host_manager.add_tag_to_host(self._host.id, tag_id)
            self._host.tags = self._host_manager.get_host_tags(self._host.id)
            self._tag_selector.set_tags([
                {"id": t.id, "name": t.name, "color": t.color}
                for t in self._host.tags
            ])
            self.host_saved.emit()

    def _on_connect(self) -> None:
        if self._host and self._host.id:
            self.connect_requested.emit(self._host.id)

    def _on_delete(self) -> None:
        if self._host and self._host.id:
            self._host_manager.delete_host(self._host.id)
            self._host = None
            self.host_deleted.emit()
