"""Custom connection tab bar with drag-reorder and detach support."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QDrag, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyleOption,
    QWidget,
)

from termplus.app.constants import Colors

_TAB_MIME = "application/x-termplus-tab"

_BTN_STYLE = (
    f"QPushButton {{ font-size: 12px; color: {Colors.TEXT_MUTED}; "
    f"background: transparent; border: none; border-radius: 4px; "
    f"padding: 0; margin: 0; }}"
)


class _TabButton(QWidget):
    """Single tab representing a connection."""

    clicked = Signal(str)
    close_requested = Signal(str)
    fullscreen_requested = Signal(str)
    detach_requested = Signal(str)

    def __init__(
        self,
        tab_id: str,
        label: str,
        protocol: str = "SSH",
        color: str | None = None,
        show_fullscreen: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_id = tab_id
        self._label_text = label
        self._protocol = protocol
        self._color = color
        self._active = False
        self._hovered = False
        self._drag_start: QPoint | None = None
        self._show_fullscreen = show_fullscreen

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(120)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(6)

        # Color bar on the left edge
        if color:
            bar = QLabel()
            bar.setFixedSize(3, 28)
            bar.setStyleSheet(
                f"background-color: {color}; border-radius: 1px; border: none;"
            )
            layout.addWidget(bar)

        # Protocol badge
        proto = QLabel(protocol.upper())
        proto.setFixedSize(36, 18)
        proto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proto.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background-color: {Colors.BG_HOVER}; border-radius: 3px; "
            f"padding: 1px 4px; border: none;"
        )
        layout.addWidget(proto)

        # Label
        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_SECONDARY}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._label, 1)

        # Fullscreen button
        self._fs_btn = QPushButton("[ ]")
        self._fs_btn.setFixedSize(22, 22)
        self._fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fs_btn.setToolTip("Fullscreen (F11)")
        self._fs_btn.setStyleSheet(
            _BTN_STYLE
            + f"QPushButton:hover {{ background-color: {Colors.ACCENT}; color: white; }}"
        )
        self._fs_btn.clicked.connect(lambda: self.fullscreen_requested.emit(self._tab_id))
        self._fs_btn.setVisible(False)
        if show_fullscreen:
            layout.addWidget(self._fs_btn)

        # Close button
        self._close_btn = QPushButton("\u2715")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            _BTN_STYLE
            + f"QPushButton:hover {{ background-color: {Colors.DANGER}; color: white; }}"
        )
        self._close_btn.clicked.connect(lambda: self.close_requested.emit(self._tab_id))
        self._close_btn.setVisible(False)
        layout.addWidget(self._close_btn)

        self._apply_style()

    # -- Properties --

    @property
    def tab_id(self) -> str:
        return self._tab_id

    @property
    def label_text(self) -> str:
        return self._label_text

    @property
    def protocol(self) -> str:
        return self._protocol

    @property
    def color(self) -> str | None:
        return self._color

    # -- Active / hover --

    def set_active(self, active: bool) -> None:
        self._active = active
        self._close_btn.setVisible(active)
        if self._show_fullscreen:
            self._fs_btn.setVisible(active)
        self._apply_style()

    def enterEvent(self, event: QEvent) -> None:
        self._hovered = True
        self._close_btn.setVisible(True)
        if self._show_fullscreen:
            self._fs_btn.setVisible(True)
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        if not self._active:
            self._close_btn.setVisible(False)
            if self._show_fullscreen:
                self._fs_btn.setVisible(False)
        self._apply_style()
        super().leaveEvent(event)

    def _apply_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                f"background-color: #2d2351; "
                f"border-bottom: 3px solid {Colors.ACCENT}; "
                f"border-radius: 6px 6px 0 0;"
            )
            self._label.setStyleSheet(
                f"font-size: 12px; color: #ffffff; font-weight: 700; "
                f"background: transparent; border: none;"
            )
        elif self._hovered:
            self.setStyleSheet(
                f"background-color: {Colors.BG_HOVER}; "
                f"border-bottom: 2px solid transparent; "
                f"border-radius: 6px 6px 0 0;"
            )
            self._label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_PRIMARY}; "
                f"background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(
                f"background: transparent; "
                f"border-bottom: 2px solid transparent;"
            )
            self._label.setStyleSheet(
                f"font-size: 12px; color: {Colors.TEXT_MUTED}; "
                f"background: transparent; border: none;"
            )

    def paintEvent(self, event) -> None:
        """Required for QWidget subclass to respect stylesheet background."""
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(self.style().PrimitiveElement.PE_Widget, opt, p, self)
        p.end()

    # -- Mouse / Drag --

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self.clicked.emit(self._tab_id)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit(self._tab_id)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_start is not None
            and (event.pos() - self._drag_start).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_TAB_MIME, self._tab_id.encode("utf-8"))
            drag.setMimeData(mime)
            drag.setPixmap(self.grab())
            drag.setHotSpot(event.pos())

            result = drag.exec(Qt.DropAction.MoveAction)

            # If drop was not accepted, check if cursor is far from tab bar → detach
            if result == Qt.DropAction.IgnoreAction:
                bar = self.parent()
                while bar and not isinstance(bar, ConnectionTabBar):
                    bar = bar.parent()
                if bar:
                    bar_rect = bar.rect()
                    cursor_in_bar = bar.mapFromGlobal(QCursor.pos())
                    # If cursor is >50px outside tab bar vertically → detach
                    if (
                        cursor_in_bar.y() < -50
                        or cursor_in_bar.y() > bar_rect.height() + 50
                    ):
                        self.detach_requested.emit(self._tab_id)

            self._drag_start = None

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)


class ConnectionTabBar(QWidget):
    """Horizontal scrollable tab bar for connections with drag reorder."""

    tab_selected = Signal(str)
    tab_close_requested = Signal(str)
    new_tab_requested = Signal()
    fullscreen_requested = Signal()
    tab_detach_requested = Signal(str)  # tab_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionTabBar")
        self.setFixedHeight(40)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            f"#ConnectionTabBar {{ background-color: {Colors.BG_DARKER}; "
            f"border-bottom: 1px solid {Colors.BORDER}; }}"
        )

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 4, 0)
        outer_layout.setSpacing(0)

        # Scrollable tabs area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setFixedHeight(40)
        scroll.setAcceptDrops(True)
        outer_layout.addWidget(scroll, 1)

        self._tabs_container = QWidget()
        self._tabs_container.setStyleSheet("background: transparent;")
        self._tabs_container.setAcceptDrops(True)
        self._tabs_layout = QHBoxLayout(self._tabs_container)
        self._tabs_layout.setContentsMargins(4, 0, 4, 0)
        self._tabs_layout.setSpacing(1)
        self._tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._tabs_container)

        # Drop indicator (thin accent line shown during drag)
        self._drop_indicator = QLabel()
        self._drop_indicator.setFixedWidth(2)
        self._drop_indicator.setStyleSheet(f"background-color: {Colors.ACCENT};")
        self._drop_indicator.setVisible(False)
        self._drop_indicator.setParent(self._tabs_container)
        self._drop_index: int = -1

        # "+" new tab button
        new_btn = QPushButton("+")
        new_btn.setFixedSize(36, 36)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setToolTip("New connection")
        new_btn.setStyleSheet(
            f"QPushButton {{ font-size: 18px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"background: transparent; border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; "
            f"background-color: {Colors.BG_HOVER}; }}"
        )
        new_btn.clicked.connect(self.new_tab_requested.emit)
        outer_layout.addWidget(new_btn)

        self._tabs: dict[str, _TabButton] = {}
        self._active_tab: str | None = None

    # -- Tab management --

    def add_tab(
        self,
        tab_id: str,
        label: str,
        protocol: str = "SSH",
        color: str | None = None,
        show_fullscreen: bool = True,
    ) -> None:
        tab = _TabButton(tab_id, label, protocol, color, show_fullscreen)
        tab.clicked.connect(self._on_tab_clicked)
        tab.close_requested.connect(self._on_tab_close)
        tab.fullscreen_requested.connect(self._on_tab_fullscreen)
        tab.detach_requested.connect(self.tab_detach_requested.emit)
        self._tabs[tab_id] = tab
        self._tabs_layout.addWidget(tab)
        self.select_tab(tab_id)

    def remove_tab(self, tab_id: str) -> None:
        tab = self._tabs.pop(tab_id, None)
        if tab:
            self._tabs_layout.removeWidget(tab)
            tab.deleteLater()

        if self._active_tab == tab_id:
            self._active_tab = None
            if self._tabs:
                self.select_tab(next(iter(self._tabs)))

    def select_tab(self, tab_id: str) -> None:
        self._active_tab = tab_id
        for tid, tab in self._tabs.items():
            tab.set_active(tid == tab_id)
        self.tab_selected.emit(tab_id)

    def tab_info(self, tab_id: str) -> tuple[str, str, str | None] | None:
        """Return (label, protocol, color) for a tab."""
        tab = self._tabs.get(tab_id)
        if tab:
            return tab.label_text, tab.protocol, tab.color
        return None

    def ordered_tab_ids(self) -> list[str]:
        """Return tab IDs in current visual order."""
        result = []
        for i in range(self._tabs_layout.count()):
            w = self._tabs_layout.itemAt(i).widget()
            if isinstance(w, _TabButton):
                result.append(w.tab_id)
        return result

    @property
    def active_tab(self) -> str | None:
        return self._active_tab

    @property
    def tab_count(self) -> int:
        return len(self._tabs)

    # -- Drag & drop (reorder) --

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_TAB_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_TAB_MIME):
            return
        event.acceptProposedAction()

        # Find insertion index based on cursor X in tabs container
        pos_in_container = self._tabs_container.mapFrom(self, event.position().toPoint())
        insert_idx = self._tabs_layout.count()
        indicator_x = 0

        for i in range(self._tabs_layout.count()):
            item = self._tabs_layout.itemAt(i)
            w = item.widget()
            if w and isinstance(w, _TabButton):
                mid = w.x() + w.width() // 2
                if pos_in_container.x() < mid:
                    insert_idx = i
                    indicator_x = w.x()
                    break
                indicator_x = w.x() + w.width()

        self._drop_index = insert_idx
        self._drop_indicator.setFixedHeight(self._tabs_container.height())
        self._drop_indicator.move(indicator_x, 0)
        self._drop_indicator.setVisible(True)
        self._drop_indicator.raise_()

    def dragLeaveEvent(self, event) -> None:
        self._drop_indicator.setVisible(False)
        self._drop_index = -1

    def dropEvent(self, event) -> None:
        self._drop_indicator.setVisible(False)
        if not event.mimeData().hasFormat(_TAB_MIME):
            return

        tab_id = bytes(event.mimeData().data(_TAB_MIME)).decode("utf-8")
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        event.acceptProposedAction()

        # Remove from current position and re-insert at drop index
        self._tabs_layout.removeWidget(tab)
        self._tabs_layout.insertWidget(self._drop_index, tab)
        self._drop_index = -1

    # -- Internal callbacks --

    def _on_tab_clicked(self, tab_id: str) -> None:
        self.select_tab(tab_id)

    def _on_tab_fullscreen(self, tab_id: str) -> None:
        self.select_tab(tab_id)
        self.fullscreen_requested.emit()

    def _on_tab_close(self, tab_id: str) -> None:
        self.tab_close_requested.emit(tab_id)
