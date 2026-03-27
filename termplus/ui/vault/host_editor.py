"""Host editor slide-in panel with auto-save."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.credential_store import CredentialStore
from termplus.core.host_manager import HostManager
from termplus.core.keychain import Keychain
from termplus.core.models.host import Host

logger = logging.getLogger(__name__)


class HostEditorContent(QWidget):
    """Scrollable form content for editing a host."""

    host_saved = Signal()
    host_deleted = Signal()
    connect_requested = Signal(int)  # host_id

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
        self._label_edit = self._add_field("Label", QLineEdit())
        self._label_edit.setPlaceholderText("e.g. web-server-1")

        # Address
        self._address_edit = self._add_field("Address", QLineEdit())
        self._address_edit.setPlaceholderText("IP or hostname")

        # Protocol
        self._protocol_combo = QComboBox()
        self._protocol_combo.addItems(["ssh", "rdp", "vnc", "telnet", "serial"])
        self._add_field("Protocol", self._protocol_combo)

        # Port
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        self._add_field("Port", self._port_spin)

        # Identity
        self._identity_combo = QComboBox()
        self._populate_identities()
        self._identity_combo.currentIndexChanged.connect(self._on_identity_changed)
        self._add_field("Identity", self._identity_combo)

        # Group
        self._group_combo = QComboBox()
        self._group_combo.addItem("No group", None)
        self._add_field("Group", self._group_combo)

        # SSH options section
        ssh_header = QLabel("SSH Options")
        ssh_header.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; padding-top: 8px;"
        )
        self._form_layout.addWidget(ssh_header)

        # Keep Alive
        self._keep_alive_spin = QSpinBox()
        self._keep_alive_spin.setRange(0, 3600)
        self._keep_alive_spin.setValue(60)
        self._keep_alive_spin.setSuffix(" sec")
        self._add_field("Keep Alive", self._keep_alive_spin)

        # Agent Forwarding
        self._agent_fwd_check = QCheckBox("Enable SSH Agent Forwarding")
        self._form_layout.addWidget(self._agent_fwd_check)

        # Compression
        self._compression_check = QCheckBox("Enable Compression")
        self._form_layout.addWidget(self._compression_check)

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
        self._color_buttons: list[QPushButton] = []
        for color in ["#e94560", "#22c55e", "#3b82f6", "#f59e0b", "#7c3aed", "#ec4899"]:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color}; border: 2px solid transparent; "
                f"border-radius: 10px; }}"
                f"QPushButton:hover {{ border-color: {Colors.TEXT_PRIMARY}; }}"
            )
            btn.clicked.connect(lambda checked=False, c=color: self._set_color(c))
            self._color_buttons.append(btn)
            self._color_row.addWidget(btn)
        self._color_row.addStretch()
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

    def load_host(self, host_id: int) -> None:
        """Load a host into the editor."""
        host = self._host_manager.get_host(host_id)
        if host is None:
            return
        self._host = host

        # Block signals during load
        for w in [self._label_edit, self._address_edit, self._port_spin,
                   self._keep_alive_spin, self._notes_edit]:
            w.blockSignals(True)
        self._protocol_combo.blockSignals(True)
        self._agent_fwd_check.blockSignals(True)
        self._compression_check.blockSignals(True)
        self._group_combo.blockSignals(True)

        self._label_edit.setText(host.label)
        self._address_edit.setText(host.address)
        self._protocol_combo.setCurrentText(host.protocol)
        self._port_spin.setValue(host.ssh_port)
        self._keep_alive_spin.setValue(host.ssh_keep_alive)
        self._agent_fwd_check.setChecked(host.ssh_agent_forwarding)
        self._compression_check.setChecked(host.ssh_compression)
        self._notes_edit.setPlainText(host.notes or "")

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
                   self._keep_alive_spin, self._notes_edit]:
            w.blockSignals(False)
        self._protocol_combo.blockSignals(False)
        self._agent_fwd_check.blockSignals(False)
        self._compression_check.blockSignals(False)
        self._group_combo.blockSignals(False)

        self._save_indicator.setText("")

    def _populate_identities(self) -> None:
        """Fill the identity dropdown from CredentialStore."""
        self._identity_combo.clear()
        self._identity_combo.addItem("— None —", None)
        if self._credential_store:
            for ident in self._credential_store.list_identities():
                display = f"{ident.label} ({ident.username})"
                self._identity_combo.addItem(display, ident.id)
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
        from termplus.ui.vault.identity_editor import IdentityEditor
        editor = IdentityEditor(self._credential_store, self._keychain, self)
        if editor.exec() == IdentityEditor.DialogCode.Accepted:
            self._populate_identities()
            # Select the newly created identity (last before "+ Create new…")
            self._identity_combo.setCurrentIndex(self._identity_combo.count() - 2)
        else:
            self._identity_combo.setCurrentIndex(0)

    def _add_field(self, label: str, widget: QWidget) -> QWidget:
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent; margin-bottom: 2px;"
        )
        self._form_layout.addWidget(lbl)
        self._form_layout.addWidget(widget)
        return widget

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
        self._host.ssh_port = self._port_spin.value()
        self._host.ssh_keep_alive = self._keep_alive_spin.value()
        self._host.ssh_agent_forwarding = self._agent_fwd_check.isChecked()
        self._host.ssh_compression = self._compression_check.isChecked()
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
            self._schedule_save()

    def _on_connect(self) -> None:
        if self._host and self._host.id:
            self.connect_requested.emit(self._host.id)

    def _on_delete(self) -> None:
        if self._host and self._host.id:
            self._host_manager.delete_host(self._host.id)
            self._host = None
            self.host_deleted.emit()
