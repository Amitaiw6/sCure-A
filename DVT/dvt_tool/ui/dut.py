"""DUT (device under test) — the sCure machine the campaign runs against.

    DutClient    HTTP client for the machine's hardware service (:3001)
    DutMonitor   background poller emitting flattened live state
    DutPanel     "DUT Control" page: connect, live state, safe controls
    FIELD_MAP    which catalog data fields can be filled from live state

The URL is chosen by the operator (header field / DUT page) and persisted
in the campaign store (`machine_url`). Every control action is confirmed
and logged in the campaign events (SRS traceability).
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton,
                               QMessageBox, QSizePolicy, QComboBox, QInputDialog)

from . import theme as T
from .widgets import Card, Pill, PulseDot, label

# data-field name (or suffix) -> live metric key.  The wizard offers an
# "⇩ from DUT" button next to any field that maps.
FIELD_MAP = {
    "chamber_temp": "chamberTemp", "max_chamber_temp": "chamberTemp", "start_temp": "chamberTemp",
    "ambient_temp": "ambientTemp", "peak_temp": "chamberTemp", "plateau_temp": "chamberTemp",
    "max_temp_reached": "chamberTemp", "chamber_temp_at_trip": "chamberTemp", "min_temp_reached": "chamberTemp",
    "max_led_temp": "ledTempMax", "peak_heater_temp": "heaterTemp",
    "max_temp_right": "ledTempRight", "max_temp_left": "ledTempLeft", "max_temp_back": "ledTempBack", "max_temp_door": "ledTempDoor",
    "baseline_tach": "ledFanRpm", "tach_reading": "ledFanRpm", "tach_at_alarm": "ledFanRpm",
    "error_code": "errorCode", "alarm_text": "alertText",
}


@dataclass
class DutState:
    online: bool = False
    url: str = ""
    version: str | None = None
    metrics: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def mode(self) -> str:
        if not self.online: return "OFFLINE"
        if self.flags.get("fault"): return "FAULT"
        if self.flags.get("uvOn"): return "CURING"
        if self.flags.get("isHeating"): return "HEATING"
        if self.flags.get("isCooling"): return "COOLING"
        return "IDLE"


class DutClient:
    def __init__(self, url: str, timeout: float = 4.0):
        self.url, self.timeout = url.rstrip("/"), timeout

    def _req(self, path: str, method="GET", body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode() or "{}")

    def state(self) -> DutState:
        try:
            s = self._req("/api/state")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            return DutState(False, self.url, error=str(e)[:90])
        led = s.get("ledTemps") or s.get("ledTemperatures") or {}
        led_map = led if isinstance(led, dict) else {}
        led_vals = [v for v in led_map.values() if isinstance(v, (int, float))]
        rpm = s.get("fanRpm") or {}
        alerts = s.get("alerts") or s.get("activeAlerts") or []
        first = alerts[0] if isinstance(alerts, list) and alerts else None
        metrics = {
            "chamberTemp": s.get("chamberTemp"), "ambientTemp": s.get("ambientTemp"), "heaterTemp": s.get("heaterTemp"),
            "ledTempMax": max(led_vals) if led_vals else s.get("ledTemp"),
            "ledTempRight": led_map.get("right") or led_map.get("LED_RIGHT"), "ledTempLeft": led_map.get("left") or led_map.get("LED_LEFT"),
            "ledTempBack": led_map.get("back") or led_map.get("LED_BACK"), "ledTempDoor": led_map.get("door") or led_map.get("LED_DOOR"),
            "heaterFanRpm": rpm.get("chamber_heating"), "ledFanRpm": rpm.get("led_cooling"), "intakeFanRpm": rpm.get("chamber_intake"),
            "targetTemp": s.get("targetTemp"), "uvIntensity": s.get("uvIntensity"),
            "errorCode": (first.get("code") if isinstance(first, dict) else first) if first else None,
            "alertText": (first.get("message") if isinstance(first, dict) else None) if first else None,
        }
        flags = {"doorOpen": s.get("doorOpen"), "uvOn": s.get("uvOn"), "isHeating": s.get("isHeating"),
                 "isCooling": s.get("isCooling"), "fault": bool(s.get("fault")) or bool(alerts), "internetOk": s.get("internetOk")}
        return DutState(True, self.url, s.get("version"), metrics, flags)

    # ---- controls (the sCure hardware API) ----
    def heat(self, target_c: float): return self._req(f"/api/cure/heat?target={target_c}", "POST")
    def cool(self, target_c: float, mode="normal"): return self._req(f"/api/cure/cool?target={target_c}&mode={mode}", "POST")
    def stop(self): return self._req("/api/cure/stop", "POST")
    def uv(self, on: bool, intensity: int = 50, wavelength: int = 405):
        return self._req("/api/uv", "POST", {"on": on, "intensity": intensity, "wavelength": wavelength})
    def door_open(self): return self._req("/api/door/open", "POST")
    def fan(self, name: str, speed: int): return self._req(f"/api/fans/{name}?speed={speed}", "POST")
    def led_test(self): return self._req("/api/diagnostics/led-test", "POST")
    def fan_test(self): return self._req("/api/diagnostics/fan-test", "POST")
    def version(self):
        try: return self._req("/api/system/version")
        except Exception: return {}  # noqa: BLE001


class DutMonitor(QThread):
    state = Signal(object)          # DutState

    def __init__(self, url: str, interval_s: float = 2.0):
        super().__init__(); self.client = DutClient(url); self.interval_s = interval_s; self._stop = False

    def run(self):
        while not self._stop:
            self.state.emit(self.client.state())
            for _ in range(int(self.interval_s * 10)):      # interruptible sleep: stop() returns within ~100 ms
                if self._stop: break
                self.msleep(100)

    def stop(self):
        self._stop = True
        self.requestInterruption()


# --------------------------------------------------------------------------
#  gauge + sparkline tile (shared by dashboard and DUT page)
# --------------------------------------------------------------------------
class MetricTile(QWidget):
    def __init__(self, caption: str, unit: str, color: str, rng: tuple[float, float]):
        super().__init__(); self.caption, self.unit, self.color, self.rng = caption, unit, QColor(color), rng
        self.values: deque[float] = deque(maxlen=90); self.value = None
        self.setMinimumHeight(78); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def push(self, v):
        if isinstance(v, (int, float)) and math.isfinite(v):
            self.value = float(v); self.values.append(self.value)
        else:
            self.value = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); w, h = self.width(), self.height()
        g = QRectF(6, 12, 58, 58); pen = QPen(QColor(T.CARD_2), 6); pen.setCapStyle(Qt.RoundCap); p.setPen(pen); p.drawArc(g, 225 * 16, -270 * 16)
        if self.value is not None:
            lo, hi = self.rng; frac = max(0.0, min(1.0, (self.value - lo) / (hi - lo)))
            pen.setColor(self.color); p.setPen(pen); p.drawArc(g, 225 * 16, -int(270 * 16 * frac))
        p.setPen(QColor(T.MUTED)); p.setFont(QFont("Segoe UI", 8)); p.drawText(76, 16, f"{self.caption} ({self.unit})")
        p.setPen(self.color); p.setFont(QFont("Segoe UI", 16, QFont.Bold))
        p.drawText(76, 40, "—" if self.value is None else (f"{self.value:.0f}" if self.unit in ("RPM", "%") else f"{self.value:.1f}"))
        if len(self.values) >= 2:
            x0, x1, y0, y1 = 76, w - 8, 48, h - 6; lo, hi = min(self.values), max(self.values); span = (hi - lo) or 1.0
            path = QPainterPath()
            for i, v in enumerate(self.values):
                x = x0 + (x1 - x0) * i / (self.values.maxlen - 1); y = y1 - (y1 - y0) * (v - lo) / span
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.setPen(QPen(self.color, 1.6)); p.drawPath(path)


TILES = [("chamberTemp", "Chamber Temp", "°C", T.SUBSYSTEM["Thermal"], (0, 100)),
         ("ledTempMax", "LED Back-Face", "°C", T.WARN, (0, 100)),
         ("heaterFanRpm", "Heater Fan", "RPM", T.INFO, (0, 7000)),
         ("ledFanRpm", "LED Fans", "RPM", T.OK, (0, 7000)),
         ("intakeFanRpm", "Intake Fan", "RPM", T.ACCENT, (0, 7000))]


# --------------------------------------------------------------------------
#  DUT Control page
# --------------------------------------------------------------------------
class DutPanel(QWidget):
    """Connect to a machine, watch it, and drive it safely between test steps."""

    def __init__(self, app):
        super().__init__(); self.app = app; self.state = DutState()
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        left = QVBoxLayout(); left.setSpacing(14); root.addLayout(left, 3)
        c = Card("Device under test"); left.addWidget(c)
        row = QHBoxLayout(); row.addWidget(label("Machine address", "muted"))
        self.url = QComboBox(); self.url.setEditable(True); self.url.setMinimumWidth(320)
        for u in app.known_machines(): self.url.addItem(u)
        self.url.setCurrentText(app.machine_url); row.addWidget(self.url, 1)
        b = QPushButton("Connect"); b.clicked.connect(lambda: app.set_machine(self.url.currentText().strip())); row.addWidget(b)
        b = QPushButton("Discover"); b.setProperty("kind", "ghost"); b.clicked.connect(self.discover); row.addWidget(b)
        c.body.addLayout(row)
        st = QHBoxLayout(); self.dot = PulseDot(T.MUTED); st.addWidget(self.dot); self.p_mode = Pill("OFFLINE", T.MUTED); st.addWidget(self.p_mode)
        self.lbl_ver = label("", "muted"); st.addWidget(self.lbl_ver); st.addStretch(); c.body.addLayout(st)
        self.lbl_err = label("", "muted"); self.lbl_err.setWordWrap(True); c.body.addWidget(self.lbl_err)

        c = Card("Live state"); grid = QGridLayout(); grid.setHorizontalSpacing(14); c.body.addLayout(grid); left.addWidget(c)
        self.tiles = {}
        for i, (key, cap, unit, col, rng) in enumerate(TILES):
            t = MetricTile(cap, unit, col, rng); grid.addWidget(t, i // 2, i % 2); self.tiles[key] = t
        self.inter = {}
        c2 = Card("Safety & interlocks"); g2 = QGridLayout(); c2.body.addLayout(g2); left.addWidget(c2)
        for i, (k, txt) in enumerate((("door", "Door closed"), ("uv", "UV off"), ("heater", "Heater off"), ("fault", "No active fault"))):
            g2.addWidget(label(txt), i, 0); pl = Pill("—", T.MUTED); g2.addWidget(pl, i, 1, alignment=Qt.AlignRight); self.inter[k] = pl
        left.addStretch()

        right = QVBoxLayout(); right.setSpacing(14); root.addLayout(right, 2)
        c = Card("Controls", hint="every action is confirmed and logged"); right.addWidget(c)
        c.body.addWidget(label("Used between wizard steps to bring the machine to the state a step needs (e.g. 'chamber in HEAT mode at 80 °C, steady').", "muted", wrap=True))
        g = QGridLayout(); g.setSpacing(8); c.body.addLayout(g)
        self.ed_target = QLineEdit("80"); self.ed_target.setFixedWidth(70)
        g.addWidget(label("Target °C"), 0, 0); g.addWidget(self.ed_target, 0, 1)
        b = QPushButton("Heat to target"); b.clicked.connect(lambda: self._act("heat", lambda c: c.heat(float(self.ed_target.text())))); g.addWidget(b, 0, 2)
        self.cb_mode = QComboBox(); self.cb_mode.addItems(["fast", "normal", "slow"]); g.addWidget(self.cb_mode, 1, 1)
        b = QPushButton("Cool to target"); b.clicked.connect(lambda: self._act("cool", lambda c: c.cool(float(self.ed_target.text()), self.cb_mode.currentText()))); g.addWidget(b, 1, 2)
        self.ed_uv = QLineEdit("50"); self.ed_uv.setFixedWidth(70); g.addWidget(label("UV %"), 2, 0); g.addWidget(self.ed_uv, 2, 1)
        b = QPushButton("UV on (405 nm)"); b.clicked.connect(lambda: self._act("uv on", lambda c: c.uv(True, int(self.ed_uv.text())))); g.addWidget(b, 2, 2)
        b = QPushButton("UV off"); b.setProperty("kind", "ghost"); b.clicked.connect(lambda: self._act("uv off", lambda c: c.uv(False))); g.addWidget(b, 3, 2)
        b = QPushButton("Open door"); b.setProperty("kind", "ghost"); b.clicked.connect(lambda: self._act("door open", lambda c: c.door_open())); g.addWidget(b, 4, 2)
        b = QPushButton("STOP — all off"); b.setProperty("kind", "danger"); b.clicked.connect(lambda: self._act("stop", lambda c: c.stop(), confirm=False)); g.addWidget(b, 5, 0, 1, 3)
        c = Card("Diagnostics"); right.addWidget(c)
        row = QHBoxLayout()
        b = QPushButton("LED test"); b.setProperty("kind", "ghost"); b.clicked.connect(lambda: self._act("led-test", lambda c: c.led_test())); row.addWidget(b)
        b = QPushButton("Fan test"); b.setProperty("kind", "ghost"); b.clicked.connect(lambda: self._act("fan-test", lambda c: c.fan_test())); row.addWidget(b)
        c.body.addLayout(row)
        self.out = label("", "mono"); self.out.setWordWrap(True); self.out.setStyleSheet(f"color: {T.MUTED}; font-family: Consolas; font-size: 11px;"); c.body.addWidget(self.out)
        right.addStretch()

    def discover(self):
        """Try the known hostnames / the last IPs and pick the first that answers."""
        cands = self.app.known_machines() + ["http://testingcm5.local:3001", "http://127.0.0.1:3001"]
        for u in dict.fromkeys(cands):
            if DutClient(u, 1.5).state().online:
                self.url.setCurrentText(u); self.app.set_machine(u); return
        QMessageBox.information(self, "Discover", "No sCure machine answered. Enter its address (http://<ip>:3001) and press Connect.")

    def _act(self, name, fn, confirm=True):
        if not self.state.online:
            QMessageBox.warning(self, "DUT", "Not connected to a machine."); return
        if confirm and QMessageBox.question(self, "DUT control", f"Send '{name}' to {self.state.url}?") != QMessageBox.Yes:
            return
        try:
            res = fn(DutClient(self.state.url)); self.out.setText(f"{name}: {json.dumps(res)[:300]}")
            self.app.store.log(f"DUT control: {name}", self.app.operator, self.app.current_run_id(), {"url": self.state.url, "result": res})
        except Exception as e:  # noqa: BLE001
            self.out.setText(f"{name}: ERROR {e}")

    def on_state(self, st: DutState):
        self.state = st
        col = {"OFFLINE": T.MUTED, "FAULT": T.BAD, "CURING": T.WARN, "HEATING": T.WARN, "COOLING": T.INFO, "IDLE": T.OK}[st.mode]
        self.dot.set_color(col); self.p_mode.set(st.mode, col)
        self.lbl_ver.setText(f"sCure {st.version or ''} · {st.url}" if st.online else st.url)
        self.lbl_err.setText("" if st.online else (st.error or ""))
        for k, t in self.tiles.items():
            t.push(st.metrics.get(k) if st.online else None)
        def mark(k, ok, good, bad):
            pl = self.inter[k]
            pl.set("—", T.MUTED) if ok is None else pl.set(good if ok else bad, T.OK if ok else T.BAD)
        f = st.flags if st.online else {}
        mark("door", None if f.get("doorOpen") is None else not f["doorOpen"], "✓ CLOSED", "✗ OPEN")
        mark("uv", None if f.get("uvOn") is None else not f["uvOn"], "✓ OFF", "● ON")
        mark("heater", None if f.get("isHeating") is None else not f["isHeating"], "✓ OFF", "● HEATING")
        mark("fault", None if not st.online else not f.get("fault"), "✓ NONE", "✗ FAULT")
