"""Custom connection tab bar with protocol icons and close buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from termplus.app.constants import Colors


class _TabButton(QWidget):
    """Single tab representing a connection."""

    clicked = Signal(str)  # tab_id
    close_requested = Signal(str)  # tab_id

    def __init__(
        self,
        tab_id: str,
        label: str,
        protocol: str = "SSH",
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_id = tab_id
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 4, 4)
        layout.setSpacing(6)

        # Protocol badge
        proto = QLabel(protocol.upper())
        proto.setFixedWidth(30)
        proto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 3px; padding: 1px 3px;"
        )
        layout.addWidget(proto)

        # Color dot
        if color:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background-color: {color}; border-radius: 4px; border: none;"
            )
            layout.addWidget(dot)

        # Label
        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(self._label)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ font-size: 11px; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {Colors.DANGER}; color: white; }}"
        )
        close_btn.clicked.connect(lambda: self.close_requested.emit(self._tab_id))
        layout.addWidget(close_btn)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                f"_TabButton {{ background-color: {Colors.BG_SURFACE}; "
                f"border-bottom: 2px solid {Colors.ACCENT}; border-radius: 0; }}"
            )
            self._label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_PRIMARY}; font-weight: 600; "
                f"background: transparent;"
            )
        else:
            self.setStyleSheet(
                f"_TabButton {{ background: transparent; "
                f"border-bottom: 2px solid transparent; border-radius: 0; }}"
                f"_TabButton:hover {{ background-color: {Colors.BG_HOVER}; }}"
            )
            self._label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: transparent;"
            )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._tab_id)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit(self._tab_id)


class ConnectionTabBar(QWidget):
    """Horizontal scrollable tab bar for connections."""

    tab_selected = Signal(str)  # tab_id
    tab_close_requested = Signal(str)
    new_tab_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet(
            f"ConnectionTabBar {{ background-color: {Colors.BG_DARKER}; "
            f"border-bottom: 1px solid {Colors.BORDER}; }}"
        )

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Scrollable tabs area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setFixedHeight(38)
        outer_layout.addWidget(scroll, 1)

        self._tabs_container = QWidget()
        self._tabs_layout = QHBoxLayout(self._tabs_container)
        self._tabs_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs_layout.setSpacing(1)
        self._tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._tabs_container)

        # "+" new tab button
        new_btn = QPushButton("+")
        new_btn.setFixedSize(32, 32)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(
            f"QPushButton {{ font-size: 16px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; border: none; border-radius: 4px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
            f"background-color: {Colors.BG_HOVER}; }}"
        )
        new_btn.clicked.connect(self.new_tab_requested.emit)
        outer_layout.addWidget(new_btn)

        self._tabs: dict[str, _TabButton] = {}
        self._active_tab: str | None = None

    def add_tab(
        self,
        tab_id: str,
        label: str,
        protocol: str = "SSH",
        color: str | None = None,
    ) -> None:
        tab = _TabButton(tab_id, label, protocol, color)
        tab.clicked.connect(self._on_tab_clicked)
        tab.close_requested.connect(self._on_tab_close)
        self._tabs[tab_id] = tab
        self._tabs_layout.addWidget(tab)
        self.select_tab(tab_id)

    def remove_tab(self, tab_id: str) -> None:
        tab = self._tabs.pop(tab_id, None)
        if tab:
            self._tabs_layout.removeWidget(tab)
            tab.deleteLater()

        # Select next tab if active was closed
        if self._active_tab == tab_id:
            self._active_tab = None
            if self._tabs:
                self.select_tab(next(iter(self._tabs)))

    def select_tab(self, tab_id: str) -> None:
        self._active_tab = tab_id
        for tid, tab in self._tabs.items():
            tab.set_active(tid == tab_id)
        self.tab_selected.emit(tab_id)

    @property
    def active_tab(self) -> str | None:
        return self._active_tab

    @property
    def tab_count(self) -> int:
        return len(self._tabs)

    def _on_tab_clicked(self, tab_id: str) -> None:
        self.select_tab(tab_id)

    def _on_tab_close(self, tab_id: str) -> None:
        self.tab_close_requested.emit(tab_id)
