"""Fuzzy search input with dropdown results."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors


def fuzzy_match(query: str, text: str) -> int:
    """Simple fuzzy matching — returns score (0 = no match).

    Characters of query must appear in order in text.
    Higher score = better match.
    """
    if not query:
        return 1  # empty query matches everything
    query_lower = query.lower()
    text_lower = text.lower()
    qi = 0
    score = 0
    last_match = -1
    for ti, ch in enumerate(text_lower):
        if qi < len(query_lower) and ch == query_lower[qi]:
            # Bonus for consecutive matches
            if ti == last_match + 1:
                score += 3
            # Bonus for start of word
            elif ti == 0 or text_lower[ti - 1] in " -_./":
                score += 2
            else:
                score += 1
            last_match = ti
            qi += 1
    if qi < len(query_lower):
        return 0  # not all chars matched
    return score


class FuzzySearchWidget(QWidget):
    """Search input with fuzzy-filtered dropdown results.

    Items are set via set_items(). Each item is a dict with at least
    'label' and 'data' keys.
    """

    result_selected = Signal(object)  # emits item data

    def __init__(
        self,
        placeholder: str = "Search…",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Search input
        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setProperty("cssClass", "search")
        layout.addWidget(self._input)

        # Results list (initially hidden)
        self._results = QListWidget()
        self._results.setVisible(False)
        self._results.setMaximumHeight(250)
        self._results.setStyleSheet(
            f"QListWidget {{ "
            f"  background-color: {Colors.BG_SURFACE}; "
            f"  border: 1px solid {Colors.BORDER}; border-radius: 8px; "
            f"}}"
        )
        layout.addWidget(self._results)

        # Debounce timer
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._do_search)

        self._input.textChanged.connect(lambda: self._debounce.start())
        self._results.itemClicked.connect(self._on_item_clicked)
        self._input.returnPressed.connect(self._on_return)

    def set_items(self, items: list[dict[str, Any]]) -> None:
        """Set searchable items: [{'label': str, 'data': Any, ...}]."""
        self._items = items

    def clear_input(self) -> None:
        self._input.clear()

    def _do_search(self) -> None:
        query = self._input.text().strip()
        self._results.clear()

        if not query:
            self._results.setVisible(False)
            return

        scored = []
        for item in self._items:
            score = fuzzy_match(query, item["label"])
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)

        for score, item in scored[:20]:
            list_item = QListWidgetItem(item["label"])
            list_item.setData(Qt.ItemDataRole.UserRole, item["data"])
            self._results.addItem(list_item)

        self._results.setVisible(self._results.count() > 0)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        self.result_selected.emit(data)
        self._input.clear()
        self._results.setVisible(False)

    def _on_return(self) -> None:
        if self._results.count() > 0:
            self._results.setCurrentRow(0)
            item = self._results.currentItem()
            if item:
                self._on_item_clicked(item)
