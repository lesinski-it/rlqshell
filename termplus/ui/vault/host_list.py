"""Host list view with groups, search, and context menu."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors
from termplus.core.host_manager import HostManager
from termplus.core.models.host import Group, Host
from termplus.ui.widgets.badge import StatusBadge
from termplus.ui.widgets.empty_state import EmptyState
from termplus.ui.widgets.tag_widget import TagPill

logger = logging.getLogger(__name__)


class HostListItem(QWidget):
    """Single host row in the list."""

    clicked = Signal(int)  # host_id
    double_clicked = Signal(int)  # host_id
    context_menu_requested = Signal(int, object)  # host_id, QPoint

    def __init__(self, host: Host, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host_id = host.id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self.setStyleSheet(
            f"HostListItem {{ background: transparent; border-radius: 6px; }}"
            f"HostListItem:hover {{ background-color: {Colors.BG_SURFACE}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Protocol icon placeholder
        proto_label = QLabel(host.protocol.upper())
        proto_label.setFixedWidth(36)
        proto_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 4px; "
            f"padding: 2px 4px;"
        )
        layout.addWidget(proto_label)

        # Host info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        name_label = QLabel(host.label or "Unnamed")
        name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        info_layout.addWidget(name_label)

        addr_label = QLabel(host.address or "—")
        addr_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        info_layout.addWidget(addr_label)

        layout.addLayout(info_layout, 1)

        # Tags
        for tag in host.tags[:3]:
            pill = TagPill(tag.id or 0, tag.name, tag.color)
            layout.addWidget(pill)

        # Status badge
        badge = StatusBadge("disconnected")
        layout.addWidget(badge)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._host_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(self._host_id, event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._host_id)


class GroupSection(QWidget):
    """Collapsible group header with child hosts."""

    host_clicked = Signal(int)
    host_double_clicked = Signal(int)
    host_context_menu = Signal(int, object)

    def __init__(self, group: Group, hosts: list[Host], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QPushButton(f"  {group.name}  ({len(hosts)})")
        header.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: none; text-align: left; "
            f"  color: {Colors.TEXT_SECONDARY}; font-weight: 600; font-size: 12px; "
            f"  padding: 8px 12px; "
            f"}}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.clicked.connect(self._toggle)
        layout.addWidget(header)

        # Hosts container
        self._hosts_container = QWidget()
        hosts_layout = QVBoxLayout(self._hosts_container)
        hosts_layout.setContentsMargins(12, 0, 0, 0)
        hosts_layout.setSpacing(2)

        for h in hosts:
            item = HostListItem(h)
            item.clicked.connect(self.host_clicked.emit)
            item.double_clicked.connect(self.host_double_clicked.emit)
            item.context_menu_requested.connect(self.host_context_menu.emit)
            hosts_layout.addWidget(item)

        layout.addWidget(self._hosts_container)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._hosts_container.setVisible(not self._collapsed)


class HostListWidget(QWidget):
    """Full host list with toolbar, groups, and search."""

    host_selected = Signal(int)
    host_connect_requested = Signal(int)

    def __init__(self, host_manager: HostManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host_manager = host_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        tb_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search hosts…")
        self._search.setProperty("cssClass", "search")
        tb_layout.addWidget(self._search, 1)

        add_btn = QPushButton("+ New Host")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_new_host)
        tb_layout.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Content scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(4)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Empty state
        self._empty_state = EmptyState(
            title="No hosts yet",
            description="Create your first host to get started.",
            action_text="+ New Host",
        )
        self._empty_state.action_clicked.connect(self._on_new_host)
        self._empty_state.setVisible(False)
        self._content_layout.addWidget(self._empty_state)

        # Search debounce
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda: self._debounce.start())

        self.refresh()

    def refresh(self) -> None:
        """Rebuild the host list from the database."""
        # Clear existing items (except empty state)
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            widget = item.widget()
            if widget and widget is not self._empty_state:
                widget.deleteLater()

        search = self._search.text().strip() or None
        hosts = self._host_manager.list_hosts(search=search)
        groups = self._host_manager.list_groups()

        if not hosts and not search:
            self._empty_state.setVisible(True)
            return

        self._empty_state.setVisible(False)

        # Group hosts by group_id
        grouped: dict[int | None, list[Host]] = {}
        for h in hosts:
            grouped.setdefault(h.group_id, []).append(h)

        # Ungrouped hosts first
        for h in grouped.get(None, []):
            item = HostListItem(h)
            item.clicked.connect(self.host_selected.emit)
            item.double_clicked.connect(self.host_connect_requested.emit)
            item.context_menu_requested.connect(self._on_context_menu)
            self._content_layout.addWidget(item)

        # Grouped hosts
        for group in groups:
            group_hosts = grouped.get(group.id, [])
            if not group_hosts and search:
                continue
            section = GroupSection(group, group_hosts)
            section.host_clicked.connect(self.host_selected.emit)
            section.host_double_clicked.connect(self.host_connect_requested.emit)
            section.host_context_menu.connect(self._on_context_menu)
            self._content_layout.addWidget(section)

    def _on_new_host(self) -> None:
        host = Host(label="", address="")
        host_id = self._host_manager.create_host(host)
        self.refresh()
        self.host_selected.emit(host_id)

    def _on_context_menu(self, host_id: int, pos) -> None:
        menu = QMenu(self)
        connect_action = menu.addAction("Connect")
        menu.addSeparator()
        edit_action = menu.addAction("Edit")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(pos)
        if action == connect_action:
            self.host_connect_requested.emit(host_id)
        elif action == edit_action:
            self.host_selected.emit(host_id)
        elif action == duplicate_action:
            self._duplicate_host(host_id)
        elif action == delete_action:
            self._host_manager.delete_host(host_id)
            self.refresh()

    def _duplicate_host(self, host_id: int) -> None:
        host = self._host_manager.get_host(host_id)
        if host:
            host.id = None
            host.label = f"{host.label} (copy)"
            new_id = self._host_manager.create_host(host)
            self.refresh()
            self.host_selected.emit(new_id)
