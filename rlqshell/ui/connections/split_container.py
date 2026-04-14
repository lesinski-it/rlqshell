"""Split view container — manages multiple terminal panels within a single tab."""

from __future__ import annotations

import logging
import uuid
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors
from rlqshell.protocols.base import AbstractConnection
from rlqshell.ui.connections.terminal_widget import TerminalWidget

logger = logging.getLogger(__name__)

_MAX_PANELS = 4


# ---------------------------------------------------------------------------
# _BroadcastBar — thin banner shown when broadcast mode is active
# ---------------------------------------------------------------------------

class _BroadcastBar(QWidget):
    """Banner indicating broadcast mode is active."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BroadcastBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)

        lbl = QLabel("\u25cf  BROADCAST MODE \u2014 input is sent to all panels")
        layout.addWidget(lbl)
        layout.addStretch()

        self.setVisible(False)


# ---------------------------------------------------------------------------
# _PanelHeader — compact bar at the top of each split panel
# ---------------------------------------------------------------------------

class _PanelHeader(QWidget):
    """Thin header bar for a split panel showing host label and close button."""

    close_requested = Signal(str)  # panel_id

    def __init__(self, panel_id: str, host_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panel_id = panel_id
        self.setFixedHeight(22)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        self._label = QLabel(host_label)
        self._label.setStyleSheet("font-size:11px; background:transparent;")

        # Apply default (unfocused) style
        self.set_focused(False)
        layout.addWidget(self._label)

        self._broadcast_icon = QLabel("\u25cf")
        self._broadcast_icon.setStyleSheet(
            f"color:{Colors.WARNING}; font-size:10px; background:transparent;"
        )
        self._broadcast_icon.setToolTip("Broadcast active")
        self._broadcast_icon.setVisible(False)
        layout.addWidget(self._broadcast_icon)

        layout.addStretch()

        self._close_btn = QPushButton("x")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Close panel")
        self._close_btn.setStyleSheet(
            f"QPushButton {{"
            f" color:{Colors.TEXT_PRIMARY};"
            f" background:{Colors.BG_PRIMARY};"
            f" border:1px solid {Colors.BORDER};"
            f" border-radius:4px;"
            f" font-size:12px;"
            f" font-weight:700;"
            f" padding:0px;"
            f" }}"
            f"QPushButton:hover {{"
            f" color:#ffffff;"
            f" background:{Colors.DANGER};"
            f" border-color:{Colors.DANGER};"
            f" }}"
        )
        self._close_btn.clicked.connect(lambda: self.close_requested.emit(self._panel_id))
        layout.addWidget(self._close_btn)

    def set_focused(self, focused: bool) -> None:
        if focused:
            bg = Colors.ACCENT
            text_color = "#ffffff"
            border_color = Colors.ACCENT
        else:
            bg = Colors.BG_SURFACE
            text_color = Colors.TEXT_SECONDARY
            border_color = Colors.BORDER
        self.setStyleSheet(
            f"background:{bg}; border-bottom:1px solid {border_color};"
        )
        self._label.setStyleSheet(
            f"color:{text_color}; font-size:11px; background:transparent;"
        )

    def set_broadcast_indicator(self, visible: bool) -> None:
        self._broadcast_icon.setVisible(visible)


# ---------------------------------------------------------------------------
# SplitPanel — one terminal panel inside the split view
# ---------------------------------------------------------------------------

class SplitPanel(QWidget):
    """Wrapper around a single terminal + connection inside a split container."""

    close_requested = Signal(str)  # panel_id
    focus_gained = Signal(str)  # panel_id

    def __init__(
        self,
        panel_id: str,
        terminal: TerminalWidget,
        connection: AbstractConnection | None,
        host_id: int | None,
        host_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._panel_id = panel_id
        self._terminal = terminal
        self._connection = connection
        self._host_id = host_id
        self._host_label = host_label

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = _PanelHeader(panel_id, host_label)
        self._header.close_requested.connect(self.close_requested)
        layout.addWidget(self._header)

        layout.addWidget(terminal, 1)
        # Terminal can be hidden by previous parent (e.g. QStackedWidget.removeWidget).
        # Make sure it is visible after reparenting into split panel.
        terminal.show()

        terminal.focus_gained.connect(lambda: self.focus_gained.emit(self._panel_id))

        # Default: unfocused border
        self._set_border(Colors.BORDER)

    # -- Properties --

    @property
    def panel_id(self) -> str:
        return self._panel_id

    @property
    def terminal(self) -> TerminalWidget:
        return self._terminal

    @property
    def connection(self) -> AbstractConnection | None:
        return self._connection

    @property
    def host_id(self) -> int | None:
        return self._host_id

    @property
    def host_label(self) -> str:
        return self._host_label

    # -- Visual state --

    def set_focused(self, focused: bool) -> None:
        color = Colors.ACCENT if focused else Colors.BORDER
        self._set_border(color)
        self._header.set_focused(focused)

    def set_broadcast_indicator(self, visible: bool) -> None:
        self._header.set_broadcast_indicator(visible)

    def _set_border(self, color: str) -> None:
        self.setStyleSheet(
            f"SplitPanel {{ border: 1px solid {color}; }}"
        )


# ---------------------------------------------------------------------------
# SplitContainer — top-level widget managing split panels via QSplitter
# ---------------------------------------------------------------------------

class SplitContainer(QWidget):
    """Container managing multiple split terminal panels within one tab."""

    all_panels_closed = Signal()
    single_panel_remaining = Signal(object)  # the surviving SplitPanel
    broadcast_toggled = Signal(bool)
    panel_removed = Signal(str)  # panel_id

    def __init__(
        self,
        terminal: TerminalWidget,
        connection: AbstractConnection | None,
        host_id: int | None,
        host_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._panels: list[SplitPanel] = []
        self._focused_panel: SplitPanel | None = None
        self._broadcast = False
        self._broadcast_slots: list[tuple[TerminalWidget, object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._broadcast_bar = _BroadcastBar()
        layout.addWidget(self._broadcast_bar)

        self._root_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._root_splitter.setHandleWidth(2)
        self._root_splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Colors.BORDER}; }}"
        )
        layout.addWidget(self._root_splitter, 1)

        # Wrap the initial terminal in a SplitPanel
        panel = self._create_panel(terminal, connection, host_id, host_label)
        self._root_splitter.addWidget(panel)
        self._focused_panel = panel
        panel.set_focused(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def broadcast_mode(self) -> bool:
        return self._broadcast

    @property
    def panels(self) -> list[SplitPanel]:
        return list(self._panels)

    @property
    def focused_panel(self) -> SplitPanel | None:
        return self._focused_panel

    def split(
        self,
        orientation: Qt.Orientation,
        terminal: TerminalWidget,
        connection: AbstractConnection | None,
        host_id: int | None,
        host_label: str,
        insert_before: bool = False,
    ) -> SplitPanel | None:
        """Split the focused panel. Returns the new panel, or None if limit reached.

        If *insert_before* is True the new panel is placed before (left/top of)
        the focused panel instead of after (right/bottom of) it.
        """
        if len(self._panels) >= _MAX_PANELS:
            logger.warning("Split limit reached (%d panels)", _MAX_PANELS)
            return None

        if self._focused_panel is None:
            return None

        new_panel = self._create_panel(terminal, connection, host_id, host_label)

        # Find the splitter that directly contains the focused panel
        focused = self._focused_panel
        parent_splitter = focused.parent()

        if not isinstance(parent_splitter, QSplitter):
            # Should not happen, but guard
            self._root_splitter.addWidget(new_panel)
            self._root_splitter.setSizes([1] * self._root_splitter.count())
            return new_panel

        idx = parent_splitter.indexOf(focused)

        if parent_splitter.orientation() == orientation:
            # Same orientation — insert before or after the focused panel
            ins = idx if insert_before else idx + 1
            parent_splitter.insertWidget(ins, new_panel)
            parent_splitter.setSizes([1] * parent_splitter.count())
        else:
            # Different orientation — create a child splitter
            child_splitter = QSplitter(orientation)
            child_splitter.setHandleWidth(2)
            child_splitter.setStyleSheet(
                f"QSplitter::handle {{ background: {Colors.BORDER}; }}"
            )
            # Replace focused panel with the child splitter
            parent_splitter.insertWidget(idx, child_splitter)
            if insert_before:
                child_splitter.addWidget(new_panel)
                child_splitter.addWidget(focused)
            else:
                child_splitter.addWidget(focused)
                child_splitter.addWidget(new_panel)
            child_splitter.setSizes([1, 1])
            parent_splitter.setSizes([1] * parent_splitter.count())

        # If broadcast is active, wire the new panel too
        if self._broadcast:
            self._connect_broadcast_for_panel(new_panel)
            new_panel.set_broadcast_indicator(True)

        return new_panel

    def remove_panel(self, panel_id: str) -> None:
        """Close and remove a panel from the split view."""
        panel = self._find_panel(panel_id)
        if panel is None:
            return

        # Disconnect broadcast if active
        if self._broadcast:
            self._disconnect_broadcast_for_panel(panel)

        # Close connection
        if panel.connection is not None:
            panel.connection.close()

        # Remove from tracking
        self._panels.remove(panel)
        self.panel_removed.emit(panel_id)

        # Remove from splitter tree
        parent_splitter = panel.parent()
        panel.setParent(None)
        panel.deleteLater()

        # Simplify splitter tree
        if isinstance(parent_splitter, QSplitter):
            self._simplify_splitter(parent_splitter)

        # Update focus
        if self._focused_panel is panel or self._focused_panel is None:
            if self._panels:
                self._focused_panel = self._panels[0]
                self._focused_panel.set_focused(True)
                self._focused_panel.terminal.setFocus()
            else:
                self._focused_panel = None

        if not self._panels:
            self.all_panels_closed.emit()
        elif len(self._panels) == 1:
            # Auto-disable broadcast — no point with a single panel
            if self._broadcast:
                self.set_broadcast(False)
            self.single_panel_remaining.emit(self._panels[0])

    def set_broadcast(self, enabled: bool) -> None:
        """Toggle broadcast mode."""
        if self._broadcast == enabled:
            return
        self._broadcast = enabled

        if enabled:
            for panel in self._panels:
                self._connect_broadcast_for_panel(panel)
                panel.set_broadcast_indicator(True)
        else:
            self._disconnect_all_broadcast()
            for panel in self._panels:
                panel.set_broadcast_indicator(False)

        self._broadcast_bar.setVisible(enabled)
        self.broadcast_toggled.emit(enabled)

    # -- Proxy API (so ConnectionsPage can treat us like a TerminalWidget) --

    def show_overlay(
        self,
        text: str,
        color: str | None = None,
        show_reconnect: bool = False,
    ) -> None:
        for panel in self._panels:
            panel.terminal.show_overlay(text, color, show_reconnect=show_reconnect)

    def clear_overlay(self) -> None:
        for panel in self._panels:
            panel.terminal.clear_overlay()

    def setFocus(self) -> None:
        if self._focused_panel is not None:
            self._focused_panel.terminal.setFocus()
        elif self._panels:
            self._panels[0].terminal.setFocus()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _create_panel(
        self,
        terminal: TerminalWidget,
        connection: AbstractConnection | None,
        host_id: int | None,
        host_label: str,
    ) -> SplitPanel:
        panel_id = str(uuid.uuid4())[:8]
        panel = SplitPanel(panel_id, terminal, connection, host_id, host_label)
        panel.close_requested.connect(self.remove_panel)
        panel.focus_gained.connect(self._on_panel_focus)
        self._panels.append(panel)
        return panel

    def _find_panel(self, panel_id: str) -> SplitPanel | None:
        for p in self._panels:
            if p.panel_id == panel_id:
                return p
        return None

    def _on_panel_focus(self, panel_id: str) -> None:
        panel = self._find_panel(panel_id)
        if panel is None or panel is self._focused_panel:
            return
        if self._focused_panel is not None:
            self._focused_panel.set_focused(False)
        self._focused_panel = panel
        panel.set_focused(True)

    # -- Broadcast wiring --

    def _connect_broadcast_for_panel(self, panel: SplitPanel) -> None:
        slot = partial(self._broadcast_input, panel)
        panel.terminal.input_ready.connect(slot)
        self._broadcast_slots.append((panel.terminal, slot))

    def _disconnect_broadcast_for_panel(self, panel: SplitPanel) -> None:
        remaining: list[tuple[TerminalWidget, object]] = []
        for terminal, slot in self._broadcast_slots:
            if terminal is panel.terminal:
                try:
                    terminal.input_ready.disconnect(slot)
                except RuntimeError:
                    pass
            else:
                remaining.append((terminal, slot))
        self._broadcast_slots = remaining

    def _disconnect_all_broadcast(self) -> None:
        for terminal, slot in self._broadcast_slots:
            try:
                terminal.input_ready.disconnect(slot)
            except RuntimeError:
                pass
        self._broadcast_slots.clear()

    def _broadcast_input(self, source_panel: SplitPanel, data: bytes) -> None:
        """Forward input from source_panel to all OTHER panels' connections."""
        for panel in self._panels:
            if panel is not source_panel and panel.connection is not None:
                try:
                    panel.connection.send(data)
                except Exception:
                    logger.debug("Broadcast send failed for panel %s", panel.panel_id)

    # -- Splitter tree simplification --

    def _simplify_splitter(self, splitter: QSplitter) -> None:
        """Collapse unnecessary nesting in the splitter tree."""
        if splitter is self._root_splitter:
            # Root splitter with one child that is itself a splitter → promote children
            if splitter.count() == 1:
                child = splitter.widget(0)
                if isinstance(child, QSplitter):
                    # Collect all grandchildren by index (widget(0) doesn't remove)
                    orientation = child.orientation()
                    widgets = [child.widget(i) for i in range(child.count())]
                    self._root_splitter.setOrientation(orientation)
                    # addWidget() reparents each widget from child → root
                    for w in widgets:
                        self._root_splitter.addWidget(w)
                    child.deleteLater()
                    self._root_splitter.setSizes([1] * self._root_splitter.count())
            return

        # Non-root splitter with 0 or 1 children — promote up
        parent = splitter.parent()
        if not isinstance(parent, QSplitter):
            return

        if splitter.count() == 0:
            splitter.setParent(None)
            splitter.deleteLater()
        elif splitter.count() == 1:
            child = splitter.widget(0)
            idx = parent.indexOf(splitter)
            parent.insertWidget(idx, child)
            splitter.setParent(None)
            splitter.deleteLater()
            parent.setSizes([1] * parent.count())
