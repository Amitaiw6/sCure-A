"""Dashboard page: KPI strip, test distribution by subsystem (donut, click
to filter), test matrix grouped by subsystem, live telemetry + interlocks.

Pure Qt painting — no chart library. Data comes from
Engine.subsystem_summary(); machine state is pushed in by the application's
single DutMonitor through `on_dut(state)`.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QTreeWidget, QTreeWidgetItem,
                               QHeaderView, QSizePolicy, QPushButton)

from .ui import theme as T
from .ui.widgets import Card, Pill, StatTile, label
from .ui.dut import MetricTile, TILES

SUBSYSTEM_COLORS, SUBSYSTEM_ICONS = T.SUBSYSTEM, T.SUBSYSTEM_ICON
STATUS_LABEL = {"Complete": "✓ Complete", "Running": "▶ Running", "Failed": "✗ Failed", "Blocked": "⊘ Blocked", "Pending": "○ Pending"}


class DonutWidget(QWidget):
    sliceClicked = Signal(str)

    def __init__(self):
        super().__init__(); self.data = []; self.selected = ""; self._spans = []
        self.setMinimumSize(200, 200); self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed); self.setCursor(Qt.PointingHandCursor)

    def set_data(self, data): self.data = data; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        total = sum(c for _, c, _ in self.data) or 1
        side = min(self.width(), self.height()) - 8
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side).adjusted(18, 18, -18, -18)
        start = 90 * 16; self._spans = []
        for name, count, colour in self.data:
            span = -int(round(360 * 16 * count / total))
            pen = QPen(QColor(colour), 26 if name != self.selected else 34); pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush); p.drawArc(rect, start, span)
            self._spans.append((name, start / 16, span / 16)); start += span
        p.setPen(QColor(T.INK)); p.setFont(QFont("Segoe UI", 22, QFont.Bold)); p.drawText(rect, Qt.AlignCenter, str(sum(c for _, c, _ in self.data)))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold)); p.setPen(QColor(T.MUTED)); p.drawText(rect.adjusted(0, 40, 0, 0), Qt.AlignCenter, "DVT TESTS")

    def mousePressEvent(self, ev):
        c = QPointF(self.width() / 2, self.height() / 2); d = ev.position() - c
        ang = math.degrees(math.atan2(-d.y(), d.x())) % 360
        for name, start, span in self._spans:
            a0, a1 = start % 360, (start + span) % 360
            hit = (a1 <= ang <= a0) if a1 <= a0 else (ang <= a0 or ang >= a1)
            if hit:
                self.selected = "" if self.selected == name else name; self.sliceClicked.emit(self.selected); self.update(); return
        self.selected = ""; self.sliceClicked.emit(""); self.update()


class DashboardPage(QWidget):
    openTest = Signal(str)

    def __init__(self, engine, machine_url: str = "", standalone: bool = False):
        super().__init__(); self.engine = engine; self.filter = ""; self.summary = {}
        self._build()

    # ---------------- layout ----------------
    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(16)
        centre = QVBoxLayout(); centre.setSpacing(16); root.addLayout(centre, 3)
        strip = QHBoxLayout(); strip.setSpacing(12); self.kpis = {}
        for key, cap, col in (("tests", "Tests", T.INK), ("running", "Running", T.WARN), ("failed", "Failed", T.BAD), ("complete", "Complete", T.OK), ("runs", "Runs done", T.INK)):
            t = StatTile(cap, "—", col); strip.addWidget(t); self.kpis[key] = t
        centre.addLayout(strip)

        c = Card("Test distribution by subsystem", hint="click a slice or a subsystem to filter the matrix"); row = QHBoxLayout(); row.setSpacing(24); c.body.addLayout(row)
        self.donut = DonutWidget(); self.donut.sliceClicked.connect(self.set_filter); row.addWidget(self.donut)
        self.legend = QGridLayout(); self.legend.setHorizontalSpacing(18); self.legend.setVerticalSpacing(8); row.addLayout(self.legend, 1)
        centre.addWidget(c)

        c = Card("Progress by subsystem", hint="% of applicable runs committed"); self.prog_grid = QGridLayout(); self.prog_grid.setHorizontalSpacing(14); self.prog_grid.setVerticalSpacing(6)
        c.body.addLayout(self.prog_grid); self.overall_bar = None; centre.addWidget(c)

        c = Card("Test matrix — grouped by subsystem"); self.matrix_card = c
        self.matrix_hint = label("", "muted"); c.body.addWidget(self.matrix_hint, 0, Qt.AlignRight)
        self.tree = QTreeWidget(); self.tree.setColumnCount(9)
        self.tree.setHeaderLabels(["ID / Subsystem", "Test name", "Method", "Appl.", "Status", "Result", "Runs", "Reps", "Est (min)"])
        hdr = self.tree.header(); hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4, 5, 6, 7, 8): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tree.setRootIsDecorated(True); self.tree.setUniformRowHeights(True); self.tree.setIndentation(18)
        self.tree.itemDoubleClicked.connect(lambda it, _: it.data(0, Qt.UserRole) and self.openTest.emit(it.data(0, Qt.UserRole)))
        c.body.addWidget(self.tree, 1); centre.addWidget(c, 1)

        right = QVBoxLayout(); right.setSpacing(16); root.addLayout(right, 1)
        c = Card("Live telemetry"); self.tele_status = label("waiting for the machine…", "muted"); c.body.addWidget(self.tele_status)
        self.tiles = {}
        for key, cap, unit, col, rng in TILES[:4]:
            t = MetricTile(cap, unit, col, rng); c.body.addWidget(t); self.tiles[key] = t
        right.addWidget(c)
        c = Card("Safety & interlocks"); g = QGridLayout(); g.setVerticalSpacing(8); c.body.addLayout(g); self.inter = {}
        for i, (k, txt) in enumerate((("door", "Door closed / locked"), ("uv", "UV off"), ("heater", "Heater off"), ("fault", "No active fault"))):
            g.addWidget(label(txt), i, 0); pl = Pill("—", T.MUTED); g.addWidget(pl, i, 1, alignment=Qt.AlignRight); self.inter[k] = pl
        right.addWidget(c)
        c = Card("What is left", hint="pending runs per test · double-click to open"); self.remaining = QTreeWidget(); self.remaining.setColumnCount(3)
        self.remaining.setHeaderLabels(["Test", "Pending runs", "Est (min)"]); self.remaining.header().setSectionResizeMode(0, QHeaderView.Stretch); self.remaining.setRootIsDecorated(False)
        self.remaining.itemDoubleClicked.connect(lambda it, _: it.data(0, Qt.UserRole) and self.openTest.emit(it.data(0, Qt.UserRole)))
        c.body.addWidget(self.remaining, 1); self.remaining_hint = label("", "muted"); c.body.addWidget(self.remaining_hint); right.addWidget(c, 1)

    # ---------------- data ----------------
    def refresh(self):
        from PySide6.QtWidgets import QProgressBar
        self.summary = self.engine.subsystem_summary()
        total = sum(s["tests"] for s in self.summary.values())
        prog = self.engine.progress()
        failed = sum(s["failed"] for s in self.summary.values())
        pct = round(100 * prog["done"] / prog["total"]) if prog["total"] else 0
        self.kpis["tests"].set(total); self.kpis["running"].set(sum(s["running"] for s in self.summary.values()))
        self.kpis["failed"].set(failed, T.BAD if failed else T.INK); self.kpis["complete"].set(sum(s["complete"] for s in self.summary.values()))
        self.kpis["runs"].set(f"{pct}%  ·  {prog['done']}/{prog['total']}")
        # progress bars: overall + one per subsystem
        while self.prog_grid.count():
            w = self.prog_grid.takeAt(0).widget()
            if w: w.deleteLater()
        rows = [("Campaign", pct, prog["done"], prog["total"], T.ACCENT)] + [(n, s["percent"], s["runsDone"], s["runsTotal"], T.SUBSYSTEM.get(n, T.MUTED)) for n, s in self.summary.items()]
        for i, (name, p, d, t_, col) in enumerate(rows):
            nm = label(name, bold=(i == 0)); self.prog_grid.addWidget(nm, i, 0)
            bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(p); bar.setTextVisible(False); bar.setFixedHeight(10)
            bar.setStyleSheet(f"QProgressBar {{ background: {T.LINE}; border-radius: 5px; }} QProgressBar::chunk {{ background: {col}; border-radius: 5px; }}")
            self.prog_grid.addWidget(bar, i, 1); self.prog_grid.addWidget(label(f"{p}%", "mono", bold=True, color=col), i, 2); self.prog_grid.addWidget(label(f"{d}/{t_} runs", "muted"), i, 3)
        self.prog_grid.setColumnStretch(1, 1)
        # what is left
        self.remaining.clear(); left = self.engine.remaining(); est = 0
        for r in left:
            it = QTreeWidgetItem([f"{r['testId']}  {r['title'][:48]}", f"{r['pendingRuns']}  ({', '.join(f'{u} ×{n}' for u, n in r['perUnit'].items())})", str(r["estMin"])])
            it.setData(0, Qt.UserRole, r["testId"]); it.setForeground(0, QColor(T.SUBSYSTEM.get(r["subsystem"], T.INK))); self.remaining.addTopLevelItem(it); est += r["estMin"]
        self.remaining_hint.setText(f"{len(left)} tests still owe runs · ≈ {est // 60} h {est % 60} min of bench time" if left else "Nothing left — every applicable run is committed.")
        self.donut.set_data([(n, s["tests"], T.SUBSYSTEM.get(n, T.MUTED)) for n, s in self.summary.items()])
        while self.legend.count():
            w = self.legend.takeAt(0).widget()
            if w: w.deleteLater()
        for i, (name, s) in enumerate(self.summary.items()):
            col = T.SUBSYSTEM.get(name, T.MUTED)
            sw = QLabel("●"); sw.setStyleSheet(f"color: {col}; font-size: 16px;")
            nm = QPushButton(f"{T.SUBSYSTEM_ICON.get(name, '')}  {name}"); nm.setProperty("kind", "link"); nm.setStyleSheet(f"color: {T.INK}; font-size: 13.5px;")
            nm.clicked.connect(lambda _, n=name: self.set_filter("" if self.filter == n else n))
            cnt = label(f"{s['tests']} tests", "muted"); pct = label(f"{100 * s['tests'] / (total or 1):.0f}%", bold=True, color=col)
            st = label(f"✓ {s['complete']}   ▶ {s['running']}   ✗ {s['failed']}   ○ {s['pending'] + s['blocked']}", "mono"); st.setStyleSheet(f"color: {T.MUTED}; font-family: Consolas;")
            for c_, w in enumerate((sw, nm, cnt, pct, st)): self.legend.addWidget(w, i, c_)
        self.legend.setColumnStretch(4, 1)
        self._fill_matrix()

    def set_filter(self, name: str):
        self.filter = name; self.donut.selected = name; self.donut.update(); self._fill_matrix()

    def _fill_matrix(self):
        self.tree.clear()
        for name, s in self.summary.items():
            if self.filter and name != self.filter: continue
            col = T.SUBSYSTEM.get(name, T.MUTED)
            top = QTreeWidgetItem([f"{T.SUBSYSTEM_ICON.get(name, '')}  {name.upper()}", f"{s['tests']} tests · {s['reps']} reps · {s['durationMin']} min", "", "",
                                   f"{s['complete']} complete · {s['running']} running · {s['failed']} failed · {s['pending'] + s['blocked']} pending", f"{s['pass']} PASS", "", "", ""])
            f = QFont("Segoe UI", 10, QFont.Bold)
            for c in range(9): top.setFont(c, f); top.setForeground(c, QColor(col if c == 0 else T.INK_2)); top.setBackground(c, QColor(T.CARD_2))
            self.tree.addTopLevelItem(top)
            for r in s["rows"]:
                it = QTreeWidgetItem([r["testId"], r["title"], r["method"], r["applicability"], STATUS_LABEL[r["status"]], r["result"] or "—",
                                      f"{r['runsDone']}/{r['runsTotal']}", str(r["reps"]), str(r["durationMin"] or "—")])
                it.setData(0, Qt.UserRole, r["testId"])
                it.setForeground(0, QColor(T.INFO)); it.setForeground(4, QColor(T.STATUS[r["status"]])); it.setForeground(5, QColor(T.VERDICT.get(r["result"] or "", T.MUTED)))
                if r["result"]:
                    fb = QFont(); fb.setBold(True); it.setFont(5, fb)
                top.addChild(it)
            top.setExpanded(True)
        tot = sum(s["tests"] for s in self.summary.values())
        run = sum(s["running"] for s in self.summary.values()); fail = sum(s["failed"] for s in self.summary.values()); comp = sum(s["complete"] for s in self.summary.values())
        self.matrix_hint.setText(f"{tot} tests · {run} running · {fail} failed · {comp} complete" + (f" · filter: {self.filter} (click again to clear)" if self.filter else ""))

    # ---------------- telemetry ----------------
    def on_dut(self, st):
        col = T.MODE.get("SIMULATION" if st.flags.get("simulated") else st.mode, T.MUTED)
        if not st.online:
            self.tele_status.setText(f"○ machine offline — {st.error or ''}"); self.tele_status.setStyleSheet(f"color: {T.MUTED};")
            for t in self.tiles.values(): t.push(None)
            for pl in self.inter.values(): pl.set("—", T.MUTED)
            return
        self.tele_status.setText(("◉ SIMULATION · " if st.flags.get("simulated") else "● live · ") + f"{st.mode} · sCure {st.version or ''}"); self.tele_status.setStyleSheet(f"color: {col}; font-weight: 600;")
        for k, t in self.tiles.items(): t.push(st.metrics.get(k))
        f = st.flags
        def mark(k, ok, good, bad):
            pl = self.inter[k]; pl.set("—", T.MUTED) if ok is None else pl.set(good if ok else bad, T.OK if ok else T.BAD)
        mark("door", None if f.get("doorOpen") is None else not f["doorOpen"], "✓ OK", "✗ OPEN")
        mark("uv", None if f.get("uvOn") is None else not f["uvOn"], "✓ OK", "● UV ON")
        mark("heater", None if f.get("isHeating") is None else not f["isHeating"], "✓ OK", "● HEATING")
        mark("fault", not f.get("fault"), "✓ OK", f"✗ {str(st.metrics.get('errorCode') or 'FAULT')}")

    def set_machine(self, url): pass          # compatibility: the app owns the machine connection

    def shutdown(self): pass
