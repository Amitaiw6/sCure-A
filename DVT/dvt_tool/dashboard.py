"""Dashboard page: test distribution by subsystem (donut), test matrix
grouped by subsystem, live telemetry + interlocks from the machine.

Pure Qt widgets — no chart library. The page is fed by Engine.subsystem_summary()
and re-renders on `refresh()`; telemetry comes from a background poller of
the machine's /api/state (the sCure hardware service on :3001).
"""

from __future__ import annotations

import json
import math
import urllib.request
from collections import deque

from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QTreeWidget,
                               QTreeWidgetItem, QHeaderView, QFrame, QSizePolicy, QPushButton, QLineEdit)

SUBSYSTEM_COLORS = {"Safety": "#e5533d", "Thermal": "#f0a030", "Electrical": "#3d8bf0", "Environmental": "#22b58a"}
SUBSYSTEM_ICONS = {"Safety": "⚠", "Thermal": "🌡", "Electrical": "⚡", "Environmental": "🚚"}
STATUS_COLORS = {"Complete": "#5cbf86", "Running": "#f5b942", "Failed": "#e06a60", "Pending": "#93a4b3", "Blocked": "#d9a93a"}
RESULT_COLORS = {"PASS": "#5cbf86", "FAIL": "#e06a60", "BLOCKED": "#d9a93a", "WAIVED": "#b39ddb"}
TELEMETRY = [  # key in /api/state, label, unit, colour, gauge range
    ("chamberTemp", "Chamber Temp", "°C", "#f0a030", (0, 100)),
    ("ledTempMax", "LED Back-Face", "°C", "#f5b942", (0, 100)),
    ("heaterFanRpm", "Heater Fan", "RPM", "#3d8bf0", (0, 7000)),
    ("ledFanRpm", "LED Fans", "RPM", "#22b58a", (0, 7000)),
]


# --------------------------------------------------------------------------
#  telemetry poller
# --------------------------------------------------------------------------
class TelemetryWorker(QThread):
    sample = Signal(dict)          # flattened metrics + flags
    offline = Signal(str)

    def __init__(self, url: str, interval_s: float = 2.0):
        super().__init__(); self.url, self.interval_s, self._stop = url.rstrip("/"), interval_s, False

    def run(self):
        while not self._stop:
            try:
                with urllib.request.urlopen(self.url + "/api/state", timeout=3) as r:
                    s = json.loads(r.read().decode())
                led = s.get("ledTemps") or s.get("ledTemperatures") or {}
                led_vals = [v for v in (led.values() if isinstance(led, dict) else led) if isinstance(v, (int, float))]
                rpm = s.get("fanRpm") or {}
                self.sample.emit({
                    "chamberTemp": s.get("chamberTemp"),
                    "ledTempMax": max(led_vals) if led_vals else s.get("ledTemp"),
                    "heaterFanRpm": rpm.get("chamber_heating"),
                    "ledFanRpm": rpm.get("led_cooling"),
                    "doorOpen": s.get("doorOpen"), "uvOn": s.get("uvOn"), "isHeating": s.get("isHeating"),
                    "fault": s.get("fault") or s.get("alerts"), "version": s.get("version"),
                })
            except Exception as e:  # noqa: BLE001
                self.offline.emit(str(e)[:80])
            self.msleep(int(self.interval_s * 1000))

    def stop(self):
        self._stop = True


# --------------------------------------------------------------------------
#  donut
# --------------------------------------------------------------------------
class DonutWidget(QWidget):
    sliceClicked = Signal(str)     # subsystem name, or "" for all

    def __init__(self):
        super().__init__()
        self.data: list[tuple[str, int, str]] = []     # (name, count, colour)
        self.selected = ""
        self.setMinimumSize(190, 190)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._spans: list[tuple[str, float, float]] = []

    def set_data(self, data):
        self.data = data; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        total = sum(c for _, c, _ in self.data) or 1
        side = min(self.width(), self.height()) - 8
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        start = 90 * 16
        self._spans = []
        for name, count, colour in self.data:
            span = -int(round(360 * 16 * count / total))
            pen = QPen(QColor(colour), 30 if name != self.selected else 38); pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            r = rect.adjusted(20, 20, -20, -20)
            p.drawArc(r, start, span)
            self._spans.append((name, start / 16, span / 16)); start += span
        p.setPen(QColor("#e6ebf0")); f = QFont("Segoe UI", 20, QFont.Bold); p.setFont(f)
        p.drawText(rect, Qt.AlignCenter, str(sum(c for _, c, _ in self.data)))
        f = QFont("Segoe UI", 8); p.setFont(f); p.setPen(QColor("#93a4b3"))
        p.drawText(rect.adjusted(0, 34, 0, 0), Qt.AlignCenter, "DVT TESTS")

    def mousePressEvent(self, ev):
        c = QPointF(self.width() / 2, self.height() / 2); d = ev.position() - c
        ang = math.degrees(math.atan2(-d.y(), d.x())) % 360        # Qt arcs: 0° = 3 o'clock, CCW positive
        for name, start, span in self._spans:                        # span negative = clockwise
            a0, a1 = start % 360, (start + span) % 360
            hit = (a1 <= ang <= a0) if a1 <= a0 else (ang <= a0 or ang >= a1)
            if hit:
                self.selected = "" if self.selected == name else name
                self.sliceClicked.emit(self.selected); self.update(); return
        self.selected = ""; self.sliceClicked.emit(""); self.update()


# --------------------------------------------------------------------------
#  sparkline + gauge tile
# --------------------------------------------------------------------------
class TelemetryTile(QWidget):
    def __init__(self, label: str, unit: str, colour: str, rng: tuple[float, float]):
        super().__init__()
        self.label, self.unit, self.colour, self.rng = label, unit, QColor(colour), rng
        self.values: deque[float] = deque(maxlen=60)
        self.value: float | None = None
        self.setMinimumHeight(74); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def push(self, v):
        if isinstance(v, (int, float)) and math.isfinite(v):
            self.value = float(v); self.values.append(self.value)
        else:
            self.value = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # gauge arc (left)
        g = QRectF(6, 12, 56, 56)
        pen = QPen(QColor("#26313a"), 6); pen.setCapStyle(Qt.RoundCap); p.setPen(pen); p.drawArc(g, 225 * 16, -270 * 16)
        if self.value is not None:
            lo, hi = self.rng; frac = max(0.0, min(1.0, (self.value - lo) / (hi - lo)))
            pen.setColor(self.colour); p.setPen(pen); p.drawArc(g, 225 * 16, -int(270 * 16 * frac))
        # label + value
        p.setPen(QColor("#93a4b3")); p.setFont(QFont("Segoe UI", 8)); p.drawText(72, 16, f"{self.label} ({self.unit})")
        p.setPen(self.colour); p.setFont(QFont("Segoe UI", 15, QFont.Bold))
        p.drawText(72, 38, "—" if self.value is None else (f"{self.value:.0f}" if self.unit == "RPM" else f"{self.value:.2f}"))
        # sparkline (right)
        if len(self.values) >= 2:
            x0, x1, y0, y1 = 72, w - 8, 46, h - 6
            lo, hi = min(self.values), max(self.values); span = (hi - lo) or 1.0
            path = QPainterPath()
            for i, v in enumerate(self.values):
                x = x0 + (x1 - x0) * i / (self.values.maxlen - 1)
                y = y1 - (y1 - y0) * (v - lo) / span
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.setPen(QPen(self.colour, 1.5)); p.setBrush(Qt.NoBrush); p.drawPath(path)


# --------------------------------------------------------------------------
#  page
# --------------------------------------------------------------------------
class DashboardPage(QWidget):
    openTest = Signal(str)          # test_id double-clicked in the matrix

    def __init__(self, engine, machine_url: str = "http://testingcm5.local:3001"):
        super().__init__()
        self.engine = engine
        self.filter = ""
        self.summary: dict = {}
        self._build(machine_url)
        self.tw = None
        self.set_machine(machine_url)

    # ---------------- layout ----------------
    def _build(self, machine_url):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(12)
        centre = QVBoxLayout(); centre.setSpacing(12); root.addLayout(centre, 3)

        # header strip
        strip = QHBoxLayout()
        self.kpis = {}
        for key, label in (("tests", "TESTS"), ("running", "RUNNING"), ("failed", "FAILED"), ("complete", "COMPLETE"), ("runs", "RUNS DONE")):
            box = QFrame(); box.setStyleSheet("QFrame { background: #171f26; border: 1px solid #2a353f; border-radius: 8px; }")
            l = QVBoxLayout(box); l.setContentsMargins(12, 8, 12, 8)
            v = QLabel("—"); v.setFont(QFont("Segoe UI", 18, QFont.Bold)); k = QLabel(label); k.setStyleSheet("color: #93a4b3; font-size: 10px; letter-spacing: 1px;")
            l.addWidget(v); l.addWidget(k); strip.addWidget(box); self.kpis[key] = v
        centre.addLayout(strip)

        # distribution
        g = QGroupBox("TEST DISTRIBUTION BY SUBSYSTEM"); gl = QHBoxLayout(g)
        self.donut = DonutWidget(); self.donut.sliceClicked.connect(self.set_filter); gl.addWidget(self.donut)
        self.legend = QGridLayout(); self.legend.setHorizontalSpacing(18); gl.addLayout(self.legend, 1)
        self.legend_hint = QLabel("click a slice or legend row to filter"); self.legend_hint.setStyleSheet("color: #93a4b3; font-size: 11px;")
        gl.addWidget(self.legend_hint, 0, Qt.AlignTop | Qt.AlignRight)
        centre.addWidget(g)

        # matrix
        g = QGroupBox("TEST MATRIX — GROUPED BY SUBSYSTEM"); gl = QVBoxLayout(g)
        self.matrix_hint = QLabel(""); self.matrix_hint.setStyleSheet("color: #93a4b3; font-size: 11px;"); gl.addWidget(self.matrix_hint, 0, Qt.AlignRight)
        self.tree = QTreeWidget(); self.tree.setColumnCount(9)
        self.tree.setHeaderLabels(["ID / Subsystem", "Test name", "Method", "Appl.", "Status", "Result", "Runs", "Reps", "Est (min)"])
        hdr = self.tree.header(); hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4, 5, 6, 7, 8): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tree.setRootIsDecorated(True); self.tree.setAlternatingRowColors(False)
        self.tree.itemDoubleClicked.connect(lambda it, _: it.data(0, Qt.UserRole) and self.openTest.emit(it.data(0, Qt.UserRole)))
        gl.addWidget(self.tree, 1); centre.addWidget(g, 1)

        # right column: telemetry + interlocks
        right = QVBoxLayout(); right.setSpacing(12); root.addLayout(right, 1)
        g = QGroupBox("LIVE TELEMETRY"); gl = QVBoxLayout(g)
        row = QHBoxLayout(); self.machine = QLineEdit(machine_url); self.machine.setPlaceholderText("http://<machine>:3001")
        b = QPushButton("Connect"); b.setProperty("secondary", True); b.clicked.connect(lambda: self.set_machine(self.machine.text().strip()))
        row.addWidget(self.machine); row.addWidget(b); gl.addLayout(row)
        self.tele_status = QLabel("connecting…"); self.tele_status.setStyleSheet("color: #93a4b3; font-size: 11px;"); gl.addWidget(self.tele_status)
        self.tiles = {}
        for key, label, unit, colour, rng in TELEMETRY:
            t = TelemetryTile(label, unit, colour, rng); gl.addWidget(t); self.tiles[key] = t
        right.addWidget(g)
        g = QGroupBox("SAFETY & INTERLOCKS"); self.inter = QGridLayout(g)
        self.inter_rows = {}
        for i, (key, label) in enumerate((("door", "Door closed"), ("uv", "UV off"), ("heater", "Heater off"), ("fault", "No active fault"))):
            self.inter.addWidget(QLabel(label), i, 0); v = QLabel("—"); v.setAlignment(Qt.AlignRight); self.inter.addWidget(v, i, 1); self.inter_rows[key] = v
        right.addWidget(g); right.addStretch()

    # ---------------- data ----------------
    def refresh(self):
        self.summary = self.engine.subsystem_summary()
        total = sum(s["tests"] for s in self.summary.values())
        self.kpis["tests"].setText(str(total))
        self.kpis["running"].setText(str(sum(s["running"] for s in self.summary.values())))
        self.kpis["failed"].setText(str(sum(s["failed"] for s in self.summary.values())))
        self.kpis["complete"].setText(str(sum(s["complete"] for s in self.summary.values())))
        prog = self.engine.progress(); self.kpis["runs"].setText(f"{prog['done']}/{prog['total']}")
        self.kpis["failed"].setStyleSheet(f"color: {'#e06a60' if int(self.kpis['failed'].text()) else '#e6ebf0'};")
        self.donut.set_data([(name, s["tests"], SUBSYSTEM_COLORS.get(name, "#93a4b3")) for name, s in self.summary.items()])
        # legend
        while self.legend.count():
            w = self.legend.takeAt(0).widget()
            if w: w.deleteLater()
        for i, (name, s) in enumerate(self.summary.items()):
            col = SUBSYSTEM_COLORS.get(name, "#93a4b3")
            sw = QLabel("■"); sw.setStyleSheet(f"color: {col}; font-size: 14px;")
            nm = QPushButton(f"{SUBSYSTEM_ICONS.get(name, '')} {name}"); nm.setProperty("secondary", True); nm.setFlat(True)
            nm.setStyleSheet("QPushButton { background: transparent; color: #e6ebf0; text-align: left; font-weight: 600; padding: 2px 4px; }")
            nm.clicked.connect(lambda _, n=name: self.set_filter("" if self.filter == n else n))
            cnt = QLabel(f"{s['tests']} tests"); pct = QLabel(f"{100 * s['tests'] / (total or 1):.0f}%"); pct.setStyleSheet(f"color: {col}; font-weight: 700;")
            st = QLabel(f"✓ {s['complete']}  ▶ {s['running']}  ✗ {s['failed']}  … {s['pending'] + s['blocked']}"); st.setStyleSheet("color: #93a4b3; font-family: Consolas;")
            for c, w in enumerate((sw, nm, cnt, pct, st)):
                self.legend.addWidget(w, i, c)
        self._fill_matrix()

    def set_filter(self, name: str):
        self.filter = name; self.donut.selected = name; self.donut.update(); self._fill_matrix()

    def _fill_matrix(self):
        self.tree.clear()
        shown = 0
        for name, s in self.summary.items():
            if self.filter and name != self.filter:
                continue
            col = SUBSYSTEM_COLORS.get(name, "#93a4b3")
            top = QTreeWidgetItem([f"{SUBSYSTEM_ICONS.get(name, '')} {name.upper()}",
                                   f"{s['tests']} tests · {s['reps']} reps · {s['durationMin']} min",
                                   "", "", f"{s['complete']} complete / {s['running']} running / {s['failed']} failed / {s['pending'] + s['blocked']} pending",
                                   f"{s['pass']} PASS", "", "", ""])
            f = QFont("Segoe UI", 10, QFont.Bold)
            for c in range(9):
                top.setFont(c, f); top.setForeground(c, QColor(col if c == 0 else "#c5d0da")); top.setBackground(c, QColor("#151c22"))
            self.tree.addTopLevelItem(top)
            for r in s["rows"]:
                it = QTreeWidgetItem([r["testId"], r["title"], r["method"], r["applicability"],
                                      {"Complete": "✓ Complete", "Running": "▶ Running", "Failed": "✗ Failed", "Blocked": "⊘ Blocked", "Pending": "⏸ Pending"}[r["status"]],
                                      r["result"] or "—", f"{r['runsDone']}/{r['runsTotal']}", str(r["reps"]), str(r["durationMin"] or "—")])
                it.setData(0, Qt.UserRole, r["testId"])
                it.setForeground(0, QColor("#3fb8ba")); it.setForeground(4, QColor(STATUS_COLORS[r["status"]]))
                it.setForeground(5, QColor(RESULT_COLORS.get(r["result"] or "", "#93a4b3")))
                it.setForeground(8, QColor("#3d8bf0"))
                if r["result"]:
                    fb = QFont(); fb.setBold(True); it.setFont(5, fb)
                top.addChild(it); shown += 1
            top.setExpanded(True)
        tot = sum(s["tests"] for s in self.summary.values())
        run = sum(s["running"] for s in self.summary.values()); fail = sum(s["failed"] for s in self.summary.values()); comp = sum(s["complete"] for s in self.summary.values())
        self.matrix_hint.setText(f"{tot} Tests · {run} Running · {fail} Failed · {comp} Complete" + (f" · filter: {self.filter}" if self.filter else ""))

    # ---------------- telemetry ----------------
    def set_machine(self, url: str):
        if self.tw:
            self.tw.stop(); self.tw.wait(3000)
        if not url:
            self.tele_status.setText("no machine configured"); return
        self.tw = TelemetryWorker(url); self.tw.sample.connect(self._on_sample); self.tw.offline.connect(self._on_offline); self.tw.start()
        self.tele_status.setText(f"connecting to {url}…")

    def _on_sample(self, s: dict):
        self.tele_status.setText(f"● live · sCure {s.get('version') or ''}"); self.tele_status.setStyleSheet("color: #5cbf86; font-size: 11px;")
        for key, t in self.tiles.items():
            t.push(s.get(key))
        def mark(key, ok, txt_ok, txt_bad):
            lb = self.inter_rows[key]
            if ok is None:
                lb.setText("—"); lb.setStyleSheet("color: #93a4b3;")
            else:
                lb.setText(txt_ok if ok else txt_bad); lb.setStyleSheet(f"color: {'#5cbf86' if ok else '#e06a60'}; font-weight: 700;")
        mark("door", None if s.get("doorOpen") is None else not s["doorOpen"], "✓ OK", "✗ OPEN")
        mark("uv", None if s.get("uvOn") is None else not s["uvOn"], "✓ OK", "● UV ON")
        mark("heater", None if s.get("isHeating") is None else not s["isHeating"], "✓ OK", "● HEATING")
        mark("fault", None if s.get("fault") is None else not s["fault"], "✓ OK", f"✗ {str(s.get('fault'))[:24]}")

    def _on_offline(self, err: str):
        self.tele_status.setText(f"○ machine offline ({err})"); self.tele_status.setStyleSheet("color: #93a4b3; font-size: 11px;")
        for t in self.tiles.values():
            t.push(None)
        for lb in self.inter_rows.values():
            lb.setText("—"); lb.setStyleSheet("color: #93a4b3;")

    def shutdown(self):
        if self.tw:
            self.tw.stop(); self.tw.wait(3000)
