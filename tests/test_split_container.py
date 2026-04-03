"""Tests for split container behavior."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from termplus.ui.connections.split_container import SplitContainer
from termplus.ui.connections.terminal_widget import TerminalWidget


class _DummyConnection:
    protocol = "ssh"

    def close(self) -> None:
        pass

    def resize(self, _cols: int, _rows: int) -> None:
        pass

    def send(self, _data: bytes) -> None:
        pass


def _line_text(term: TerminalWidget, width: int) -> str:
    line = term._screen.buffer[0]
    return "".join(line[c].data for c in range(width))


def test_split_header_has_visible_close_button(qtbot):
    term = TerminalWidget(cols=80, rows=24)
    container = SplitContainer(term, _DummyConnection(), 1, "host")
    qtbot.addWidget(container)

    panel = container.panels[0]
    buttons = panel.findChildren(QPushButton)
    assert any(btn.text() == "x" for btn in buttons)


def test_split_remove_emits_panel_removed(qtbot):
    term = TerminalWidget(cols=80, rows=24)
    container = SplitContainer(term, _DummyConnection(), 1, "host")
    qtbot.addWidget(container)

    new_term = TerminalWidget(cols=80, rows=24)
    panel = container.split(Qt.Orientation.Horizontal, new_term, _DummyConnection(), 1, "host2")
    assert panel is not None

    removed: list[str] = []
    container.panel_removed.connect(removed.append)
    container.remove_panel(panel.panel_id)

    assert removed == [panel.panel_id]


def test_existing_terminal_buffer_not_cleared_by_split(qtbot):
    term = TerminalWidget(cols=80, rows=24)
    term.feed(b"hello")
    container = SplitContainer(term, _DummyConnection(), 1, "host")
    qtbot.addWidget(container)

    new_term = TerminalWidget(cols=80, rows=24)
    panel = container.split(Qt.Orientation.Horizontal, new_term, _DummyConnection(), 1, "host2")
    assert panel is not None

    assert _line_text(term, 5) == "hello"


def test_hidden_terminal_is_shown_after_reparent_to_split(qtbot):
    term = TerminalWidget(cols=80, rows=24)
    term.hide()

    container = SplitContainer(term, _DummyConnection(), 1, "host")
    qtbot.addWidget(container)
    container.show()
    qtbot.wait(10)

    assert term.isVisible()
