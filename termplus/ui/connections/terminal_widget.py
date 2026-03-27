"""Terminal widget — pyte VT100 emulator rendered with QPainter."""

from __future__ import annotations

import logging

import pyte

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QClipboard,
    QFont,
    QFontMetricsF,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

# Default ANSI 16-color palette
_ANSI_COLORS: dict[str, str] = {
    "black": "#45475a",
    "red": "#f38ba8",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "blue": "#89b4fa",
    "magenta": "#cba6f7",
    "cyan": "#94e2d5",
    "white": "#bac2de",
    "brightblack": "#585b70",
    "brightred": "#f38ba8",
    "brightgreen": "#a6e3a1",
    "brightyellow": "#f9e2af",
    "brightblue": "#89b4fa",
    "brightmagenta": "#cba6f7",
    "brightcyan": "#94e2d5",
    "brightwhite": "#a6adc8",
    # pyte defaults
    "default": "#cdd6f4",
    "brown": "#fab387",
}

# Qt key → terminal escape sequence mapping
_KEY_MAP: dict[int, bytes] = {
    Qt.Key.Key_Up: b"\x1b[A",
    Qt.Key.Key_Down: b"\x1b[B",
    Qt.Key.Key_Right: b"\x1b[C",
    Qt.Key.Key_Left: b"\x1b[D",
    Qt.Key.Key_Home: b"\x1b[H",
    Qt.Key.Key_End: b"\x1b[F",
    Qt.Key.Key_Insert: b"\x1b[2~",
    Qt.Key.Key_Delete: b"\x1b[3~",
    Qt.Key.Key_PageUp: b"\x1b[5~",
    Qt.Key.Key_PageDown: b"\x1b[6~",
    Qt.Key.Key_F1: b"\x1bOP",
    Qt.Key.Key_F2: b"\x1bOQ",
    Qt.Key.Key_F3: b"\x1bOR",
    Qt.Key.Key_F4: b"\x1bOS",
    Qt.Key.Key_F5: b"\x1b[15~",
    Qt.Key.Key_F6: b"\x1b[17~",
    Qt.Key.Key_F7: b"\x1b[18~",
    Qt.Key.Key_F8: b"\x1b[19~",
    Qt.Key.Key_F9: b"\x1b[20~",
    Qt.Key.Key_F10: b"\x1b[21~",
    Qt.Key.Key_F11: b"\x1b[23~",
    Qt.Key.Key_F12: b"\x1b[24~",
    Qt.Key.Key_Backspace: b"\x7f",
    Qt.Key.Key_Tab: b"\t",
    Qt.Key.Key_Return: b"\r",
    Qt.Key.Key_Enter: b"\r",
    Qt.Key.Key_Escape: b"\x1b",
}


class TerminalWidget(QWidget):
    """QPainter-based terminal emulator widget backed by pyte."""

    input_ready = Signal(bytes)  # data to send to the connection
    size_changed = Signal(int, int)  # cols, rows

    def __init__(
        self,
        cols: int = 80,
        rows: int = 24,
        font_family: str = "JetBrains Mono",
        font_size: int = 13,
        scrollback: int = 10000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        # Font setup
        self._font = QFont(font_family, font_size)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._bold_font = QFont(self._font)
        self._bold_font.setBold(True)
        self._italic_font = QFont(self._font)
        self._italic_font.setItalic(True)
        self._bold_italic_font = QFont(self._font)
        self._bold_italic_font.setBold(True)
        self._bold_italic_font.setItalic(True)

        fm = QFontMetricsF(self._font)
        self._cell_width = fm.horizontalAdvance("M")
        self._cell_height = fm.height()
        self._ascent = fm.ascent()

        # pyte screen + stream
        self._screen = pyte.HistoryScreen(cols, rows, history=scrollback)
        self._screen.set_mode(pyte.modes.LNM)
        self._stream = pyte.Stream(self._screen)

        self._cols = cols
        self._rows = rows
        self._scrollback = scrollback

        # Cursor blink
        self._cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(530)

        # Selection state
        self._selecting = False
        self._sel_start: tuple[int, int] | None = None  # (col, row)
        self._sel_end: tuple[int, int] | None = None

        # Scroll offset into history (0 = bottom)
        self._scroll_offset = 0

        # Background
        self._bg_color = QColor("#1e1e2e")
        self._fg_color = QColor("#cdd6f4")

        # Dirty tracking
        self._dirty = True

        self.setMinimumSize(
            int(self._cell_width * 20), int(self._cell_height * 5)
        )

    # --- Public API ---

    @Slot(bytes)
    def feed(self, data: bytes) -> None:
        """Feed raw terminal data from the connection."""
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")

        self._stream.feed(text)
        # Auto-scroll to bottom on new output
        if self._scroll_offset > 0:
            self._scroll_offset = 0
        self._dirty = True
        self.update()

    def set_font(self, family: str, size: int) -> None:
        """Change terminal font."""
        self._font = QFont(family, size)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._bold_font = QFont(self._font)
        self._bold_font.setBold(True)
        self._italic_font = QFont(self._font)
        self._italic_font.setItalic(True)
        self._bold_italic_font = QFont(self._font)
        self._bold_italic_font.setBold(True)
        self._bold_italic_font.setItalic(True)

        fm = QFontMetricsF(self._font)
        self._cell_width = fm.horizontalAdvance("M")
        self._cell_height = fm.height()
        self._ascent = fm.ascent()

        self._recompute_size()
        self.update()

    # --- Rendering ---

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            # Clear background
            painter.fillRect(self.rect(), self._bg_color)

            screen = self._screen
            cw = self._cell_width
            ch = self._cell_height

            for row_idx in range(self._rows):
                y = row_idx * ch

                # Get screen buffer line (accounting for scroll offset)
                line = screen.buffer.get(row_idx, {})

                for col_idx in range(self._cols):
                    char = line.get(col_idx, screen.default_char)

                    x = col_idx * cw

                    # Background color
                    bg = self._resolve_color(char.bg, is_bg=True)
                    if char.reverse:
                        bg, fg_color = (
                            self._resolve_color(char.fg, is_bg=False),
                            bg,
                        )
                    else:
                        fg_color = self._resolve_color(char.fg, is_bg=False)

                    # Selection highlight
                    if self._is_selected(col_idx, row_idx):
                        bg = QColor("#585b70")
                        fg_color = QColor("#cdd6f4")

                    if bg != self._bg_color:
                        painter.fillRect(QRectF(x, y, cw, ch), bg)

                    # Draw character
                    if char.data and char.data != " ":
                        # Pick font variant
                        if char.bold and char.italics:
                            font = self._bold_italic_font
                        elif char.bold:
                            font = self._bold_font
                        elif char.italics:
                            font = self._italic_font
                        else:
                            font = self._font

                        painter.setFont(font)
                        painter.setPen(fg_color)
                        painter.drawText(QRectF(x, y, cw, ch), Qt.AlignmentFlag.AlignCenter, char.data)

                    # Underline
                    if char.underscore:
                        painter.setPen(fg_color)
                        uy = y + ch - 1
                        painter.drawLine(int(x), int(uy), int(x + cw), int(uy))

            # Draw cursor
            if self._cursor_visible and self._scroll_offset == 0:
                cx = screen.cursor.x * cw
                cy = screen.cursor.y * ch
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#f5e0dc"))
                painter.setOpacity(0.7)
                painter.drawRect(QRectF(cx, cy, cw, ch))
                painter.setOpacity(1.0)
        finally:
            painter.end()

    # --- Keyboard ---

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        key = event.key()

        # Ctrl+Shift+C → copy
        if (
            modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and key == Qt.Key.Key_C
        ):
            self._copy_selection()
            return

        # Ctrl+Shift+V → paste
        if (
            modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and key == Qt.Key.Key_V
        ):
            self._paste()
            return

        # Mapped keys
        seq = _KEY_MAP.get(key)
        if seq:
            self.input_ready.emit(seq)
            return

        # Ctrl+letter (A-Z) → control character
        if modifiers & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            code = key - Qt.Key.Key_A + 1
            self.input_ready.emit(bytes([code]))
            return

        # Regular text input
        text = event.text()
        if text:
            self.input_ready.emit(text.encode("utf-8"))

    # --- Mouse (selection + scroll) ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            col, row = self._pos_to_cell(event.position())
            self._sel_start = (col, row)
            self._sel_end = (col, row)
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._selecting:
            col, row = self._pos_to_cell(event.position())
            self._sel_end = (col, row)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click selects a word."""
        col, row = self._pos_to_cell(event.position())
        line = self._screen.buffer.get(row, {})

        # Find word boundaries
        start = col
        end = col
        while start > 0:
            ch = line.get(start - 1, self._screen.default_char).data
            if ch in (" ", "\t", ""):
                break
            start -= 1
        while end < self._cols:
            ch = line.get(end, self._screen.default_char).data
            if ch in (" ", "\t", ""):
                break
            end += 1

        self._sel_start = (start, row)
        self._sel_end = (end - 1, row)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        history_len = len(self._screen.history.top)
        if delta > 0:
            # Scroll up into history
            self._scroll_offset = min(
                self._scroll_offset + 3, history_len
            )
        else:
            # Scroll down
            self._scroll_offset = max(self._scroll_offset - 3, 0)
        self.update()

    # --- Resize ---

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._recompute_size()

    def _recompute_size(self) -> None:
        new_cols = max(1, int(self.width() / self._cell_width))
        new_rows = max(1, int(self.height() / self._cell_height))
        if new_cols != self._cols or new_rows != self._rows:
            self._cols = new_cols
            self._rows = new_rows
            self._screen.resize(new_rows, new_cols)
            self.size_changed.emit(new_cols, new_rows)
            self.update()

    # --- Private helpers ---

    def _blink_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        # Only repaint the cursor area for efficiency
        if self._screen:
            cx = int(self._screen.cursor.x * self._cell_width)
            cy = int(self._screen.cursor.y * self._cell_height)
            self.update(QRect(cx, cy, int(self._cell_width) + 1, int(self._cell_height) + 1))

    def _resolve_color(self, color: str, is_bg: bool) -> QColor:
        """Convert pyte color names/codes to QColor."""
        if not color or color == "default":
            return self._bg_color if is_bg else self._fg_color

        # Named color
        lower = color.lower()
        if lower in _ANSI_COLORS:
            return QColor(_ANSI_COLORS[lower])

        # 256-color index
        if color.isdigit():
            idx = int(color)
            if idx < 16:
                names = list(_ANSI_COLORS.keys())[:16]
                return QColor(_ANSI_COLORS[names[idx]])
            elif idx < 232:
                # 6x6x6 color cube
                idx -= 16
                b = (idx % 6) * 51
                idx //= 6
                g = (idx % 6) * 51
                r = (idx // 6) * 51
                return QColor(r, g, b)
            else:
                # Grayscale
                gray = 8 + (idx - 232) * 10
                return QColor(gray, gray, gray)

        # Hex color
        if len(color) == 6:
            try:
                return QColor(f"#{color}")
            except Exception:
                pass

        return self._bg_color if is_bg else self._fg_color

    def _pos_to_cell(self, pos) -> tuple[int, int]:
        """Convert widget pixel position to (col, row)."""
        col = max(0, min(int(pos.x() / self._cell_width), self._cols - 1))
        row = max(0, min(int(pos.y() / self._cell_height), self._rows - 1))
        return col, row

    def _is_selected(self, col: int, row: int) -> bool:
        if self._sel_start is None or self._sel_end is None:
            return False
        sc, sr = self._sel_start
        ec, er = self._sel_end

        # Normalize so start <= end
        if (sr, sc) > (er, ec):
            sc, sr, ec, er = ec, er, sc, sr

        if sr == er:
            return row == sr and sc <= col <= ec
        if row == sr:
            return col >= sc
        if row == er:
            return col <= ec
        return sr < row < er

    def _get_selected_text(self) -> str:
        if self._sel_start is None or self._sel_end is None:
            return ""

        sc, sr = self._sel_start
        ec, er = self._sel_end
        if (sr, sc) > (er, ec):
            sc, sr, ec, er = ec, er, sc, sr

        lines: list[str] = []
        for row in range(sr, er + 1):
            line = self._screen.buffer.get(row, {})
            start_col = sc if row == sr else 0
            end_col = ec if row == er else self._cols - 1
            chars = []
            for c in range(start_col, end_col + 1):
                ch = line.get(c, self._screen.default_char)
                chars.append(ch.data if ch.data else " ")
            lines.append("".join(chars).rstrip())

        return "\n".join(lines)

    def _copy_selection(self) -> None:
        text = self._get_selected_text()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)

    def _paste(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text()
            if text:
                self.input_ready.emit(text.encode("utf-8"))
