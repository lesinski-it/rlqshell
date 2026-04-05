"""Splash screen shown during application startup."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QByteArray, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QRegion
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from termplus.app.constants import APP_VERSION

_SVG_PATH = Path(__file__).parent.parent / "resources" / "images" / "splash.svg"
# SVG viewBox is 680x480 but the visible content rect starts at (40,20) with size 600x440.
# We size the widget to the content area only, eliminating transparent margins that
# render as a gray border on systems without a compositor.
_SVG_VB_W = 680
_SVG_VB_H = 480
_CONTENT_X = 40
_CONTENT_Y = 20
_SPLASH_W = 600
_SPLASH_H = 440
_BAR_FULL_W = 240


class SplashScreen(QWidget):
    """Frameless, always-on-top splash screen rendered from SVG."""

    def __init__(self, version: str = APP_VERSION) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._version = version
        self._progress = 0
        self._message = "Initializing\u2026"
        self._svg_template = _SVG_PATH.read_bytes()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_SPLASH_W, _SPLASH_H)
        # Rounded mask as fallback for systems without compositor.
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, _SPLASH_W, _SPLASH_H), 20, 20)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        self._center_on_screen()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - _SPLASH_W // 2,
            screen.center().y() - _SPLASH_H // 2,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        svg_bytes = _patch_svg(self._svg_template, self._version, self._progress, self._message)
        renderer = QSvgRenderer(QByteArray(svg_bytes))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Shift so the SVG content area (40,20) aligns to widget (0,0).
        painter.translate(-_CONTENT_X, -_CONTENT_Y)
        renderer.render(painter, QRectF(0, 0, _SVG_VB_W, _SVG_VB_H))
        painter.end()

    def update_progress(self, value: int, message: str = "") -> None:
        """Update progress bar (0–100) and status message, then repaint."""
        self._progress = value
        self._message = message
        self.repaint()
        QApplication.processEvents()


def _patch_svg(template: bytes, version: str, progress: int, message: str) -> bytes:
    """Substitute version, progress bar width, and status message into the SVG template."""
    svg = template.decode("utf-8")
    fill_w = round(_BAR_FULL_W * max(0, min(100, progress)) / 100)

    svg = svg.replace(
        'width="0" height="4" rx="2" fill="#22D3EE" opacity="0.5" id="splash-progress-bar"',
        f'width="{fill_w}" height="4" rx="2" fill="#22D3EE" opacity="0.5" id="splash-progress-bar"',
        1,
    )
    svg = svg.replace(">Initializing\u2026</text>", f">{message}</text>", 1)
    svg = svg.replace(">v0.1.0</text>", f">v{version}</text>", 1)

    return svg.encode("utf-8")
