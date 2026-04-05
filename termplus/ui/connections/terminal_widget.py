"""Terminal widget — pyte VT100 emulator rendered with QPainter."""

from __future__ import annotations

import logging

import pyte

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QAction,
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
from PySide6.QtWidgets import QApplication, QMenu, QScrollBar, QWidget

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
        scroll_speed: int = 3,
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
        self._scroll_speed = max(1, scroll_speed)

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

        # Selection state
        self._selecting = False
        self._sel_start: tuple[int, int] | None = None  # (col, row)
        self._sel_end: tuple[int, int] | None = None

        # Click tracking for triple-click line selection
        self._click_count = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(400)
        self._click_timer.timeout.connect(self._reset_click_count)

        # Default font size for reset
        self._default_font_size = font_size

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

            # Scroll-to-bottom indicator
            if self._scroll_offset > 0:
                pill_text = f"\u2193 {self._scroll_offset}"
                pill_font = QFont(self._font)
                pill_font.setPointSize(max(9, self._font.pointSize() - 2))
                painter.setFont(pill_font)
                pfm = QFontMetricsF(pill_font)
                tw = pfm.horizontalAdvance(pill_text)
                th = pfm.height()
                px, py = 12, 8
                pill_w = tw + px * 2
                pill_h = th + py
                content_w = self._content_width()
                pill_x = content_w - pill_w - 8
                pill_y = self.height() - pill_h - 8
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(30, 30, 46, 220))
                painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), pill_h / 2, pill_h / 2)
                painter.setPen(QColor("#94e2d5"))
                painter.drawText(
                    QRectF(pill_x, pill_y, pill_w, pill_h),
                    Qt.AlignmentFlag.AlignCenter,
                    pill_text,
                )
                painter.setFont(self._font)

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

        # Ctrl+Shift+A -> select all
        if (
            modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and key == Qt.Key.Key_A
        ):
            self._select_all()
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

            # Shift+click extends selection from existing anchor
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self._sel_start is not None:
                self._sel_end = (col, row)
                self._selecting = True
                self.update()
                return

            # Track clicks for triple-click detection
            self._click_count += 1
            self._click_timer.start()

            if self._click_count >= 3:
                # Triple-click: select entire line
                self._sel_start = (0, row)
                self._sel_end = (self._cols - 1, row)
                self._selecting = False
                self._click_count = 0
                self.update()
                return

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
        # Count this as click #2 for triple-click detection
        self._click_count = 2
        self._click_timer.start()

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
        # Ctrl+scroll = font zoom
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if delta > 0:
                self._adjust_font_size(1)
            elif delta < 0:
                self._adjust_font_size(-1)
            return
        max_offset = self._max_scroll_offset()
        if max_offset <= 0:
            return
        speed = self._scroll_speed
        old_offset = self._scroll_offset
        if delta > 0:
            # Scroll up into history
            self._scroll_offset = min(
                self._scroll_offset + speed, max_offset
            )
        else:
            # Scroll down
            self._scroll_offset = max(self._scroll_offset - speed, 0)
        self._shift_selection(self._scroll_offset - old_offset)
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
            # Suppress PTY resize to avoid prompt redraw spam on the remote side,
            # but allow the pyte screen to resize so the buffer stays in sync with
            # the new column/row count — prevents text loss on zoom-out.
            self._pending_resize = None
            self._resize_emit_timer.stop()
            self._suppress_pty_resize_emit = True
            try:
                self.set_font(self._font.family(), new_size)
            finally:
                self._suppress_pty_resize_emit = False
            # Snap to bottom so the current prompt stays visible after zoom.
            self._scroll_offset = 0
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
        old_offset = self._scroll_offset
        self._scroll_offset = max_offset - value
        self._shift_selection(self._scroll_offset - old_offset)
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
        # Strip empty rows below cursor so the prompt stays at the bottom
        # of the viewport after zoom instead of floating in the middle.
        cursor_y = max(0, min(old_screen.cursor.y, old_screen.lines - 1))
        last_used = cursor_y
        for r in range(old_screen.lines - 1, cursor_y, -1):
            if old_screen.buffer.get(r, {}):
                last_used = r
                break
        old_rows = [old_screen.buffer.get(row, {}) for row in range(last_used + 1)]
        all_lines = [dict(line) for line in (old_history + old_rows)]

        # Keep only scrollback + viewport tail.
        max_total = max(1, self._scrollback + new_rows)
        if len(all_lines) > max_total:
            all_lines = all_lines[-max_total:]

        # Ensure the new viewport is fully populated with empty rows when needed.
        # Extra rows are appended at the bottom (top-anchored growth), which matches
        # terminal behavior during window maximize/resize.
        if len(all_lines) < new_rows:
            all_lines = all_lines + ([{}] * (new_rows - len(all_lines)))

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

        for line in history_lines:
            new_screen.history.top.append(dict(line) if line else {})

        for row, line in enumerate(buffer_lines):
            if line:
                new_screen.buffer[row] = dict(line)

        old_abs_cursor = len(old_history) + cursor_y
        trimmed_total = len(old_history) + len(old_rows)
        crop_start = max(0, trimmed_total - len(all_lines))
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

    def _shift_selection(self, delta: int) -> None:
        """Shift selection coordinates to track content when scroll offset changes."""
        if delta == 0:
            return
        if self._sel_start is not None:
            sc, sr = self._sel_start
            self._sel_start = (sc, sr + delta)
        if self._sel_end is not None:
            ec, er = self._sel_end
            self._sel_end = (ec, er + delta)

    def _get_selected_text(self) -> str:
        if self._sel_start is None or self._sel_end is None:
            return ""

        sc, sr = self._sel_start
        ec, er = self._sel_end
        if (sr, sc) > (er, ec):
            sc, sr, ec, er = ec, er, sc, sr

        # Build full line array (history + screen buffer) to support
        # selections that extend beyond the current viewport.
        history = list(self._screen.history.top)
        screen_lines = getattr(self._screen, "lines", self._rows)
        current = [self._screen.buffer.get(r, {}) for r in range(screen_lines)]
        all_lines = history + current
        # Viewport row 0 maps to this index in all_lines
        base = len(all_lines) - self._rows - self._scroll_offset

        lines: list[str] = []
        for row in range(sr, er + 1):
            idx = base + row
            line = all_lines[idx] if 0 <= idx < len(all_lines) else {}
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
            self._sel_start = None
            self._sel_end = None
            self.update()

    def _paste(self) -> None:
        clipboard = QApplication.clipboard()
        if not clipboard:
            return
        text = clipboard.text()
        if not text:
            return
        # Single line: paste immediately; multi-line: show confirmation dialog
        if "\n" not in text and "\r" not in text:
            self.input_ready.emit(text.encode("utf-8"))
        else:
            from termplus.ui.dialogs.paste_confirm_dialog import PasteConfirmDialog

            dlg = PasteConfirmDialog(text, parent=self)
            if dlg.exec() == PasteConfirmDialog.Accepted:
                self.input_ready.emit(text.encode("utf-8"))

    def _cut_selection(self) -> None:
        """Copy selected text and send backspace for each character (simulated cut)."""
        text = self._get_selected_text()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            # Send backspaces to remove selected text from command line
            for _ in text.replace("\n", ""):
                self.input_ready.emit(b"\x08")

    def _select_all(self) -> None:
        """Select all visible lines."""
        self._sel_start = (0, 0)
        self._sel_end = (self._cols - 1, self._rows - 1)
        self.update()

    def _clear_scrollback(self) -> None:
        """Clear scrollback history."""
        self._screen.history.top.clear()
        if hasattr(self._screen.history, "bottom"):
            self._screen.history.bottom.clear()
        self._scroll_offset = 0
        self._sync_scrollbar_from_offset()
        self.update()

    def _reset_terminal(self) -> None:
        """Reset terminal state."""
        self._screen.reset()
        self._scroll_offset = 0
        self._sel_start = None
        self._sel_end = None
        self._sync_scrollbar_from_offset()
        self.update()

    def _reset_font_size(self) -> None:
        """Reset font to default size."""
        if self._font.pointSize() != self._default_font_size:
            self._pending_resize = None
            self._resize_emit_timer.stop()
            self._suppress_pty_resize_emit = True
            try:
                self.set_font(self._font.family(), self._default_font_size)
            finally:
                self._suppress_pty_resize_emit = False
            self._scroll_offset = 0
            self._sync_scrollbar_from_offset()

    def _reset_click_count(self) -> None:
        self._click_count = 0

    # --- Context menu ---

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 28px 6px 12px;
            }
            QMenu::item:selected {
                background: #313244;
            }
            QMenu::item:disabled {
                color: #585b70;
            }
            QMenu::separator {
                height: 1px;
                background: #45475a;
                margin: 4px 8px;
            }
        """)

        has_selection = bool(self._sel_start and self._sel_end and self._sel_start != self._sel_end)
        clipboard = QApplication.clipboard()
        has_clipboard = bool(clipboard and clipboard.text())

        act_copy = menu.addAction("Copy\tCtrl+Shift+C")
        act_copy.setEnabled(has_selection)

        act_cut = menu.addAction("Cut\tCtrl+Shift+X")
        act_cut.setEnabled(has_selection)

        act_paste = menu.addAction("Paste\tCtrl+Shift+V")
        act_paste.setEnabled(has_clipboard)

        menu.addSeparator()

        act_select_all = menu.addAction("Select All\tCtrl+Shift+A")

        act_clear_sel = menu.addAction("Clear Selection")
        act_clear_sel.setEnabled(has_selection)

        menu.addSeparator()

        act_clear_buf = menu.addAction("Clear Scrollback")

        act_reset = menu.addAction("Reset Terminal")

        menu.addSeparator()

        # Font size submenu
        font_menu = menu.addMenu("Font Size")
        font_menu.setStyleSheet(menu.styleSheet())

        act_zoom_in = font_menu.addAction("Zoom In\tCtrl+Shift++")
        act_zoom_out = font_menu.addAction("Zoom Out\tCtrl+Shift+-")
        act_zoom_reset = font_menu.addAction("Reset")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return

        if chosen is act_copy:
            self._copy_selection()
        elif chosen is act_cut:
            self._cut_selection()
        elif chosen is act_paste:
            self._paste()
        elif chosen is act_select_all:
            self._select_all()
        elif chosen is act_clear_sel:
            self._sel_start = None
            self._sel_end = None
            self.update()
        elif chosen is act_clear_buf:
            self._clear_scrollback()
        elif chosen is act_reset:
            self._reset_terminal()
        elif chosen is act_zoom_in:
            self._adjust_font_size(1)
        elif chosen is act_zoom_out:
            self._adjust_font_size(-1)
        elif chosen is act_zoom_reset:
            self._reset_font_size()

