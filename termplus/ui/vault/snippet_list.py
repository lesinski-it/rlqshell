"""Snippet list view with search, packages, and CRUD."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
from termplus.core.models.snippet import Snippet, SnippetPackage
from termplus.core.snippet_manager import SnippetManager
from termplus.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


class _SnippetItem(QWidget):
    """Single snippet row in the list."""

    clicked = Signal(int)  # snippet_id
    context_menu_requested = Signal(int, object)  # snippet_id, QPoint

    def __init__(self, snippet: Snippet, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snippet_id = snippet.id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"_SnippetItem {{ background: transparent; border-radius: 6px; }}"
            f"_SnippetItem:hover {{ background-color: {Colors.BG_SURFACE}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # Name
        name = QLabel(snippet.name or "Unnamed")
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        layout.addWidget(name)

        # Script preview (truncated)
        preview = snippet.script[:80].replace("\n", " ") if snippet.script else "—"
        script_label = QLabel(preview)
        script_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"font-family: monospace;"
        )
        layout.addWidget(script_label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._snippet_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(
                self._snippet_id, event.globalPosition().toPoint()
            )


class SnippetListView(QWidget):
    """Full snippet list with toolbar, package filter, and search."""

    snippet_selected = Signal(int)  # snippet_id
    snippet_run_requested = Signal(str)  # script content

    def __init__(
        self,
        snippet_manager: SnippetManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = snippet_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 8, 16, 8)
        tb.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search snippets…")
        self._search.setProperty("cssClass", "search")
        tb.addWidget(self._search, 1)

        self._package_filter = QComboBox()
        self._package_filter.setFixedWidth(140)
        tb.addWidget(self._package_filter)

        add_btn = QPushButton("+ New")
        add_btn.setProperty("cssClass", "primary")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_new_snippet)
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)

        # Content scroll
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
        self._empty = EmptyState(
            title="No snippets yet",
            description="Create a snippet to save frequently used commands.",
            action_text="+ New Snippet",
        )
        self._empty.action_clicked.connect(self._on_new_snippet)
        self._empty.setVisible(False)
        self._content_layout.addWidget(self._empty)

        # Debounced search
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda: self._debounce.start())
        self._package_filter.currentIndexChanged.connect(lambda: self.refresh())

        self._refresh_packages()
        self.refresh()

    def _refresh_packages(self) -> None:
        self._package_filter.blockSignals(True)
        self._package_filter.clear()
        self._package_filter.addItem("All packages", None)
        for pkg in self._manager.list_packages():
            self._package_filter.addItem(pkg.name, pkg.id)
        self._package_filter.blockSignals(False)

    def refresh(self) -> None:
        """Rebuild the snippet list."""
        for i in reversed(range(self._content_layout.count())):
            w = self._content_layout.itemAt(i).widget()
            if w and w is not self._empty:
                w.deleteLater()

        search = self._search.text().strip() or None
        pkg_id = self._package_filter.currentData()

        snippets = self._manager.list_snippets(package_id=pkg_id, search=search)

        if not snippets and not search:
            self._empty.setVisible(True)
            return

        self._empty.setVisible(False)

        for s in snippets:
            item = _SnippetItem(s)
            item.clicked.connect(self.snippet_selected.emit)
            item.context_menu_requested.connect(self._on_context_menu)
            self._content_layout.addWidget(item)

    def _on_new_snippet(self) -> None:
        from termplus.ui.vault.snippet_editor import SnippetEditor

        editor = SnippetEditor(self._manager, parent=self)
        if editor.exec() == SnippetEditor.DialogCode.Accepted:
            self._refresh_packages()
            self.refresh()

    def _on_context_menu(self, snippet_id: int, pos) -> None:
        menu = QMenu(self)
        run_action = menu.addAction("Run in Terminal")
        edit_action = menu.addAction("Edit")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(pos)
        if action == run_action:
            snippet = self._manager.get_snippet(snippet_id)
            if snippet:
                script = snippet.script
                if snippet.run_as_sudo and not script.lstrip().startswith("sudo "):
                    script = f"sudo {script}"
                self.snippet_run_requested.emit(script)
        elif action == edit_action:
            self._edit_snippet(snippet_id)
        elif action == delete_action:
            self._manager.delete_snippet(snippet_id)
            self.refresh()

    def _edit_snippet(self, snippet_id: int) -> None:
        from termplus.ui.vault.snippet_editor import SnippetEditor

        editor = SnippetEditor(self._manager, snippet_id=snippet_id, parent=self)
        if editor.exec() == SnippetEditor.DialogCode.Accepted:
            self._refresh_packages()
            self.refresh()
