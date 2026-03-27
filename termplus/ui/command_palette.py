"""Command Palette — Ctrl+K fuzzy-search overlay for hosts and actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from termplus.app.constants import Colors

logger = logging.getLogger(__name__)


@dataclass
class PaletteItem:
    """A searchable item in the palette."""

    title: str
    subtitle: str = ""
    category: str = ""
    action: Callable | None = None
    data: object = None


def fuzzy_score(query: str, text: str) -> int:
    """Simple fuzzy match: returns score (higher = better), 0 = no match."""
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
            # Bonus for consecutive matches
            if prev_match == ti - 1:
                score += 5
            # Bonus for start of word
            if ti == 0 or text_lower[ti - 1] in " _-.@/":
                score += 3
            prev_match = ti
            qi += 1

    return score if qi == len(query_lower) else 0


class CommandPalette(QWidget):
    """Overlay command palette with fuzzy search."""

    item_activated = Signal(object)  # PaletteItem
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setFixedSize(600, 400)

        self.setStyleSheet(
            f"CommandPalette {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 12px; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(8)

        # Search input
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search hosts, actions…")
        self._search.setStyleSheet(
            f"QLineEdit {{ "
            f"  background-color: {Colors.BG_PRIMARY}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 8px; "
            f"  padding: 10px 16px; "
            f"  font-size: 14px; "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"}}"
            f"QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}"
        )
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Results list
        self._results = QListWidget()
        self._results.setStyleSheet(
            f"QListWidget {{ "
            f"  background: transparent; border: none; outline: none; "
            f"}}"
            f"QListWidget::item {{ "
            f"  padding: 8px 12px; border-radius: 6px; "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"}}"
            f"QListWidget::item:selected {{ "
            f"  background-color: {Colors.BG_HOVER}; "
            f"}}"
            f"QListWidget::item:hover {{ "
            f"  background-color: {Colors.BG_HOVER}; "
            f"}}"
        )
        self._results.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._results)

        # Hint
        hint = QLabel("↑↓ Navigate  ↵ Open  Esc Close")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"padding: 4px;"
        )
        layout.addWidget(hint)

        self._items: list[PaletteItem] = []

    def set_items(self, items: list[PaletteItem]) -> None:
        """Set the full list of searchable items."""
        self._items = items
        self._on_search("")

    def show_palette(self) -> None:
        """Show the palette centered on parent."""
        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = max(80, (parent_rect.height() - self.height()) // 3)
            self.move(self.parent().mapToGlobal(self.parent().rect().topLeft()).x() + x,
                      self.parent().mapToGlobal(self.parent().rect().topLeft()).y() + y)
        self.show()
        self._search.clear()
        self._search.setFocus()
        self._on_search("")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.closed.emit()
            return

        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            # Forward to list
            self._results.keyPressEvent(event)
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current = self._results.currentItem()
            if current:
                self._on_item_activated(current)
            return

        super().keyPressEvent(event)

    def _on_search(self, query: str) -> None:
        self._results.clear()

        if not query:
            scored = [(item, 1) for item in self._items]
        else:
            scored = []
            for item in self._items:
                s = fuzzy_score(query, item.title)
                if s == 0 and item.subtitle:
                    s = fuzzy_score(query, item.subtitle) // 2
                if s > 0:
                    scored.append((item, s))

        scored.sort(key=lambda x: -x[1])

        for item, _ in scored[:20]:
            display = item.title
            if item.subtitle:
                display += f"  —  {item.subtitle}"
            if item.category:
                display = f"[{item.category}]  {display}"

            list_item = QListWidgetItem(display)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self._results.addItem(list_item)

        if self._results.count() > 0:
            self._results.setCurrentRow(0)

    def _on_item_activated(self, list_item: QListWidgetItem) -> None:
        item: PaletteItem = list_item.data(Qt.ItemDataRole.UserRole)
        if item:
            self.hide()
            if item.action:
                item.action()
            self.item_activated.emit(item)
