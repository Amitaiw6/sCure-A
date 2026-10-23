"""Screen fitting — the console was laid out for 1500 x 920 logical pixels.
A 1920 x 1080 laptop at 150 % Windows scaling only has 1280 x 688 logical
pixels, so every top-level window is sized to the screen it opens on and
the shell switches to a compact layout when the screen is smaller than the
design size. Pages scroll instead of being crushed.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QScrollArea, QFrame, QWidget

DESIGN_W, DESIGN_H = 1500, 920


def available(widget: QWidget | None = None):
    """Available (work-area) geometry of the screen the widget is on, or the primary screen."""
    scr = (widget.screen() if widget is not None and widget.screen() else None) or QApplication.primaryScreen()
    return scr.availableGeometry()


def is_compact(widget: QWidget | None = None) -> bool:
    g = available(widget)
    return g.width() < DESIGN_W or g.height() < DESIGN_H


def fit(widget: QWidget, w: int, h: int, margin: int = 24) -> None:
    """Resize `widget` to (w, h) clamped to the screen's work area, and centre it."""
    g = available(widget)
    w = min(w, g.width() - margin); h = min(h, g.height() - margin)
    widget.resize(w, h)
    widget.move(g.x() + (g.width() - w) // 2, g.y() + max(0, (g.height() - h) // 2))


def scale_info() -> str:
    scr = QApplication.primaryScreen(); g = scr.availableGeometry()
    return f"{scr.size().width()}x{scr.size().height()} @ {scr.devicePixelRatio():.2f} → {g.width()}x{g.height()} logical"


def scrollable(inner: QWidget, margins=(18, 16, 18, 16)) -> QScrollArea:
    """Wrap a page so it scrolls vertically when the window is shorter than its content."""
    host = QWidget(); host.setProperty("card", "page")
    from PySide6.QtWidgets import QVBoxLayout
    l = QVBoxLayout(host); l.setContentsMargins(*margins); l.addWidget(inner)
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame); sa.setWidget(host)
    sa.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
    return sa
