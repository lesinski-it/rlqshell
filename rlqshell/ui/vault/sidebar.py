"""Vault sidebar — compact 64-px icon rail with section navigation."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rlqshell.app.constants import Colors, ICONS_DIR

# (Display label, section key, icon filename)
SECTIONS: list[tuple[str, str, str]] = [
    ("Hosts",           "hosts",        "hosts.svg"),
    ("Snippets",        "snippets",     "snippets.svg"),
    ("Keychain",        "keychain",     "keychain.svg"),
    ("Identities",      "identities",   "identities.svg"),
    ("Known Hosts",     "known_hosts",  "known_hosts.svg"),
    ("Port Forwarding", "port_forward", "port_forward.svg"),
    ("History",         "history",      "history.svg"),
]


def _render_svg_icon(filename: str, color: str, size: int = 22) -> QIcon:
    """Load an SVG file, recolor `currentColor` to `color`, and rasterize to a QIcon."""
    path = ICONS_DIR / filename
    if not path.exists():
        return QIcon()
    svg_text = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class _SidebarItem(QPushButton):
    """Single icon-only sidebar navigation item with tooltip label."""

    def __init__(
        self,
        label: str,
        section_key: str,
        icon_file: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.section_key = section_key
        self._label = label
        self._icon_file = icon_file
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedSize(QSize(64, 56))
        self.setIconSize(QSize(22, 22))
        self._update_visual(False)

    def _update_visual(self, active: bool) -> None:
        color = Colors.ACCENT if active else Colors.TEXT_SECONDARY
        self.setIcon(_render_svg_icon(self._icon_file, color))
        if active:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background-color: {Colors.BG_SURFACE}; "
                f"  border: none; "
                f"  border-left: 3px solid {Colors.ACCENT}; "
                f"  border-radius: 0; "
                f"  padding-left: 0; "
                f"}}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ "
                f"  background: transparent; "
                f"  border: none; "
                f"  border-left: 3px solid transparent; "
                f"  border-radius: 0; "
                f"  padding-left: 0; "
                f"}}"
                f"QPushButton:hover {{ "
                f"  background-color: {Colors.BG_SURFACE}; "
                f"}}"
            )

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._update_visual(active)


class Sidebar(QWidget):
    """Compact left rail (64 px) with icon-only section navigation."""

    section_changed = Signal(str)  # section key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(64)
        self.setStyleSheet(
            f"Sidebar {{ "
            f"  background-color: {Colors.BG_DARKER}; "
            f"  border-right: 1px solid {Colors.BORDER}; "
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(4)

        self._items: list[_SidebarItem] = []
        for label, key, icon_file in SECTIONS:
            item = _SidebarItem(label, key, icon_file)
            item.clicked.connect(lambda checked=False, k=key: self._on_item_click(k))
            self._items.append(item)
            layout.addWidget(item, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch()

        # Select first item
        if self._items:
            self._items[0].set_active(True)

    def _on_item_click(self, section_key: str) -> None:
        for item in self._items:
            item.set_active(item.section_key == section_key)
        self.section_changed.emit(section_key)

    def select_section(self, section_key: str) -> None:
        """Programmatically select a section."""
        if any(item.section_key == section_key for item in self._items):
            self._on_item_click(section_key)
