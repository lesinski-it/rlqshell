"""Host list view with groups, search, filtering, drag-and-drop, and context menu."""

from __future__ import annotations

import logging

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
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
from termplus.core.connection_pool import ConnectionPool
from termplus.core.host_manager import HostManager
from termplus.core.models.host import Group, Host, Tag
from termplus.ui.widgets.badge import StatusBadge
from termplus.ui.widgets.empty_state import EmptyState
from termplus.ui.widgets.tag_widget import TagPill

logger = logging.getLogger(__name__)

# Protocol display colors
PROTOCOL_COLORS: dict[str, str] = {
    "ssh": "#22c55e",
    "rdp": "#3b82f6",
    "vnc": "#f59e0b",
    "telnet": "#e94560",
    "serial": "#7c3aed",
}

ALL_PROTOCOLS = ["ssh", "rdp", "vnc", "telnet", "serial"]

_DRAG_MIME = "application/x-termplus-host-id"


class _FilterChip(QPushButton):
    """Toggleable filter chip button."""

    toggled_signal = Signal(str, bool)  # value, checked

    def __init__(self, label: str, value: str, color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._value = value
        self._color = color or Colors.ACCENT
        self._checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.clicked.connect(self._on_click)
        self._apply_style()

    @property
    def checked(self) -> bool:
        return self._checked

    @checked.setter
    def checked(self, value: bool) -> None:
        self._checked = value
        self._apply_style()

    @property
    def value(self) -> str:
        return self._value

    def _on_click(self) -> None:
        self._checked = not self._checked
        self._apply_style()
        self.toggled_signal.emit(self._value, self._checked)

    def _apply_style(self) -> None:
        if self._checked:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background-color: {self._color}; color: #ffffff; "
                f"  border: none; border-radius: 14px; "
                f"  padding: 6px 14px; font-size: 12px; font-weight: 600; "
                f"}}"
                f"QPushButton:hover {{ background-color: {self._color}; opacity: 0.9; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background-color: transparent; color: {Colors.TEXT_MUTED}; "
                f"  border: 1px solid {Colors.BORDER}; border-radius: 14px; "
                f"  padding: 6px 14px; font-size: 12px; font-weight: 600; "
                f"}}"
                f"QPushButton:hover {{ border-color: {self._color}; color: {self._color}; }}"
            )


class FilterBar(QWidget):
    """Filter bar with protocol and tag chips."""

    filters_changed = Signal()

    def __init__(self, host_manager: HostManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._protocol_chips: list[_FilterChip] = []
        self._tag_chips: list[_FilterChip] = []

        self.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 10)
        layout.setSpacing(8)

        # Protocol row
        proto_row = QHBoxLayout()
        proto_row.setSpacing(6)

        proto_label = QLabel("Protocol")
        proto_label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {Colors.TEXT_MUTED}; "
            f"background: transparent;"
        )
        proto_label.setFixedWidth(56)
        proto_row.addWidget(proto_label)

        for proto in ALL_PROTOCOLS:
            chip = _FilterChip(
                proto.upper(), proto,
                color=PROTOCOL_COLORS.get(proto, Colors.ACCENT),
            )
            chip.toggled_signal.connect(lambda v, c: self.filters_changed.emit())
            self._protocol_chips.append(chip)
            proto_row.addWidget(chip)

        proto_row.addStretch()
        layout.addLayout(proto_row)

        # Tag row (same flat structure as protocol row)
        self._tag_row = QHBoxLayout()
        self._tag_row.setSpacing(6)

        self._tag_label = QLabel("Tags")
        self._tag_label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {Colors.TEXT_MUTED}; "
            f"background: transparent;"
        )
        self._tag_label.setFixedWidth(56)
        self._tag_row.addWidget(self._tag_label)

        # Chips will be added here by _rebuild_tags
        # We add stretch at the end after chips
        self._tag_row.addStretch()

        layout.addLayout(self._tag_row)
        self._rebuild_tags()

    def _rebuild_tags(self) -> None:
        """Rebuild tag chips from database, preserving checked state."""
        # Remember which tags were checked
        checked_ids = {c.value for c in self._tag_chips if c.checked}

        # Remove old chip widgets (keep label at 0 and stretch at end)
        for chip in self._tag_chips:
            self._tag_row.removeWidget(chip)
            chip.deleteLater()
        self._tag_chips.clear()

        tags = self._host_manager.list_tags()

        # Hide label if no tags
        self._tag_label.setVisible(bool(tags))

        # Insert chips before the stretch (which is the last item)
        insert_pos = 1  # after the label
        for tag in tags:
            chip = _FilterChip(tag.name, str(tag.id), color=tag.color)
            if str(tag.id) in checked_ids:
                chip.checked = True
            chip.toggled_signal.connect(lambda v, c: self.filters_changed.emit())
            self._tag_chips.append(chip)
            self._tag_row.insertWidget(insert_pos, chip)
            insert_pos += 1

    def refresh_tags(self) -> None:
        """Refresh tag chips (e.g. after a tag is created/deleted)."""
        self._rebuild_tags()

    @property
    def active_protocol(self) -> str | None:
        """Return the single active protocol filter, or None if none/multiple."""
        active = [c.value for c in self._protocol_chips if c.checked]
        if len(active) == 1:
            return active[0]
        return None

    @property
    def active_protocols(self) -> list[str]:
        """Return list of active protocol filters."""
        return [c.value for c in self._protocol_chips if c.checked]

    @property
    def active_tag_ids(self) -> list[int]:
        """Return list of active tag id filters."""
        return [int(c.value) for c in self._tag_chips if c.checked]

    def has_active_filters(self) -> bool:
        return bool(self.active_protocols or self.active_tag_ids)

    def clear_filters(self) -> None:
        for c in self._protocol_chips:
            c.checked = False
        for c in self._tag_chips:
            c.checked = False


class HostListItem(QWidget):
    """Single host row in the list."""

    clicked = Signal(int)  # host_id
    double_clicked = Signal(int)  # host_id
    context_menu_requested = Signal(int, object)  # host_id, QPoint

    def __init__(self, host: Host, connected: bool = False, parent: QWidget | None = None) -> None:
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

        # Drag handle
        handle = QLabel("\u2261")
        handle.setFixedWidth(16)
        handle.setStyleSheet(
            f"font-size: 18px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(handle)

        # Protocol badge with color
        proto_color = PROTOCOL_COLORS.get(host.protocol, Colors.TEXT_MUTED)
        proto_label = QLabel(host.protocol.upper())
        proto_label.setFixedWidth(36)
        proto_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {proto_color}; "
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

        addr_label = QLabel(host.address or "\u2014")
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
        status = "connected" if connected else "disconnected"
        self._badge = StatusBadge(status)
        layout.addWidget(self._badge)

        # Drag state
        self._drag_start: QPoint | None = None

    @property
    def host_id(self) -> int:
        return self._host_id

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(self._host_id, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None:
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_DRAG_MIME, str(self._host_id).encode())
        drag.setMimeData(mime)

        pixmap = QPixmap(self.size())
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setOpacity(0.6)
        self.render(painter, QPoint())
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(self._drag_start)

        self._drag_start = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self.clicked.emit(self._host_id)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.double_clicked.emit(self._host_id)


class _DropIndicator(QWidget):
    """Thin horizontal line shown between items during drag."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet(f"background-color: {Colors.ACCENT}; border-radius: 1px;")
        self.hide()


class GroupSection(QWidget):
    """Collapsible group header with child hosts."""

    host_clicked = Signal(int)
    host_double_clicked = Signal(int)
    host_context_menu = Signal(int, object)
    edit_requested = Signal(int)  # group_id
    delete_requested = Signal(int)  # group_id
    host_dropped = Signal(int, int)  # host_id, group_id
    hosts_reordered = Signal(list)  # ordered host_ids

    def __init__(
        self, group: Group, hosts: list[Host],
        connected_ids: set[int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._group = group
        self._collapsed = False
        connected_ids = connected_ids or set()

        # Outer layout — color bar on the left covers entire group
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Color bar spanning full group height
        if group.color:
            color_bar = QWidget()
            color_bar.setFixedWidth(3)
            color_bar.setStyleSheet(f"background-color: {group.color}; border-radius: 1px;")
            outer_layout.addWidget(color_bar)

        # Content (header + hosts)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header row — accepts drops for "move host into this group"
        self._header_widget = QWidget()
        self._header_widget.setAcceptDrops(True)
        self._header_widget.dragEnterEvent = self._header_drag_enter
        self._header_widget.dragLeaveEvent = self._header_drag_leave
        self._header_widget.dropEvent = self._header_drop
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(0, 0, 8, 0)
        header_layout.setSpacing(0)

        self._header_btn = QPushButton(f"  \u25be  {group.name}  ({len(hosts)})")
        self._header_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: none; text-align: left; "
            f"  color: {Colors.TEXT_SECONDARY}; font-weight: 600; font-size: 12px; "
            f"  padding: 8px 12px; "
            f"}}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
            f"  background-color: {Colors.BG_SURFACE}; border-radius: 4px; }}"
        )
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._header_btn, 1)

        # Group context menu button
        menu_btn = QPushButton("\u22ef")
        menu_btn.setFixedSize(28, 28)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: none; "
            f"  color: {Colors.TEXT_MUTED}; font-size: 16px; font-weight: 700; "
            f"}}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
            f"  background-color: {Colors.BG_HOVER}; border-radius: 4px; }}"
        )
        menu_btn.clicked.connect(self._on_menu)
        header_layout.addWidget(menu_btn)

        layout.addWidget(self._header_widget)

        # Hosts container
        self._hosts_container = QWidget()
        self._hosts_container.setAcceptDrops(True)
        self._hosts_container.dragEnterEvent = self._container_drag_enter
        self._hosts_container.dragMoveEvent = self._container_drag_move
        self._hosts_container.dragLeaveEvent = self._container_drag_leave
        self._hosts_container.dropEvent = self._container_drop
        hosts_layout = QVBoxLayout(self._hosts_container)
        hosts_layout.setContentsMargins(12, 0, 0, 0)
        hosts_layout.setSpacing(2)

        if hosts:
            for h in hosts:
                item = HostListItem(h, connected=(h.id or 0) in connected_ids)
                item.clicked.connect(self.host_clicked.emit)
                item.double_clicked.connect(self.host_double_clicked.emit)
                item.context_menu_requested.connect(self.host_context_menu.emit)
                hosts_layout.addWidget(item)
        else:
            empty_label = QLabel("No hosts in this group")
            empty_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-style: italic; "
                f"background: transparent; padding: 8px 12px;"
            )
            hosts_layout.addWidget(empty_label)

        layout.addWidget(self._hosts_container)
        outer_layout.addWidget(content, 1)

        # Drop indicator inside group
        self._drop_indicator = _DropIndicator(self._hosts_container)
        # Drop highlight state (for header area)
        self._drop_highlight = False

    @property
    def group_id(self) -> int:
        return self._group.id or 0

    def _host_items(self) -> list[HostListItem]:
        layout = self._hosts_container.layout()
        items: list[HostListItem] = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, HostListItem):
                items.append(w)
        return items

    def _drop_index(self, pos: QPoint) -> int:
        items = self._host_items()
        if not items:
            return 0
        for idx, item in enumerate(items):
            if item.y() <= pos.y() < item.y() + item.height():
                return idx
        if pos.y() < items[0].y():
            return 0
        return len(items) - 1

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._hosts_container.setVisible(not self._collapsed)
        arrow = "\u25b8" if self._collapsed else "\u25be"
        group = self._group
        # Update button text with correct arrow
        text = self._header_btn.text()
        self._header_btn.setText(f"  {arrow}  {group.name}  ({text.split('(')[-1]}")

    def _on_menu(self) -> None:
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Group")
        menu.addSeparator()
        delete_action = menu.addAction("Delete Group")

        action = menu.exec(self.cursor().pos())
        if action == edit_action:
            self.edit_requested.emit(self._group.id or 0)
        elif action == delete_action:
            self.delete_requested.emit(self._group.id or 0)

    def _set_header_highlight(self, on: bool) -> None:
        if on == self._drop_highlight:
            return
        self._drop_highlight = on
        btn = self._header_btn
        if on:
            btn.setStyleSheet(
                f"QPushButton {{ "
                f"  background-color: rgba(124, 58, 237, 0.15); border: none; "
                f"  text-align: left; color: {Colors.TEXT_PRIMARY}; "
                f"  font-weight: 600; font-size: 12px; padding: 8px 12px; "
                f"  border-radius: 4px; "
                f"}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ "
                f"  background: transparent; border: none; text-align: left; "
                f"  color: {Colors.TEXT_SECONDARY}; font-weight: 600; font-size: 12px; "
                f"  padding: 8px 12px; "
                f"}}"
                f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
                f"  background-color: {Colors.BG_SURFACE}; border-radius: 4px; }}"
            )

    # Header drag — drop onto group header = move host into this group
    def _header_drag_enter(self, event) -> None:
        if event.mimeData().hasFormat(_DRAG_MIME):
            event.acceptProposedAction()
            self._set_header_highlight(True)

    def _header_drag_leave(self, event) -> None:
        self._set_header_highlight(False)

    def _header_drop(self, event) -> None:
        self._set_header_highlight(False)
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()
        host_id = int(event.mimeData().data(_DRAG_MIME).data().decode())
        self.host_dropped.emit(host_id, self._group.id or 0)

    def _clear_item_highlights(self) -> None:
        for item in self._host_items():
            item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            item.setStyleSheet(
                f"background: transparent; border-radius: 6px;"
            )

    def _highlight_item_at(self, idx: int) -> None:
        self._clear_item_highlights()
        items = self._host_items()
        if 0 <= idx < len(items):
            items[idx].setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            items[idx].setStyleSheet(
                f"background-color: rgba(124, 58, 237, 0.15); border-radius: 6px;"
            )

    # Container-level drag (reorder within group)
    def _container_drag_enter(self, event) -> None:
        if event.mimeData().hasFormat(_DRAG_MIME):
            event.acceptProposedAction()

    def _container_drag_move(self, event) -> None:
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()
        if not self._host_items():
            return
        self._highlight_item_at(self._drop_index(event.position().toPoint()))

    def _container_drag_leave(self, event) -> None:
        self._clear_item_highlights()

    def _container_drop(self, event) -> None:
        self._clear_item_highlights()
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()

        host_id = int(event.mimeData().data(_DRAG_MIME).data().decode())
        target_idx = self._drop_index(event.position().toPoint())

        items = self._host_items()
        ordered_ids = [it.host_id for it in items]

        if host_id in ordered_ids:
            # Reorder within group
            old_idx = ordered_ids.index(host_id)
            if old_idx == target_idx:
                return
            ordered_ids.pop(old_idx)
            ordered_ids.insert(target_idx, host_id)
            self.hosts_reordered.emit(ordered_ids)
        else:
            # Moving from outside into this group at specific position
            ordered_ids.insert(target_idx, host_id)
            self.host_dropped.emit(host_id, self._group.id or 0)
            self.hosts_reordered.emit(ordered_ids)


class HostListWidget(QWidget):
    """Full host list with toolbar, filters, groups, and search."""

    host_selected = Signal(int)
    host_connect_requested = Signal(int)
    sftp_requested = Signal(int)  # host_id

    def __init__(
        self, host_manager: HostManager,
        connection_pool: ConnectionPool | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._host_manager = host_manager
        self._connection_pool = connection_pool

        # Auto-refresh badges when connection status changes
        if connection_pool is not None:
            connection_pool.host_status_changed.connect(self._on_host_status_changed)

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
        self._search.setPlaceholderText("Search hosts\u2026")
        self._search.setProperty("cssClass", "search")
        tb_layout.addWidget(self._search, 1)

        # Filter toggle button
        self._filter_btn = QPushButton("\u26db Filter")
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setCheckable(True)
        self._filter_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 4px; padding: 4px 12px; "
            f"  color: {Colors.TEXT_SECONDARY}; font-size: 12px; "
            f"}}"
            f"QPushButton:checked {{ "
            f"  background-color: {Colors.ACCENT}; border-color: {Colors.ACCENT}; "
            f"  color: #ffffff; "
            f"}}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; }}"
        )
        self._filter_btn.clicked.connect(self._toggle_filter_bar)
        tb_layout.addWidget(self._filter_btn)

        # Add dropdown button
        add_btn = QPushButton("+ New")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_menu)
        tb_layout.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Filter bar (hidden by default)
        self._filter_bar = FilterBar(host_manager)
        self._filter_bar.filters_changed.connect(self.refresh)
        self._filter_bar.setVisible(False)
        layout.addWidget(self._filter_bar)

        # Active filters indicator
        self._active_filters_bar = QWidget()
        self._active_filters_bar.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")
        af_layout = QHBoxLayout(self._active_filters_bar)
        af_layout.setContentsMargins(16, 0, 16, 6)
        af_layout.setSpacing(8)
        self._active_filters_label = QLabel()
        self._active_filters_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.ACCENT_LIGHT}; background: transparent;"
        )
        af_layout.addWidget(self._active_filters_label, 1)
        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: transparent; border: none; "
            f"  color: {Colors.TEXT_MUTED}; font-size: 11px; text-decoration: underline; "
            f"}}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        clear_btn.clicked.connect(self._clear_filters)
        af_layout.addWidget(clear_btn)
        self._active_filters_bar.setVisible(False)
        layout.addWidget(self._active_filters_bar)

        # Content scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setAcceptDrops(True)
        self._content.dragEnterEvent = self._on_drag_enter
        self._content.dragMoveEvent = self._on_drag_move
        self._content.dragLeaveEvent = self._on_drag_leave
        self._content.dropEvent = self._on_drop
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(4)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Drop indicator
        self._drop_indicator = _DropIndicator(self._content)

        # Empty state
        self._empty_state = EmptyState(
            title="No hosts yet",
            description="Create your first host to get started.",
            action_text="+ New Host",
        )
        self._empty_state.action_clicked.connect(self._on_new_host)
        self._empty_state.setVisible(False)
        self._content_layout.addWidget(self._empty_state)

        # No results state (for filtered/searched)
        self._no_results = EmptyState(
            title="No matching hosts",
            description="Try adjusting your search or filters.",
        )
        self._no_results.setVisible(False)
        self._content_layout.addWidget(self._no_results)

        # Search debounce
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda: self._debounce.start())

        self.refresh()

    # --- Drag & drop on ungrouped area ---

    def _ungrouped_items(self) -> list[HostListItem]:
        items: list[HostListItem] = []
        for i in range(self._content_layout.count()):
            w = self._content_layout.itemAt(i).widget()
            if isinstance(w, HostListItem):
                items.append(w)
        return items

    def _drop_index(self, pos: QPoint) -> int:
        items = self._ungrouped_items()
        if not items:
            return 0
        for idx, item in enumerate(items):
            if item.y() <= pos.y() < item.y() + item.height():
                return idx
        if pos.y() < items[0].y():
            return 0
        return len(items) - 1

    def _clear_ungrouped_highlights(self) -> None:
        for item in self._ungrouped_items():
            item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            item.setStyleSheet(
                f"background: transparent; border-radius: 6px;"
            )

    def _highlight_ungrouped_at(self, idx: int) -> None:
        self._clear_ungrouped_highlights()
        items = self._ungrouped_items()
        if 0 <= idx < len(items):
            items[idx].setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            items[idx].setStyleSheet(
                f"background-color: rgba(124, 58, 237, 0.15); border-radius: 6px;"
            )

    def _on_drag_enter(self, event) -> None:
        if event.mimeData().hasFormat(_DRAG_MIME):
            event.acceptProposedAction()

    def _on_drag_move(self, event) -> None:
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()
        if not self._ungrouped_items():
            return
        self._highlight_ungrouped_at(self._drop_index(event.position().toPoint()))

    def _on_drag_leave(self, event) -> None:
        self._clear_ungrouped_highlights()

    def _on_drop(self, event) -> None:
        self._clear_ungrouped_highlights()
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()

        host_id = int(event.mimeData().data(_DRAG_MIME).data().decode())

        # Move host to ungrouped
        self._host_manager.move_host_to_group(host_id, None)

        # Reorder ungrouped hosts
        items = self._ungrouped_items()
        target_idx = self._drop_index(event.position().toPoint())
        ordered_ids = [it.host_id for it in items]
        # Remove if already in list (was ungrouped)
        if host_id in ordered_ids:
            old_idx = ordered_ids.index(host_id)
            if old_idx == target_idx:
                return
            ordered_ids.pop(old_idx)
        ordered_ids.insert(target_idx, host_id)
        self._host_manager.reorder_hosts(ordered_ids)
        self.refresh()

    def _on_host_dropped_to_group(self, host_id: int, group_id: int) -> None:
        """Handle a host being dropped onto a group section."""
        self._host_manager.move_host_to_group(host_id, group_id)
        self.refresh()

    def _on_hosts_reordered(self, ordered_ids: list[int]) -> None:
        """Handle reordering of hosts within a group."""
        self._host_manager.reorder_hosts(ordered_ids)
        self.refresh()

    # --- Regular methods ---

    def _toggle_filter_bar(self) -> None:
        visible = self._filter_btn.isChecked()
        self._filter_bar.setVisible(visible)
        if not visible and self._filter_bar.has_active_filters():
            self._filter_bar.clear_filters()
            self.refresh()

    def _clear_filters(self) -> None:
        self._filter_bar.clear_filters()
        self.refresh()

    def _on_add_menu(self) -> None:
        menu = QMenu(self)
        new_host_action = menu.addAction("New Host")
        new_group_action = menu.addAction("New Group")

        action = menu.exec(self.cursor().pos())
        if action == new_host_action:
            self._on_new_host()
        elif action == new_group_action:
            self._on_new_group()

    def _on_new_group(self) -> None:
        from termplus.ui.vault.group_editor import GroupEditor
        editor = GroupEditor(self._host_manager, parent=self)
        editor.group_saved.connect(self.refresh)
        editor.exec()

    def _edit_group(self, group_id: int) -> None:
        groups = self._host_manager.list_groups()
        group = next((g for g in groups if g.id == group_id), None)
        if group is None:
            return
        from termplus.ui.vault.group_editor import GroupEditor
        editor = GroupEditor(self._host_manager, group=group, parent=self)
        editor.group_saved.connect(self.refresh)
        editor.exec()

    def _delete_group(self, group_id: int) -> None:
        # Move hosts from this group to ungrouped before deleting
        hosts = self._host_manager.list_hosts(group_id=group_id)
        for h in hosts:
            h.group_id = None
            self._host_manager.update_host(h)
        self._host_manager.delete_group(group_id)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the host list from the database."""
        # Clear existing items (except persistent states)
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            widget = item.widget()
            if widget and widget not in (self._empty_state, self._no_results):
                widget.deleteLater()

        search = self._search.text().strip() or None

        # Gather filters
        active_protocols = self._filter_bar.active_protocols
        active_tag_ids = self._filter_bar.active_tag_ids
        has_filters = bool(active_protocols or active_tag_ids)

        # Update active filters indicator
        self._update_filters_indicator(active_protocols, active_tag_ids)

        # Query hosts — filter by one protocol at a time or all matching
        all_hosts: list[Host] = []
        if len(active_protocols) <= 1:
            proto = active_protocols[0] if active_protocols else None
            all_hosts = self._host_manager.list_hosts(
                search=search, protocol=proto,
                tag_ids=active_tag_ids or None,
            )
        else:
            # Multiple protocols selected — union results
            seen_ids: set[int] = set()
            for proto in active_protocols:
                hosts = self._host_manager.list_hosts(
                    search=search, protocol=proto,
                    tag_ids=active_tag_ids or None,
                )
                for h in hosts:
                    if h.id not in seen_ids:
                        seen_ids.add(h.id or 0)
                        all_hosts.append(h)

        groups = self._host_manager.list_groups()

        # No hosts at all — show empty state
        if not all_hosts and not search and not has_filters:
            self._empty_state.setVisible(True)
            self._no_results.setVisible(False)
            return

        # No results for search/filter — show no results state
        if not all_hosts and (search or has_filters):
            self._empty_state.setVisible(False)
            self._no_results.setVisible(True)
            return

        self._empty_state.setVisible(False)
        self._no_results.setVisible(False)

        # Get connected host IDs
        connected_ids: set[int] = set()
        if self._connection_pool is not None:
            connected_ids = self._connection_pool.connected_host_ids()

        # Group hosts by group_id
        grouped: dict[int | None, list[Host]] = {}
        for h in all_hosts:
            grouped.setdefault(h.group_id, []).append(h)

        # Ungrouped hosts first
        for h in grouped.get(None, []):
            item = HostListItem(h, connected=(h.id or 0) in connected_ids)
            item.clicked.connect(self.host_selected.emit)
            item.double_clicked.connect(self.host_connect_requested.emit)
            item.context_menu_requested.connect(self._on_context_menu)
            self._content_layout.addWidget(item)

        # Grouped hosts
        for group in groups:
            group_hosts = grouped.get(group.id, [])
            # When filtering, skip groups with no matching hosts
            if not group_hosts and (search or has_filters):
                continue
            section = GroupSection(group, group_hosts, connected_ids=connected_ids)
            section.host_clicked.connect(self.host_selected.emit)
            section.host_double_clicked.connect(self.host_connect_requested.emit)
            section.host_context_menu.connect(self._on_context_menu)
            section.edit_requested.connect(self._edit_group)
            section.delete_requested.connect(self._delete_group)
            section.host_dropped.connect(self._on_host_dropped_to_group)
            section.hosts_reordered.connect(self._on_hosts_reordered)
            self._content_layout.addWidget(section)

        # Refresh tag chips in filter bar (in case tags changed)
        self._filter_bar.refresh_tags()

    def _update_filters_indicator(self, protocols: list[str], tag_ids: list[int]) -> None:
        if not protocols and not tag_ids:
            self._active_filters_bar.setVisible(False)
            return

        parts: list[str] = []
        if protocols:
            parts.append("Protocol: " + ", ".join(p.upper() for p in protocols))
        if tag_ids:
            tags = self._host_manager.list_tags()
            tag_map = {t.id: t.name for t in tags}
            tag_names = [tag_map.get(tid, "?") for tid in tag_ids]
            parts.append("Tags: " + ", ".join(tag_names))

        self._active_filters_label.setText("Active filters: " + " | ".join(parts))
        self._active_filters_bar.setVisible(True)

    def _on_host_status_changed(self, host_id: int, status: str) -> None:
        """Refresh the list when a host connects or disconnects."""
        self.refresh()

    def _on_new_host(self) -> None:
        host = Host(label="", address="")
        host_id = self._host_manager.create_host(host)
        self.refresh()
        self.host_selected.emit(host_id)

    def _on_context_menu(self, host_id: int, pos) -> None:
        host = self._host_manager.get_host(host_id)
        menu = QMenu(self)
        connect_action = menu.addAction("Connect")
        sftp_action = menu.addAction("Open SFTP") if host and host.protocol == "ssh" else None
        menu.addSeparator()
        edit_action = menu.addAction("Edit")
        duplicate_action = menu.addAction("Duplicate")

        # Move to group submenu
        groups = self._host_manager.list_groups()
        if groups:
            menu.addSeparator()
            move_menu = menu.addMenu("Move to Group")
            no_group_action = move_menu.addAction("No group")
            move_menu.addSeparator()
            group_actions = {}
            for g in groups:
                if host and g.id != host.group_id:
                    action = move_menu.addAction(g.name)
                    group_actions[action] = g.id

        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(pos)
        if action == connect_action:
            self.host_connect_requested.emit(host_id)
        elif sftp_action and action == sftp_action:
            self.sftp_requested.emit(host_id)
        elif action == edit_action:
            self.host_selected.emit(host_id)
        elif action == duplicate_action:
            self._duplicate_host(host_id)
        elif action == delete_action:
            self._host_manager.delete_host(host_id)
            self.refresh()
        elif groups and action == no_group_action:
            self._move_host_to_group(host_id, None)
        elif groups and action in group_actions:
            self._move_host_to_group(host_id, group_actions[action])

    def _move_host_to_group(self, host_id: int, group_id: int | None) -> None:
        host = self._host_manager.get_host(host_id)
        if host:
            host.group_id = group_id
            self._host_manager.update_host(host)
            self.refresh()

    def _duplicate_host(self, host_id: int) -> None:
        host = self._host_manager.get_host(host_id)
        if host:
            host.id = None
            host.label = f"{host.label} (copy)"
            new_id = self._host_manager.create_host(host)
            self.refresh()
            self.host_selected.emit(new_id)
