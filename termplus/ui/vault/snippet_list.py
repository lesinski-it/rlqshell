"""Snippet list view with search, packages, drag-and-drop reorder, and CRUD."""

from __future__ import annotations

import logging

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor
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
from termplus.core.snippet_variables import extract_variables, resolve_variables
from termplus.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)

_DRAG_MIME = "application/x-termplus-snippet-id"


class _SnippetItem(QWidget):
    """Single snippet row in the list."""

    clicked = Signal(int)  # snippet_id
    context_menu_requested = Signal(int, object)  # snippet_id, QPoint

    def __init__(self, snippet: Snippet, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snippet_id = snippet.id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"_SnippetItem {{ background: transparent; border-radius: 6px; }}"
            f"_SnippetItem:hover {{ background-color: {Colors.BG_SURFACE}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Drag handle
        handle = QLabel("\u2261")
        handle.setFixedWidth(16)
        handle.setStyleSheet(
            f"font-size: 18px; color: {Colors.TEXT_MUTED}; background: transparent;"
        )
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(handle)

        # Color indicator
        color = snippet.color_label or "#6c757d"
        indicator = QWidget()
        indicator.setFixedSize(4, 40)
        indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 2px;"
        )
        layout.addWidget(indicator)

        # Text area
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        # Name row
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)

        name = QLabel(snippet.name or "Unnamed")
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent;"
        )
        name_row.addWidget(name)

        # Tags
        if snippet.tags:
            for tag in snippet.tags[:3]:
                pill = QLabel(tag)
                pill.setStyleSheet(
                    f"font-size: 10px; color: {Colors.TEXT_MUTED}; "
                    f"background-color: {Colors.BG_SURFACE}; "
                    f"border: 1px solid {Colors.BORDER}; border-radius: 8px; "
                    f"padding: 1px 6px;"
                )
                name_row.addWidget(pill)
            if len(snippet.tags) > 3:
                more = QLabel(f"+{len(snippet.tags) - 3}")
                more.setStyleSheet(
                    f"font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent;"
                )
                name_row.addWidget(more)

        name_row.addStretch()
        text_col.addLayout(name_row)

        # Script preview (truncated)
        preview = snippet.script[:80].replace("\n", " ") if snippet.script else "\u2014"
        script_label = QLabel(preview)
        script_label.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; "
            f"font-family: monospace;"
        )
        text_col.addWidget(script_label)

        layout.addLayout(text_col, 1)

        # Drag state
        self._drag_start: QPoint | None = None

    @property
    def snippet_id(self) -> int:
        return self._snippet_id

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_menu_requested.emit(
                self._snippet_id, event.globalPosition().toPoint()
            )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None:
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
            return
        # Start drag
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_DRAG_MIME, str(self._snippet_id).encode())
        drag.setMimeData(mime)

        # Semi-transparent pixmap of this widget
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
            self.clicked.emit(self._snippet_id)


class _DropIndicator(QWidget):
    """Thin horizontal line shown between items during drag."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet(f"background-color: {Colors.ACCENT}; border-radius: 1px;")
        self.hide()


class SnippetListView(QWidget):
    """Full snippet list with toolbar, package filter, and search."""

    snippet_selected = Signal(int)  # snippet_id
    snippet_run_requested = Signal(str)  # script content
    snippet_broadcast_requested = Signal(str)  # script content

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
        self._search.setPlaceholderText("Search snippets\u2026")
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

    # --- Drag & drop helpers ---

    def _snippet_items(self) -> list[_SnippetItem]:
        """Return all _SnippetItem widgets in layout order."""
        items: list[_SnippetItem] = []
        for i in range(self._content_layout.count()):
            w = self._content_layout.itemAt(i).widget()
            if isinstance(w, _SnippetItem):
                items.append(w)
        return items

    def _target_index(self, pos: QPoint) -> int:
        """Return the index of the item under (or nearest to) the cursor."""
        items = self._snippet_items()
        if not items:
            return 0
        for idx, item in enumerate(items):
            if item.y() <= pos.y() < item.y() + item.height():
                return idx
        # Cursor outside all items — clamp to nearest end
        if pos.y() < items[0].y():
            return 0
        return len(items) - 1

    def _clear_highlights(self) -> None:
        for item in self._snippet_items():
            item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            item.setStyleSheet(
                f"background: transparent; border-radius: 6px;"
            )

    def _highlight_at(self, idx: int) -> None:
        self._clear_highlights()
        items = self._snippet_items()
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
        if not self._snippet_items():
            return
        self._highlight_at(self._target_index(event.position().toPoint()))

    def _on_drag_leave(self, event) -> None:
        self._clear_highlights()

    def _on_drop(self, event) -> None:
        self._clear_highlights()
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()

        dragged_id = int(event.mimeData().data(_DRAG_MIME).data().decode())
        target_idx = self._target_index(event.position().toPoint())

        # Build new order
        items = self._snippet_items()
        ordered_ids = [it.snippet_id for it in items]

        if dragged_id not in ordered_ids:
            return

        old_idx = ordered_ids.index(dragged_id)
        if old_idx == target_idx:
            return

        ordered_ids.pop(old_idx)
        ordered_ids.insert(target_idx, dragged_id)

        self._manager.reorder_snippets(ordered_ids)
        self.refresh()

    # --- Regular methods ---

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

    def _resolve_script(self, snippet: Snippet) -> str | None:
        """Apply sudo prefix, resolve variables, show confirmation.

        Returns the final script string, or ``None`` if the user cancelled.
        """
        script = snippet.script
        if snippet.run_as_sudo and not script.lstrip().startswith("sudo "):
            script = f"sudo {script}"

        # Variables
        variables = extract_variables(script)
        if variables:
            from termplus.ui.dialogs.snippet_variable_dialog import SnippetVariableDialog

            dlg = SnippetVariableDialog(variables, parent=self)
            if dlg.exec() != SnippetVariableDialog.DialogCode.Accepted:
                return None
            script = resolve_variables(script, dlg.values)

        # Confirmation
        from termplus.ui.dialogs.snippet_confirm_dialog import SnippetConfirmDialog

        confirm = SnippetConfirmDialog(snippet.name, script, parent=self)
        if confirm.exec() != SnippetConfirmDialog.DialogCode.Accepted:
            return None

        return script

    def _on_context_menu(self, snippet_id: int, pos) -> None:
        menu = QMenu(self)
        run_action = menu.addAction("Run in Terminal")
        broadcast_action = menu.addAction("Run on Multiple Terminals\u2026")
        menu.addSeparator()
        edit_action = menu.addAction("Edit")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(pos)
        if action == run_action:
            snippet = self._manager.get_snippet(snippet_id)
            if snippet:
                script = self._resolve_script(snippet)
                if script is not None:
                    self.snippet_run_requested.emit(script)
        elif action == broadcast_action:
            snippet = self._manager.get_snippet(snippet_id)
            if snippet:
                script = self._resolve_script(snippet)
                if script is not None:
                    self.snippet_broadcast_requested.emit(script)
        elif action == edit_action:
            self._edit_snippet(snippet_id)
        elif action == duplicate_action:
            self._manager.duplicate_snippet(snippet_id)
            self.refresh()
        elif action == delete_action:
            self._manager.delete_snippet(snippet_id)
            self.refresh()

    def _edit_snippet(self, snippet_id: int) -> None:
        from termplus.ui.vault.snippet_editor import SnippetEditor

        editor = SnippetEditor(self._manager, snippet_id=snippet_id, parent=self)
        if editor.exec() == SnippetEditor.DialogCode.Accepted:
            self._refresh_packages()
            self.refresh()
