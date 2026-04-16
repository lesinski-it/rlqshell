"""Session status bar — displays live server metrics as colored icon chips."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QToolButton, QWidget

from rlqshell.app.constants import Colors
from rlqshell.protocols.ssh.monitor import ServerStats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THRESHOLD_GREEN  = Colors.SUCCESS   # < 60 %
_THRESHOLD_YELLOW = Colors.WARNING   # 60–80 %
_THRESHOLD_RED    = Colors.DANGER    # > 80 %


def _threshold_color(pct: int) -> str:
    if pct >= 80:
        return _THRESHOLD_RED
    if pct >= 60:
        return _THRESHOLD_YELLOW
    return _THRESHOLD_GREEN


def _fmt_net(bps: int) -> str:
    """Format bytes transferred in the last 5 s window as a per-second rate."""
    rate = bps / 5.0
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} Mb/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.1f} Kb/s"
    return f"{rate:.0f} B/s"


def _fmt_uptime(secs: int) -> str:
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _fmt_ram(used_kb: int, total_kb: int) -> str:
    """Short RAM string: '0.57/1.92 GB'."""
    return f"{used_kb / 1_048_576:.2f}/{total_kb / 1_048_576:.2f} GB"


def _fmt_disk(used_kb: int, total_kb: int) -> str:
    """Auto-scale disk size: '12.3/40.0 GB' or '256/512 MB'."""
    total_gb = total_kb / 1_048_576
    if total_gb >= 1.0:
        return f"{used_kb / 1_048_576:.1f}/{total_gb:.1f} GB"
    return f"{used_kb // 1024}/{total_kb // 1024} MB"


# ---------------------------------------------------------------------------
# _StatusChip
# ---------------------------------------------------------------------------

_CHIP_HEIGHT    = 22
_ICON_WIDTH     = 20
_RADIUS         = 3
_ICON_FONT_SIZE = 9
_VAL_FONT_SIZE  = 10


def _val_font(base: QFont) -> QFont:
    f = QFont(base)
    f.setPointSize(_VAL_FONT_SIZE)
    return f


class _StatusChip(QWidget):
    """A single metric chip: [colored icon area][value text]."""

    def __init__(self, icon: str, icon_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._icon_color = QColor(icon_color)
        self._value = "—"
        self._value_color = QColor(Colors.TEXT_SECONDARY)

        self.setFixedHeight(_CHIP_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._update_width()

    def set_value(self, text: str, icon_color: str | None = None) -> None:
        self._value = text
        if icon_color is not None:
            self._icon_color = QColor(icon_color)
        self._update_width()
        self.update()

    def _update_width(self) -> None:
        # Measure with the same font that paintEvent uses for the value
        fm = QFontMetrics(_val_font(self.font()))
        val_w = fm.horizontalAdvance(self._value or "—")
        self.setFixedWidth(_ICON_WIDTH + val_w + 12)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Outer rounded rect background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, w, h, _RADIUS, _RADIUS)
        p.fillPath(bg_path, QColor(Colors.BG_SURFACE))

        # Icon pill (left), square-clipped on the right edge
        icon_path = QPainterPath()
        icon_path.addRoundedRect(0, 0, _ICON_WIDTH, h, _RADIUS, _RADIUS)
        p.fillPath(icon_path, self._icon_color)
        p.fillRect(_ICON_WIDTH - _RADIUS, 0, _RADIUS, h, self._icon_color)

        # Icon text
        icon_font = QFont(self.font())
        icon_font.setPointSize(_ICON_FONT_SIZE)
        icon_font.setBold(True)
        p.setFont(icon_font)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(0, 0, _ICON_WIDTH, h), Qt.AlignmentFlag.AlignCenter, self._icon)

        # Value text
        p.setFont(_val_font(self.font()))
        p.setPen(self._value_color)
        p.drawText(
            QRect(_ICON_WIDTH + 5, 0, w - _ICON_WIDTH - 8, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._value,
        )

        p.end()


# ---------------------------------------------------------------------------
# _MonitorToggle
# ---------------------------------------------------------------------------

class _MonitorToggle(QToolButton):
    """Checkable button that draws a mini bar-chart icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setFixedSize(28, _CHIP_HEIGHT)
        self.setToolTip("Toggle server monitoring")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        active = self.isChecked()

        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, w, h, _RADIUS, _RADIUS)
        p.fillPath(bg_path, QColor(Colors.BG_SURFACE))

        bar_w, gap = 4, 2
        total_w = 3 * bar_w + 2 * gap
        x0 = (w - total_w) // 2
        heights = [h * 0.40, h * 0.65, h * 0.85]
        colors_on = [QColor("#22c55e"), QColor("#f59e0b"), QColor("#e94560")]
        color_off = QColor(Colors.TEXT_MUTED)

        for i, bar_h in enumerate(heights):
            bx = x0 + i * (bar_w + gap)
            by = int((h - bar_h) / 2)
            bar_path = QPainterPath()
            bar_path.addRoundedRect(bx, by, bar_w, int(bar_h), 1, 1)
            p.fillPath(bar_path, colors_on[i] if active else color_off)

        p.end()


# ---------------------------------------------------------------------------
# SessionStatusBar
# ---------------------------------------------------------------------------

class SessionStatusBar(QWidget):
    """Compact bar below the terminal showing live server metrics."""

    monitoring_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        self._chip_host   = _StatusChip("▶", Colors.ACCENT)
        self._chip_cpu    = _StatusChip("%",  _THRESHOLD_GREEN)
        self._chip_ram    = _StatusChip("▤",  "#3b82f6")
        self._chip_rx     = _StatusChip("↓",  "#06b6d4")
        self._chip_tx     = _StatusChip("↑",  "#0ea5e9")
        self._chip_uptime = _StatusChip("◷",  "#8b5cf6")
        self._chip_user   = _StatusChip("◉",  "#6c7086")

        self._static_chips: list[_StatusChip] = [
            self._chip_host, self._chip_cpu, self._chip_ram,
            self._chip_rx, self._chip_tx, self._chip_uptime, self._chip_user,
        ]
        self._disk_chips: list[_StatusChip] = []

        for chip in self._static_chips:
            layout.addWidget(chip)

        # Disk chips are inserted here (between static chips and stretch)
        layout.addStretch(1)

        self._toggle = _MonitorToggle()
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_monitoring_enabled(self, enabled: bool) -> None:
        """Set initial toggle state (no signal emitted)."""
        self._toggle.blockSignals(True)
        self._toggle.setChecked(enabled)
        self._toggle.blockSignals(False)
        self._set_chips_visible(enabled)

    def update_stats(self, stats: ServerStats) -> None:
        """Update all chips with fresh server data."""
        if not self._toggle.isChecked():
            return

        # Prevent intermediate repaints while updating multiple chips
        self.setUpdatesEnabled(False)

        self._chip_host.set_value(stats.hostname)

        cpu_color = _threshold_color(stats.cpu_pct)
        self._chip_cpu.set_value(f"{stats.cpu_pct}%", icon_color=cpu_color)

        if stats.mem_total_kb > 0:
            mem_pct = int(100 * stats.mem_used_kb / stats.mem_total_kb)
            self._chip_ram.set_value(
                _fmt_ram(stats.mem_used_kb, stats.mem_total_kb),
                icon_color=_threshold_color(mem_pct),
            )
        else:
            self._chip_ram.set_value("—")

        self._chip_rx.set_value(_fmt_net(stats.net_rx_bytes))
        self._chip_tx.set_value(_fmt_net(stats.net_tx_bytes))
        self._chip_uptime.set_value(_fmt_uptime(stats.uptime_secs))
        self._chip_user.set_value(stats.user or "—")

        self._update_disk_chips(stats.disk)

        self.setUpdatesEnabled(True)

    def clear(self) -> None:
        """Reset all chips to placeholder dashes."""
        for chip in self._static_chips:
            chip.set_value("—")
        self._update_disk_chips([])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_chips_visible(self, visible: bool) -> None:
        for chip in self._static_chips + self._disk_chips:
            chip.setVisible(visible)

    def _update_disk_chips(self, disk: list[tuple[str, int, int, int]]) -> None:
        layout = self.layout()
        assert layout is not None
        monitoring_on = self._toggle.isChecked()
        needed = len(disk)

        # Grow: add missing chips (insert before stretch, which is at count-2)
        while len(self._disk_chips) < needed:
            chip = _StatusChip("⬡", _THRESHOLD_GREEN)
            chip.setVisible(monitoring_on)
            self._disk_chips.append(chip)
            layout.insertWidget(layout.count() - 2, chip)

        # Shrink: remove excess chips from the end
        while len(self._disk_chips) > needed:
            chip = self._disk_chips.pop()
            layout.removeWidget(chip)
            chip.deleteLater()

        # Update values in-place (no widget creation/destruction in steady state)
        for i, (mount, pct, used_kb, total_kb) in enumerate(disk):
            label = mount.lstrip("/") or "/"
            color = _threshold_color(pct)
            chip = self._disk_chips[i]
            if total_kb > 0:
                chip.set_value(f"{label}: {_fmt_disk(used_kb, total_kb)} ({pct}%)", icon_color=color)
            else:
                chip.set_value(f"{label}:{pct}%", icon_color=color)

    def _on_toggle(self, checked: bool) -> None:
        self._set_chips_visible(checked)
        if not checked:
            self.clear()
        self.monitoring_toggled.emit(checked)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(Colors.BG_DARKER))
        pen = QPen(QColor(Colors.BORDER))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawLine(0, 0, self.width(), 0)
        p.end()
