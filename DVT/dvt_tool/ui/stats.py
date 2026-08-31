"""Statistics page — the comparison view (SRS-DVT-095): a swept test renders
as one curve per unit (x = sweep value / repetition, y = any numeric data
field), plus the table of the same numbers. Pure QPainter.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
                               QSizePolicy, QLabel)

from . import theme as T
from .widgets import Card, label

UNIT_COLORS = ["#2f6fdb", "#e8461f", "#1f9d61", "#7c5cbf", "#d68a0c", "#0aa3b5"]


class LineChart(QWidget):
    def __init__(self):
        super().__init__(); self.series: dict[str, list[tuple[float, float]]] = {}; self.xlabels: list[str] = []
        self.ylabel = ""; self.limit: float | None = None
        self.setMinimumHeight(300); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set(self, series, xlabels, ylabel, limit=None):
        self.series, self.xlabels, self.ylabel, self.limit = series, xlabels, ylabel, limit; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); L, R, Tm, B = 56, 24, 20, 40
        plot = QRectF(L, Tm, w - L - R, h - Tm - B)
        p.fillRect(self.rect(), QColor(T.CARD))
        pts = [y for s in self.series.values() for _, y in s]
        if not pts:
            p.setPen(QColor(T.MUTED)); p.drawText(self.rect(), Qt.AlignCenter, "No recorded values yet for this field"); return
        lo, hi = min(pts + ([self.limit] if self.limit is not None else [])), max(pts + ([self.limit] if self.limit is not None else []))
        if hi == lo: hi = lo + 1
        pad = (hi - lo) * 0.1; lo -= pad; hi += pad
        n = max(len(self.xlabels), 1)
        def X(i): return plot.left() + plot.width() * (i / max(n - 1, 1))
        def Y(v): return plot.bottom() - plot.height() * (v - lo) / (hi - lo)
        p.setPen(QPen(QColor(T.LINE), 1))
        for k in range(5):
            y = plot.top() + plot.height() * k / 4; p.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            p.setPen(QColor(T.MUTED)); p.setFont(QFont("Segoe UI", 8)); p.drawText(QRectF(0, y - 8, L - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{hi - (hi - lo) * k / 4:.1f}"); p.setPen(QPen(QColor(T.LINE), 1))
        for i, xl in enumerate(self.xlabels):
            p.setPen(QColor(T.MUTED)); p.drawText(QRectF(X(i) - 40, plot.bottom() + 6, 80, 16), Qt.AlignCenter, xl)
        if self.limit is not None:
            p.setPen(QPen(QColor(T.BAD), 1.5, Qt.DashLine)); p.drawLine(int(plot.left()), int(Y(self.limit)), int(plot.right()), int(Y(self.limit)))
            p.drawText(QRectF(plot.right() - 120, Y(self.limit) - 16, 120, 14), Qt.AlignRight, f"limit {self.limit:g}")
        for si, (name, s) in enumerate(self.series.items()):
            col = QColor(UNIT_COLORS[si % len(UNIT_COLORS)]); path = QPainterPath(); first = True
            for i, y in s:
                pt = QPointF(X(i), Y(y))
                path.moveTo(pt) if first else path.lineTo(pt); first = False
                p.setPen(Qt.NoPen); p.setBrush(col); p.drawEllipse(pt, 3.5, 3.5)
            p.setPen(QPen(col, 2)); p.setBrush(Qt.NoBrush); p.drawPath(path)
            p.setPen(col); p.setFont(QFont("Segoe UI", 9, QFont.Bold)); p.drawText(int(plot.left()) + 8 + si * 90, int(plot.top()) + 12, name)
        p.setPen(QColor(T.MUTED)); p.setFont(QFont("Segoe UI", 8)); p.save(); p.translate(14, plot.center().y()); p.rotate(-90); p.drawText(QRectF(-80, -8, 160, 16), Qt.AlignCenter, self.ylabel); p.restore()


class StatisticsPage(QWidget):
    def __init__(self, engine):
        super().__init__(); self.engine, self.cat, self.store = engine, engine.cat, engine.store
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(16)
        cm = Card("All machines — verdict per test", hint="rolled-up verdict of each test on each unit · N/A = not applicable to that unit")
        self.matrix = QTableWidget(0, 0); self.matrix.verticalHeader().hide(); self.matrix.setMinimumHeight(220); cm.body.addWidget(self.matrix, 1); root.addWidget(cm, 2)
        c = Card("Comparison across units", hint="SRS-DVT-095 — one curve per unit, x = sweep value (or repetition)")
        row = QHBoxLayout(); row.addWidget(label("Test", "muted")); self.cb_test = QComboBox(); self.cb_test.setMinimumWidth(420)
        for tid in self.cat.ordered_test_ids(): self.cb_test.addItem(f"{tid} — {self.cat.tests[tid]['title']}", tid)
        row.addWidget(self.cb_test); row.addWidget(label("Field", "muted")); self.cb_field = QComboBox(); self.cb_field.setMinimumWidth(220); row.addWidget(self.cb_field); row.addStretch()
        c.body.addLayout(row); self.chart = LineChart(); c.body.addWidget(self.chart, 1); root.addWidget(c, 2)
        c2 = Card("Values"); self.tbl = QTableWidget(0, 0); self.tbl.verticalHeader().hide(); c2.body.addWidget(self.tbl); root.addWidget(c2, 1)
        self.cb_test.currentIndexChanged.connect(self._fields); self.cb_field.currentIndexChanged.connect(self.refresh)
        self._fields()

    def _fields(self):
        tid = self.cb_test.currentData(); self.cb_field.blockSignals(True); self.cb_field.clear()
        for f in self.cat.tests[tid].get("data_fields") or []:
            if f["type"] in ("float", "int"): self.cb_field.addItem(f["name"] + (f" [{f['unit']}]" if f.get("unit") else ""), f["name"])
        self.cb_field.blockSignals(False); self.refresh()

    def refresh_matrix(self):
        m = self.engine.unit_matrix(); units = m["units"]
        self.matrix.clear(); self.matrix.setColumnCount(len(units) + 2); self.matrix.setHorizontalHeaderLabels(["Test", "Subsystem"] + units); self.matrix.setRowCount(len(m["rows"]))
        for i, r in enumerate(m["rows"]):
            self.matrix.setItem(i, 0, QTableWidgetItem(f"{r['testId']}  {r['title'][:40]}"))
            sub = QTableWidgetItem(r["subsystem"]); sub.setForeground(QColor(T.SUBSYSTEM.get(r["subsystem"], T.INK))); self.matrix.setItem(i, 1, sub)
            for j, u in enumerate(units):
                v = r["cells"][u]; it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter)
                col = T.VERDICT.get(v); it.setForeground(QColor(col if col else (T.LINE_2 if v == "N/A" else T.MUTED)))
                if col:
                    f = it.font(); f.setBold(True); it.setFont(f)
                self.matrix.setItem(i, j + 2, it)
        self.matrix.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for j in range(1, len(units) + 2): self.matrix.horizontalHeader().setSectionResizeMode(j, QHeaderView.ResizeToContents)

    def refresh(self):
        self.refresh_matrix()
        tid = self.cb_test.currentData(); field = self.cb_field.currentData()
        if not tid or not field: self.chart.set({}, [], ""); return
        runs = [r for r in self.store.runs(tid) if r["status"] == "DONE"]
        variants = self.cat.variants(tid); reps = int(self.cat.tests[tid].get("repetitions") or 1)
        xs = [(", ".join(f"{k}={v}" for k, v in var.items()) or f"rep {rep}") if reps == 1 or var else f"rep {rep}"
              for var in variants for rep in range(1, reps + 1)]
        index = {(tuple(sorted(var.items())), rep): i for i, (var, rep) in enumerate([(v, r) for v in variants for r in range(1, reps + 1)])}
        series = {}; table = {}
        for r in runs:
            v = self.store.values(r["run_id"]).get(field)
            if not isinstance(v, (int, float)): continue
            i = index.get((tuple(sorted(r["variant"].items())), r["repetition"]))
            if i is None: continue
            series.setdefault(r["unit_id"], []).append((i, float(v))); table.setdefault(r["unit_id"], {})[i] = v
        for s in series.values(): s.sort()
        limit = None
        import re
        m = re.search(rf"{re.escape(field)}\s*(<=|<)\s*([0-9.]+)", self.cat.tests[tid]["pass_criteria"])
        if m: limit = float(m.group(2))
        self.chart.set(series, xs, field, limit)
        self.tbl.clear(); self.tbl.setColumnCount(len(xs) + 1); self.tbl.setHorizontalHeaderLabels(["Unit"] + xs); self.tbl.setRowCount(len(table))
        for row, (u, vals) in enumerate(sorted(table.items())):
            self.tbl.setItem(row, 0, QTableWidgetItem(u))
            for i in range(len(xs)):
                it = QTableWidgetItem("" if i not in vals else f"{vals[i]:g}")
                if limit is not None and i in vals and vals[i] > limit: it.setForeground(QColor(T.BAD))
                self.tbl.setItem(row, i + 1, it)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
