"""Tests for terminal widget and SSH connection."""

from __future__ import annotations

import pytest

from termplus.protocols.ssh.connection import SSHConnection


# === TerminalWidget (requires QApplication) ===

@pytest.fixture
def terminal(qtbot):
    """Create a TerminalWidget for testing."""
    from termplus.ui.connections.terminal_widget import TerminalWidget

    widget = TerminalWidget(cols=80, rows=24)
    qtbot.addWidget(widget)
    return widget


def test_terminal_initial_size(terminal):
    assert terminal._cols == 80
    assert terminal._rows == 24


def test_terminal_feed_text(terminal):
    terminal.feed(b"Hello, Termplus!")
    # Text should be in the pyte screen buffer
    line = terminal._screen.buffer[0]
    text = "".join(line[c].data for c in range(16))
    assert text == "Hello, Termplus!"


def test_terminal_feed_ansi_colors(terminal):
    # Red text
    terminal.feed(b"\x1b[31mRED\x1b[0m")
    char = terminal._screen.buffer[0][0]
    assert char.data == "R"
    assert char.fg == "red"


def test_terminal_cursor_position(terminal):
    terminal.feed(b"AB")
    assert terminal._screen.cursor.x == 2
    assert terminal._screen.cursor.y == 0


def test_terminal_newlines(terminal):
    terminal.feed(b"Line1\r\nLine2")
    line0 = "".join(terminal._screen.buffer[0][c].data for c in range(5))
    line1 = "".join(terminal._screen.buffer[1][c].data for c in range(5))
    assert line0 == "Line1"
    assert line1 == "Line2"


def test_terminal_resize(terminal):
    # Simulate resize by changing widget size metrics
    terminal._cols = 40
    terminal._rows = 10
    terminal._screen.resize(10, 40)
    assert terminal._cols == 40
    assert terminal._rows == 10


def test_terminal_input_signal(terminal, qtbot):
    """Check that keypress emits input_ready signal."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    signals = []
    terminal.input_ready.connect(signals.append)

    # Simulate pressing 'a'
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"
    )
    terminal.keyPressEvent(event)

    assert len(signals) == 1
    assert signals[0] == b"a"


def test_terminal_arrow_keys(terminal, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    signals = []
    terminal.input_ready.connect(signals.append)

    for key, expected in [
        (Qt.Key.Key_Up, b"\x1b[A"),
        (Qt.Key.Key_Down, b"\x1b[B"),
        (Qt.Key.Key_Right, b"\x1b[C"),
        (Qt.Key.Key_Left, b"\x1b[D"),
    ]:
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, ""
        )
        terminal.keyPressEvent(event)

    assert signals == [b"\x1b[A", b"\x1b[B", b"\x1b[C", b"\x1b[D"]


def test_terminal_ctrl_c(terminal, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    signals = []
    terminal.input_ready.connect(signals.append)

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier, "",
    )
    terminal.keyPressEvent(event)

    assert signals == [b"\x03"]


def test_terminal_font_zoom_shortcuts(terminal):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    initial = terminal._font.pointSize()

    zoom_in = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Equal,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "+",
    )
    terminal.keyPressEvent(zoom_in)
    assert terminal._font.pointSize() == initial + 1

    zoom_out = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Minus,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "-",
    )
    terminal.keyPressEvent(zoom_out)
    assert terminal._font.pointSize() == initial


def test_terminal_scrollbar_works_with_history(terminal):
    # generate enough output to fill scrollback above visible rows
    payload = b"".join(f"line{i}\r\n".encode("utf-8") for i in range(60))
    terminal.feed(payload)

    assert terminal._v_scrollbar.maximum() > 0
    assert terminal._v_scrollbar.isEnabled()

    # top of scrollbar should map to maximum scroll offset
    terminal._v_scrollbar.setValue(0)
    assert terminal._scroll_offset == terminal._v_scrollbar.maximum()


def test_terminal_zoom_keeps_scroll_position(terminal):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    payload = b"".join(f"line{i}\r\n".encode("utf-8") for i in range(80))
    terminal.feed(payload)
    terminal._v_scrollbar.setValue(0)
    prev_offset = terminal._scroll_offset
    assert prev_offset > 0

    zoom_in = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Equal,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "+",
    )
    terminal.keyPressEvent(zoom_in)

    assert terminal._scroll_offset == prev_offset


def test_terminal_resize_preserves_prompt_without_duplication(terminal):
    terminal.feed(b"".join(f"line{i}\r\n".encode("utf-8") for i in range(40)))
    terminal.feed(b"prompt$ ")

    for _ in range(4):
        terminal._resize_screen_preserving_content(18, 80)
        terminal._resize_screen_preserving_content(24, 80)

    lines: list[str] = []
    for row in range(terminal._screen.lines):
        line = terminal._screen.buffer.get(row, {})
        text = "".join(
            line.get(col, terminal._screen.default_char).data or " "
            for col in range(terminal._screen.columns)
        ).rstrip()
        if text:
            lines.append(text)

    assert lines.count("prompt$") == 1


def test_terminal_resize_emission_is_debounced(terminal, qtbot):
    emitted: list[tuple[int, int]] = []
    terminal.size_changed.connect(lambda c, r: emitted.append((c, r)))

    terminal._queue_resize_emit(100, 30)
    terminal._queue_resize_emit(110, 33)
    qtbot.wait(180)

    assert emitted == [(110, 33)]


def test_terminal_zoom_does_not_emit_pty_resize(terminal, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    emitted: list[tuple[int, int]] = []
    terminal.size_changed.connect(lambda c, r: emitted.append((c, r)))

    zoom_in = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Equal,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "+",
    )
    terminal.keyPressEvent(zoom_in)
    qtbot.wait(180)

    assert emitted == []


def test_terminal_color_resolution(terminal):
    """Test ANSI color name resolution."""
    from PySide6.QtGui import QColor

    color = terminal._resolve_color("red", is_bg=False)
    assert isinstance(color, QColor)
    assert color.name() == "#f38ba8"

    # 256-color index
    color = terminal._resolve_color("196", is_bg=False)
    assert isinstance(color, QColor)

    # Default
    color = terminal._resolve_color("default", is_bg=True)
    assert color == terminal._bg_color


def test_terminal_selection(terminal):
    terminal.feed(b"Hello World")
    terminal._sel_start = (0, 0)
    terminal._sel_end = (4, 0)
    text = terminal._get_selected_text()
    assert text == "Hello"


# === SSHConnection (unit, no actual connection) ===

def test_ssh_connection_init():
    conn = SSHConnection(
        hostname="example.com",
        port=22,
        username="testuser",
        password="secret",
    )
    assert not conn.is_connected
    assert conn._hostname == "example.com"
    assert conn._port == 22
    assert conn._username == "testuser"


def test_ssh_connection_close_when_not_connected():
    conn = SSHConnection(hostname="example.com")
    conn.close()  # should not raise
    assert not conn.is_connected
