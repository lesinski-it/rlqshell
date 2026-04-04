"""Split Picker — floating fuzzy search dialog for choosing a host to split with."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors

logger = logging.getLogger(__name__)

_MAX_RESULTS = 10


def _fuzzy_score(query: str, text: str) -> int:
    """Fuzzy match returning score (higher = better), 0 = no match."""
    query_lower = query.lower()
    text_lower = text.lower()
    if not query_lower:
        return 1
    qi = 0
    score = 0
    prev_match = -1
    for ti, ch in enumerate(text_lower):
        if qi < len(query_lower) and ch == query_lower[qi]:
            score += 10
            if prev_match == ti - 1:
                score += 5
            if ti == 0 or text_lower[ti - 1] in " _-.@/:":
                score += 3
            prev_match = ti
            qi += 1
    return score if qi == len(query_lower) else 0


class _HostResultItem(QWidget):
    """Custom widget for a single host result row."""

    def __init__(
        self,
        label: str,
        address: str,
        group: str,
        tags: str,
        protocol: str,
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # Color dot
        if color:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background-color: {color}; border-radius: 4px; border: none;"
            )
            layout.addWidget(dot)

        # Protocol badge
        proto = QLabel(protocol.upper())
        proto.setFixedWidth(36)
        proto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 3px; "
            f"padding: 1px 4px; border: none;"
        )
        layout.addWidget(proto)

        # Text column
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        title = QLabel(label)
        title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        text_col.addWidget(title)

        subtitle_parts = [address]
        if group:
            subtitle_parts.append(f"group: {group}")
        if tags:
            subtitle_parts.append(tags)
        sub = QLabel("  \u00b7  ".join(subtitle_parts))
        sub.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; border: none;"
        )
        text_col.addWidget(sub)

        layout.addLayout(text_col, 1)

    def paintEvent(self, event) -> None:
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(self.style().PrimitiveElement.PE_Widget, opt, p, self)
        p.end()


class SplitPickerDialog(QWidget):
    """Floating overlay dialog for picking a host to open in a split panel.

    Signals:
        host_picked(int, str): Emitted with (host_id, orientation).
            orientation is 'vertical' or 'horizontal'.
    """

    host_picked = Signal(int, str)  # host_id, orientation
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setFixedSize(520, 420)
        self.setObjectName("SplitPickerDialog")

        self.setStyleSheet(
            f"#SplitPickerDialog {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 12px; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("Split Panel \u2014 Select Host")
        title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        # Search input
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search hosts by name, IP, group, tag\u2026")
        self._search.setStyleSheet(
            f"QLineEdit {{ "
            f"  background-color: {Colors.BG_PRIMARY}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 8px; "
            f"  padding: 10px 16px; "
            f"  font-size: 13px; "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"}}"
            f"QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}"
        )
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Orientation selector
        orient_row = QHBoxLayout()
        orient_row.setSpacing(6)

        orient_label = QLabel("Split:")
        orient_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; border: none;"
        )
        orient_row.addWidget(orient_label)

        self._btn_vertical = _OrientButton("\u258e\u258e  Vertical", True)
        self._btn_vertical.clicked.connect(lambda: self._set_orientation("vertical"))
        orient_row.addWidget(self._btn_vertical)

        self._btn_horizontal = _OrientButton("\u2550  Horizontal", False)
        self._btn_horizontal.clicked.connect(lambda: self._set_orientation("horizontal"))
        orient_row.addWidget(self._btn_horizontal)

        orient_row.addStretch()
        layout.addLayout(orient_row)

        self._orientation = "vertical"

        # Results list
        self._results = QListWidget()
        self._results.setStyleSheet(
            f"QListWidget {{ "
            f"  background: transparent; border: none; outline: none; "
            f"}}"
            f"QListWidget::item {{ "
            f"  padding: 0px; border-radius: 6px; "
            f"}}"
            f"QListWidget::item:selected {{ "
            f"  background-color: {Colors.BG_HOVER}; "
            f"}}"
            f"QListWidget::item:hover {{ "
            f"  background-color: {Colors.BG_HOVER}; "
            f"}}"
        )
        self._results.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._results, 1)

        # Hint bar
        hint = QLabel("\u2191\u2193 Navigate    \u21b5 Open    Tab Switch orientation    Esc Close")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"padding: 4px; border: none;"
        )
        layout.addWidget(hint)

        self._hosts: list[dict[str, Any]] = []
        self._groups: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_hosts(
        self,
        hosts: list[dict[str, Any]],
        groups: dict[int, str] | None = None,
    ) -> None:
        """Set searchable hosts.

        Each host dict: {
            'id': int, 'label': str, 'address': str,
            'protocol': str, 'group_id': int | None,
            'tags': list[str], 'color': str | None,
            'last_connected': str | None, 'connect_count': int,
        }
        """
        self._hosts = hosts
        self._groups = groups or {}
        self._on_search("")

    def show_picker(self) -> None:
        """Show the picker centered on parent."""
        if self.parent():
            pr = self.parent().rect()
            x = (pr.width() - self.width()) // 2
            y = max(60, (pr.height() - self.height()) // 3)
            gp = self.parent().mapToGlobal(pr.topLeft())
            self.move(gp.x() + x, gp.y() + y)
        self.show()
        self._search.clear()
        self._search.setFocus()
        self._on_search("")

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.hide()
            self.closed.emit()
            return

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._results.keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current = self._results.currentItem()
            if current:
                self._on_item_activated(current)
            return

        if key == Qt.Key.Key_Tab:
            # Toggle orientation
            if self._orientation == "vertical":
                self._set_orientation("horizontal")
            else:
                self._set_orientation("vertical")
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Search & filtering
    # ------------------------------------------------------------------

    def _on_search(self, query: str) -> None:
        self._results.clear()
        query = query.strip()

        scored: list[tuple[int, dict]] = []
        for host in self._hosts:
            # Build searchable text: label, address, group name, tags
            parts = [host.get("label", ""), host.get("address", "")]
            gid = host.get("group_id")
            group_name = self._groups.get(gid, "") if gid else ""
            parts.append(group_name)
            for tag in host.get("tags", []):
                parts.append(tag)
            searchable = " ".join(parts)

            if not query:
                # No query — sort by recent first, then alphabetically
                score = 1
            else:
                score = _fuzzy_score(query, searchable)

            if score > 0:
                scored.append((score, host))

        # Sort: for empty query, recent connections first then alpha;
        # for non-empty query, by score descending
        if not query:
            scored.sort(
                key=lambda x: (
                    -(x[1].get("connect_count", 0)),
                    (x[1].get("label") or x[1].get("address", "")).lower(),
                )
            )
        else:
            scored.sort(key=lambda x: -x[0])

        for _, host in scored[:_MAX_RESULTS]:
            label = host.get("label") or host.get("address", "")
            address = host.get("address", "")
            gid = host.get("group_id")
            group_name = self._groups.get(gid, "") if gid else ""
            tags_str = ", ".join(host.get("tags", []))
            protocol = host.get("protocol", "ssh")
            color = host.get("color")

            item_widget = _HostResultItem(
                label=label,
                address=address,
                group=group_name,
                tags=tags_str,
                protocol=protocol,
                color=color,
            )

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.ItemDataRole.UserRole, host.get("id"))
            self._results.addItem(list_item)
            self._results.setItemWidget(list_item, item_widget)

        if self._results.count() > 0:
            self._results.setCurrentRow(0)

    def _on_item_activated(self, list_item: QListWidgetItem) -> None:
        host_id = list_item.data(Qt.ItemDataRole.UserRole)
        if host_id is not None:
            self.hide()
            self.host_picked.emit(host_id, self._orientation)

    def _set_orientation(self, orient: str) -> None:
        self._orientation = orient
        self._btn_vertical.set_selected(orient == "vertical")
        self._btn_horizontal.set_selected(orient == "horizontal")


# ---------------------------------------------------------------------------
# _OrientButton — small toggle for vertical / horizontal split
# ---------------------------------------------------------------------------

class _OrientButton(QWidget):
    """Small toggle button for split orientation."""

    clicked = Signal()

    def __init__(self, text: str, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected = selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        self._label = QLabel(text)
        self._label.setStyleSheet(
            f"font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(self._label)

        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"background-color: {Colors.ACCENT}; border-radius: 4px;"
            )
            self._label.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: #ffffff; "
                f"background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(
                f"background-color: {Colors.BG_HOVER}; border-radius: 4px;"
            )
            self._label.setStyleSheet(
                f"font-size: 11px; color: {Colors.TEXT_MUTED}; "
                f"background: transparent; border: none;"
            )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()

    def paintEvent(self, event) -> None:
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(self.style().PrimitiveElement.PE_Widget, opt, p, self)
        p.end()
