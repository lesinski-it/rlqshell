"""Terminal widget — pyte VT100 emulator rendered with QPainter."""

from __future__ import annotations

import logging

import pyte

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTimer, Signal, Slot
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
from PySide6.QtWidgets import QApplication, QScrollBar, QWidget

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

# DECCKM (Application Cursor Keys) — pyte stores private mode 1 as 1 << 5 = 32
_DECCKM = 32

# Qt key → terminal escape sequence mapping (normal cursor mode)
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
    Qt.Key.Key_Backtab: b"\x1b[Z",
    Qt.Key.Key_Return: b"\r",
    Qt.Key.Key_Enter: b"\r",
    Qt.Key.Key_Escape: b"\x1b",
}

# Overrides when DECCKM (application cursor mode) is active — used by mc, vim, etc.
_APP_CURSOR_MAP: dict[int, bytes] = {
    Qt.Key.Key_Up: b"\x1bOA",
    Qt.Key.Key_Down: b"\x1bOB",
    Qt.Key.Key_Right: b"\x1bOC",
    Qt.Key.Key_Left: b"\x1bOD",
    Qt.Key.Key_Home: b"\x1bOH",
    Qt.Key.Key_End: b"\x1bOF",
}

_MIN_FONT_SIZE = 8
_MAX_FONT_SIZE = 32


class TerminalWidget(QWidget):
    """QPainter-based terminal emulator widget backed by pyte."""

    input_ready = Signal(bytes)  # data to send to the connection
    size_changed = Signal(int, int)  # cols, rows
    focus_gained = Signal()  # emitted when the terminal receives focus

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

        # Debounced PTY resize emission (prevents prompt spam on rapid zoom/resize).
        self._pending_resize: tuple[int, int] | None = None
        self._resize_emit_timer = QTimer(self)
        self._resize_emit_timer.setSingleShot(True)
        self._resize_emit_timer.setInterval(120)
        self._resize_emit_timer.timeout.connect(self._emit_queued_resize)
        self._suppress_pty_resize_emit = False
        self._suppress_screen_resize = False

        # Selection state
        self._selecting = False
        self._sel_start: tuple[int, int] | None = None  # (col, row)
        self._sel_end: tuple[int, int] | None = None

        # Scroll offset into history (0 = bottom)
        self._scroll_offset = 0

        # Background
        self._bg_color = QColor("#1e1e2e")
        self._fg_color = QColor("#cdd6f4")

        # Overlay (status messages like "Connecting...", errors)
        self._overlay_text: str | None = None
        self._overlay_color: QColor = QColor("#a6adc8")

        # Dirty tracking
        self._dirty = True

        # Freeze resize flag — set during detach/dock to preserve pyte buffer
        self._freeze_resize = False

        # Scrollbar (visible history slider on the right)
        self._scrollbar_width = 12
        self._v_scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._v_scrollbar.setSingleStep(1)
        self._v_scrollbar.valueChanged.connect(self._on_scrollbar_changed)

        self.setMinimumSize(
            int(self._cell_width * 20) + self._scrollbar_width, int(self._cell_height * 5)
        )
        self._layout_scrollbar()
        self._sync_scrollbar_from_offset()

    # --- Public API ---

    def show_overlay(self, text: str, color: str | None = None) -> None:
        """Show a centered status overlay on the terminal."""
        self._overlay_text = text
        if color:
            self._overlay_color = QColor(color)
        else:
            self._overlay_color = QColor("#a6adc8")
        self.update()

    def clear_overlay(self) -> None:
        """Remove the status overlay."""
        if self._overlay_text is not None:
            self._overlay_text = None
            self.update()

    @Slot(bytes)
    def feed(self, data: bytes) -> None:
        """Feed raw terminal data from the connection."""
        self.clear_overlay()
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")

        self._stream.feed(text)
        # Auto-scroll to bottom on new output
        if self._scroll_offset > 0:
            self._scroll_offset = 0
        self._dirty = True
        self._sync_scrollbar_from_offset()
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
        self._sync_scrollbar_from_offset()
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
            visible_lines = self._get_visible_lines()

            for row_idx in range(self._rows):
                y = row_idx * ch

                # Visible line in viewport (history + current buffer)
                line = visible_lines[row_idx] if row_idx < len(visible_lines) else {}

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

            # Draw overlay (status messages)
            if self._overlay_text:
                overlay_font = QFont(self._font)
                overlay_font.setPointSize(14)
                painter.setFont(overlay_font)
                fm = QFontMetricsF(overlay_font)
                text_width = fm.horizontalAdvance(self._overlay_text)
                text_height = fm.height()
                pad_x, pad_y = 24, 12
                rx = (self.width() - text_width) / 2 - pad_x
                ry = (self.height() - text_height) / 2 - pad_y
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(30, 30, 46, 200))
                painter.drawRoundedRect(
                    QRectF(rx, ry, text_width + pad_x * 2, text_height + pad_y * 2),
                    8, 8,
                )
                painter.setPen(self._overlay_color)
                painter.drawText(
                    QRectF(0, 0, self.width(), self.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    self._overlay_text,
                )
        finally:
            painter.end()

    # --- Focus ---

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focus_gained.emit()

    # --- Keyboard ---

    def event(self, event: QEvent) -> bool:
        """Intercept Tab/Backtab before Qt uses them for focus navigation."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.keyPressEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        key = event.key()

        # Ctrl+Shift++ / Ctrl+Shift+- -> terminal font zoom
        if (
            modifiers & Qt.KeyboardModifier.ControlModifier
            and modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._adjust_font_size(1)
                return
            if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                self._adjust_font_size(-1)
                return

        # Ctrl+Shift+C -> copy
        if (
            modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and key == Qt.Key.Key_C
        ):
            self._copy_selection()
            return

        # Ctrl+Shift+V -> paste
        if (
            modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and key == Qt.Key.Key_V
        ):
            self._paste()
            return

        # Mapped keys (application cursor mode overrides when DECCKM is active)
        if _DECCKM in self._screen.mode:
            seq = _APP_CURSOR_MAP.get(key) or _KEY_MAP.get(key)
        else:
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
        visible_lines = self._get_visible_lines()
        line = visible_lines[row] if row < len(visible_lines) else {}

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
        max_offset = self._max_scroll_offset()
        if max_offset <= 0:
            return
        if delta > 0:
            # Scroll up into history
            self._scroll_offset = min(
                self._scroll_offset + 3, max_offset
            )
        else:
            # Scroll down
            self._scroll_offset = max(self._scroll_offset - 3, 0)
        self._sync_scrollbar_from_offset()
        self.update()

    # --- Resize ---

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_scrollbar()
        self._recompute_size()

    def _recompute_size(self) -> None:
        if self._content_width() < 10 or self.height() < 10:
            return  # skip resize during reparenting
        if self._freeze_resize:
            return  # skip resize while detaching (preserves pyte buffer)
        new_cols = max(1, int(self._content_width() / self._cell_width))
        new_rows = max(1, int(self.height() / self._cell_height))
        if new_cols != self._cols or new_rows != self._rows:
            self._cols = new_cols
            self._rows = new_rows
            if not self._suppress_screen_resize:
                self._resize_screen_preserving_content(new_rows, new_cols)
                if not self._suppress_pty_resize_emit:
                    self._queue_resize_emit(new_cols, new_rows)
        self._sync_scrollbar_from_offset()
        self.update()

    # --- Private helpers ---

    def _adjust_font_size(self, delta: int) -> None:
        current = self._font.pointSize()
        new_size = max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, current + delta))
        if new_size != current:
            prev_offset = self._scroll_offset
            # Keep zoom local to renderer; avoid PTY resize prompt redraw spam.
            self._pending_resize = None
            self._resize_emit_timer.stop()
            self._suppress_pty_resize_emit = True
            self._suppress_screen_resize = True
            try:
                self.set_font(self._font.family(), new_size)
            finally:
                self._suppress_pty_resize_emit = False
                self._suppress_screen_resize = False
            # Keep current history position after zoom (natural terminal behavior).
            self._scroll_offset = prev_offset
            self._sync_scrollbar_from_offset()

    def _queue_resize_emit(self, cols: int, rows: int) -> None:
        self._pending_resize = (cols, rows)
        self._resize_emit_timer.start()

    def _emit_queued_resize(self) -> None:
        if self._pending_resize is None:
            return
        cols, rows = self._pending_resize
        self._pending_resize = None
        self.size_changed.emit(cols, rows)

    def _content_width(self) -> int:
        return max(1, self.width() - self._scrollbar_width)

    def _layout_scrollbar(self) -> None:
        self._v_scrollbar.setGeometry(
            self.width() - self._scrollbar_width,
            0,
            self._scrollbar_width,
            self.height(),
        )

    def _max_scroll_offset(self) -> int:
        return max(0, len(self._screen.history.top))

    def _sync_scrollbar_from_offset(self) -> None:
        max_offset = self._max_scroll_offset()
        self._scroll_offset = max(0, min(self._scroll_offset, max_offset))
        self._v_scrollbar.blockSignals(True)
        self._v_scrollbar.setRange(0, max_offset)
        self._v_scrollbar.setPageStep(max(1, self._rows))
        self._v_scrollbar.setValue(max_offset - self._scroll_offset)
        self._v_scrollbar.setEnabled(max_offset > 0)
        self._v_scrollbar.blockSignals(False)

    def _on_scrollbar_changed(self, value: int) -> None:
        max_offset = self._max_scroll_offset()
        self._scroll_offset = max_offset - value
        self.update()

    def _resize_screen_preserving_content(self, new_rows: int, new_cols: int) -> None:
        """Resize pyte screen without line duplication artifacts.

        pyte.HistoryScreen.resize() can duplicate trailing rows when rows shrink/grow
        repeatedly. Build a new screen from existing history + visible rows instead.
        """
        old_screen = self._screen
        if new_rows == old_screen.lines and new_cols == old_screen.columns:
            return

        old_history = list(old_screen.history.top)
        old_rows = [old_screen.buffer.get(row, {}) for row in range(old_screen.lines)]
        all_lines = [dict(line) for line in (old_history + old_rows)]

        # Keep only scrollback + viewport tail.
        max_total = max(1, self._scrollback + new_rows)
        if len(all_lines) > max_total:
            all_lines = all_lines[-max_total:]

        # Ensure the new viewport is fully populated with empty rows when needed.
        if len(all_lines) < new_rows:
            all_lines = ([{}] * (new_rows - len(all_lines))) + all_lines

        history_lines = all_lines[:-new_rows] if len(all_lines) > new_rows else []
        buffer_lines = all_lines[-new_rows:]

        new_screen = pyte.HistoryScreen(new_cols, new_rows, history=self._scrollback)
        new_screen.set_mode(pyte.modes.LNM)
        new_screen.mode = set(old_screen.mode)
        new_screen.charset = old_screen.charset
        new_screen.g0_charset = old_screen.g0_charset
        new_screen.g1_charset = old_screen.g1_charset
        new_screen.icon_name = old_screen.icon_name
        new_screen.title = old_screen.title

        def _clip_line(line: dict) -> dict:
            if not line:
                return {}
            return {col: char for col, char in line.items() if col < new_cols}

        for line in history_lines:
            new_screen.history.top.append(_clip_line(line))

        for row, line in enumerate(buffer_lines):
            clipped = _clip_line(line)
            if clipped:
                new_screen.buffer[row] = clipped

        old_abs_cursor = len(old_history) + max(0, min(old_screen.cursor.y, old_screen.lines - 1))
        visible_total = len(all_lines)
        old_total = len(old_history) + old_screen.lines
        crop_start = max(0, old_total - visible_total)
        new_abs_cursor = max(0, old_abs_cursor - crop_start)
        history_len = len(history_lines)
        new_screen.cursor.y = max(0, min(new_rows - 1, new_abs_cursor - history_len))
        new_screen.cursor.x = max(0, min(new_cols - 1, old_screen.cursor.x))

        self._screen = new_screen
        self._stream.detach(old_screen)
        self._stream.attach(new_screen)

    def _get_visible_lines(self) -> list[dict]:
        history = list(self._screen.history.top)
        screen_rows = getattr(self._screen, "lines", self._rows)
        start_row = max(0, screen_rows - self._rows)
        current = [
            self._screen.buffer.get(start_row + row, {})
            for row in range(self._rows)
        ]
        lines = history + current
        if not lines:
            return [{} for _ in range(self._rows)]
        start = max(0, len(lines) - self._rows - self._scroll_offset)
        visible = lines[start:start + self._rows]
        if len(visible) < self._rows:
            visible.extend({} for _ in range(self._rows - len(visible)))
        return visible

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

