"""Reusable widgets: Card, Pill, StatTile, Stepper, FadeStack, PulseDot, Toast."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QRectF, Property, QParallelAnimationGroup, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PySide6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QStackedWidget,
                               QGraphicsOpacityEffect, QSizePolicy)

from . import theme as T


def label(text="", role=None, color=None, size=None, bold=False, wrap=False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    css = []
    if color: css.append(f"color: {color};")
    if size: css.append(f"font-size: {size}px;")
    if bold: css.append("font-weight: 700;")
    if css: lb.setStyleSheet(" ".join(css))
    lb.setWordWrap(wrap)
    return lb


class Card(QFrame):
    def __init__(self, title: str | None = None, kind: str = "true", hint: str | None = None):
        super().__init__()
        self.setProperty("card", kind)
        self.body = QVBoxLayout(self); self.body.setContentsMargins(16, 14, 16, 14); self.body.setSpacing(10)
        if title:
            row = QHBoxLayout(); row.addWidget(label(title.upper(), "eyebrow")); row.addStretch()
            if hint:
                self.hint = label(hint, "muted"); self.hint.setStyleSheet(f"color: {T.MUTED}; font-size: 11px;"); row.addWidget(self.hint)
            self.body.addLayout(row)


class Pill(QLabel):
    def __init__(self, text="—", color=T.MUTED):
        super().__init__(text); self.setProperty("role", "pill"); self.set(text, color)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text, color):
        self.setText(text); self.setStyleSheet(f"background: {color}2b; color: {color};")


class StatTile(QFrame):
    def __init__(self, caption: str, value: str = "—", color: str = T.INK):
        super().__init__(); self.setProperty("card", "true")
        l = QVBoxLayout(self); l.setContentsMargins(16, 12, 16, 12); l.setSpacing(2)
        self.value = label(value, size=24, bold=True, color=color); self.caption = label(caption.upper(), "eyebrow")
        l.addWidget(self.value); l.addWidget(self.caption)

    def set(self, value, color=None):
        self.value.setText(str(value))
        if color:
            self.value.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {color};")


class PulseDot(QWidget):
    """Small breathing dot used for 'live' / 'current step' indicators."""

    def __init__(self, color=T.OK, size=12):
        super().__init__(); self._color = QColor(color); self._phase = 0.0; self.setFixedSize(size + 8, size + 8)
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(40)

    def set_color(self, color):
        self._color = QColor(color); self.update()

    def _tick(self):
        self._phase = (self._phase + 0.06) % 6.283; self.update()

    def paintEvent(self, _):
        import math
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        c = self.rect().center(); r = self.width() / 2 - 2
        halo = QColor(self._color); halo.setAlphaF(0.18 + 0.18 * math.sin(self._phase))
        p.setPen(Qt.NoPen); p.setBrush(halo); p.drawEllipse(c, r, r)
        p.setBrush(self._color); p.drawEllipse(c, r * 0.45, r * 0.45)


class Stepper(QWidget):
    """Horizontal wizard progress: numbered nodes, animated fill to the current step."""

    def __init__(self, titles: list[str]):
        super().__init__(); self.titles = titles; self.current = 0; self._fill = 0.0
        self.setMinimumHeight(64); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = QPropertyAnimation(self, b"fill", self); self._anim.setDuration(450); self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def _get_fill(self): return self._fill
    def _set_fill(self, v): self._fill = v; self.update()
    fill = Property(float, _get_fill, _set_fill)

    def set_current(self, i: int):
        self.current = i
        self._anim.stop(); self._anim.setStartValue(self._fill); self._anim.setEndValue(float(i)); self._anim.start()

    def set_titles(self, titles):
        self.titles = titles; self.current = 0; self._fill = 0.0; self.update()

    def paintEvent(self, _):
        n = len(self.titles)
        if n == 0:
            return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); pad = 24; y = 22
        xs = [pad + (w - 2 * pad) * i / max(n - 1, 1) for i in range(n)]
        p.setPen(QPen(QColor(T.LINE), 3)); p.drawLine(int(xs[0]), y, int(xs[-1]), y)
        if n > 1:
            fx = xs[0] + (xs[-1] - xs[0]) * self._fill / (n - 1)
            p.setPen(QPen(QColor(T.ACCENT), 3)); p.drawLine(int(xs[0]), y, int(fx), y)
        f = QFont("Segoe UI", 9); fb = QFont("Segoe UI", 9, QFont.Bold)
        for i, x in enumerate(xs):
            done, cur = i < self.current, i == self.current
            col = QColor(T.ACCENT if (done or cur) else T.LINE)
            p.setPen(QPen(col, 2)); p.setBrush(QBrush(QColor(T.ACCENT) if done else QColor(T.CARD) if not cur else QColor(T.ACCENT)))
            r = 11 if cur else 9
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
            p.setPen(QColor(T.ACCENT_INK if (done or cur) else T.MUTED)); p.setFont(fb)
            p.drawText(QRectF(x - 12, y - 12, 24, 24), Qt.AlignCenter, "✓" if done else str(i + 1))
            p.setPen(QColor(T.INK if cur else T.MUTED)); p.setFont(fb if cur else f)
            tw = min(140, (w - 2 * pad) / max(n - 1, 1) + 30) if n > 1 else 200
            p.drawText(QRectF(x - tw / 2, y + 16, tw, 30), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.titles[i])


class FadeStack(QStackedWidget):
    """QStackedWidget whose page changes fade + slide in (respecting reduced motion = 0 duration)."""

    duration = 260

    def set_page(self, index: int, forward: bool = True):
        if index == self.currentIndex() or self.duration == 0:
            self.setCurrentIndex(index); return
        w = self.widget(index)
        eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff); eff.setOpacity(0.0)
        self.setCurrentIndex(index)
        start = w.pos() + QPoint(40 if forward else -40, 0); end = w.pos()
        w.move(start)
        g = QParallelAnimationGroup(self)
        a = QPropertyAnimation(eff, b"opacity"); a.setDuration(self.duration); a.setStartValue(0.0); a.setEndValue(1.0); a.setEasingCurve(QEasingCurve.OutCubic)
        b = QPropertyAnimation(w, b"pos"); b.setDuration(self.duration); b.setStartValue(start); b.setEndValue(end); b.setEasingCurve(QEasingCurve.OutCubic)
        g.addAnimation(a); g.addAnimation(b)
        g.finished.connect(lambda: w.setGraphicsEffect(None))
        g.start(QPropertyAnimation.DeleteWhenStopped)
        self._anim = g


class Toast(QLabel):
    """Transient message in the corner of a parent widget."""

    def __init__(self, parent):
        super().__init__(parent); self.hide(); self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"background: {T.CARD_2}; color: {T.INK}; border: 1px solid {T.LINE}; border-radius: 10px; padding: 10px 18px; font-weight: 600;")
        self._t = QTimer(self); self._t.setSingleShot(True); self._t.timeout.connect(self.hide)

    def show_message(self, text: str, color: str | None = None, ms: int = 2600):
        self.setText(text)
        if color:
            self.setStyleSheet(f"background: {T.CARD_2}; color: {color}; border: 1px solid {color}; border-radius: 10px; padding: 10px 18px; font-weight: 600;")
        self.adjustSize(); pw = self.parent().width(); ph = self.parent().height()
        self.move(pw - self.width() - 24, ph - self.height() - 24); self.raise_(); self.show(); self._t.start(ms)
