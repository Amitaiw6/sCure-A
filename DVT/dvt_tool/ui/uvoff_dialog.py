"""Instrumented UV-off measurement dialog — Ophir StarBright + machine.

Opened from the wizard on a catalog step that carries a `tool:` key:

    tool: uv_off_timing    DVT-SAF-008  trigger = the door opens         (uv_off_time  <= 1 s)
    tool: led_off_timing   DVT-SAF-004  trigger = LED thermistor pulled  (led_off_time <= 2 s)

The dialog drives the whole sequence: LEDs at maximum → trigger → irradiance
recorded against time → graph. On "Apply to run" the CSV and PNG are attached
to the run and the captured fields are handed back to the wizard.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, QLineEdit,
                               QSpinBox, QLabel, QMessageBox, QSizePolicy)

from . import theme as T
from .widgets import Card, Pill, label
from .i18n import tr, trf
from ..instruments.ophir import open_meter, list_serial_ports, MeterError
from ..instruments.uvoff import UvOffRunner, UvOffConfig, UvOffResult, TRIGGERS, TOOL_TRIGGERS, LED_POSITIONS, write_csv, plot_png  # noqa: F401

# per-trigger UI text (English source strings; translated by i18n)
_UI = {
    "door": {
        "title": "DVT-SAF-008 — UV-off timing with the Ophir StarBright",
        "headline": "LEDs at maximum → door opened → irradiance recorded against time",
        "intro": "Put the Ophir sensor at the door opening, facing the LEDs. UV eyewear on. The sequence is automatic: baseline, LEDs on, plateau, door, decay, LEDs off. Pass criterion: UV removed within 1 s of the door opening.",
        "auto": "Automatic — release the door via the API", "operator": "Operator opens the door on the prompt",
        "trigger_caption": "Door", "marker": "The door is open", "result_caption": "Door open",
    },
    "led_thermistor": {
        "title": "DVT-SAF-004 — LED-off timing on thermistor disconnect with the Ophir StarBright",
        "headline": "LEDs at maximum → LED thermistor disconnected → irradiance recorded against time",
        "intro": "Put the Ophir sensor at the door opening, facing the LEDs, door closed. UV eyewear on. The sequence is automatic: baseline, LEDs on, plateau, then pull the connector of the selected LED thermistor when prompted and press the marker (in simulation the fault is injected for you). Pass criterion: LED drive removed within 2 s of the disconnection; the alarm must name the sensor.",
        "auto": "Automatic — inject the open-thermistor fault (simulator only)", "operator": "Operator pulls the thermistor connector on the prompt",
        "trigger_caption": "Thermistor", "marker": "The thermistor is disconnected", "result_caption": "Disconnected",
    },
}


class UvOffWorker(QThread):
    status = Signal(str, str)
    sample = Signal(object)
    done = Signal(object)

    def __init__(self, dut, meter, cfg: UvOffConfig):
        super().__init__()
        self.runner = UvOffRunner(dut, meter, cfg, on_status=lambda p, t: self.status.emit(p, t), on_sample=lambda s: self.sample.emit(s))

    def run(self):
        self.done.emit(self.runner.run())


class TraceWidget(QWidget):
    """Live irradiance trace — the last `window_s` seconds, trigger marker in red."""

    def __init__(self, window_s: float = 8.0):
        super().__init__(); self.window_s = window_s; self.pts: deque = deque(maxlen=4000); self.t_trigger = None; self.unit = ""
        self.setMinimumHeight(170); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def push(self, t, v):
        self.pts.append((t, v)); self.update()

    def clear(self):
        self.pts.clear(); self.t_trigger = None; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8, 8, -8, -8)
        p.fillRect(self.rect(), QColor(T.CARD)); p.setPen(QPen(QColor(T.LINE), 1)); p.drawRect(r)
        if len(self.pts) < 2:
            p.setPen(QColor(T.MUTED)); p.drawText(r, Qt.AlignCenter, tr("waiting for readings…")); return
        t1 = self.pts[-1][0]; t0 = t1 - self.window_s
        pts = [(t, v) for t, v in self.pts if t >= t0]
        vmax = max(v for _, v in pts) or 1.0
        def X(t): return r.left() + (t - t0) / self.window_s * r.width()
        def Y(v): return r.bottom() - min(1.0, v / (vmax * 1.08)) * r.height()
        if self.t_trigger is not None and self.t_trigger >= t0:
            p.setPen(QPen(QColor(T.BAD), 2)); p.drawLine(int(X(self.t_trigger)), r.top(), int(X(self.t_trigger)), r.bottom())
        p.setPen(QPen(QColor(T.PURPLE), 2))
        last = None
        for t, v in pts:
            cur = (X(t), Y(v))
            if last: p.drawLine(int(last[0]), int(last[1]), int(cur[0]), int(cur[1]))
            last = cur
        p.setPen(QColor(T.MUTED)); p.drawText(QRectF(r.left() + 6, r.top() + 4, 260, 18), Qt.AlignLeft, f"{pts[-1][1]:.3g} {self.unit}   max {vmax:.3g}")


class UvOffDialog(QDialog):
    applied = Signal(dict, list)       # (field values, attached file paths)

    def __init__(self, app, run: dict | None = None, parent=None, trigger: str = "door", defaults: dict | None = None):
        super().__init__(parent)
        if trigger not in TRIGGERS:
            raise ValueError(f"unknown trigger {trigger!r}")
        self.app, self.run, self.store, self.trigger = app, run, app.store, trigger
        self.spec, self.ui, self.defaults = TRIGGERS[trigger], _UI[trigger], defaults or {}
        self.result: UvOffResult | None = None; self.worker: UvOffWorker | None = None; self.files: list[Path] = []
        self.setWindowTitle(tr(self.ui["title"]))
        from .screen import fit
        fit(self, 1080, 840)                       # never larger than the screen's work area (150 % laptops: 1280x688 logical)
        self._build()

    @property
    def test_id(self) -> str:
        return self.spec["test_id"]

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(10)
        head = QVBoxLayout(); root.addLayout(head)
        head.addWidget(label(self.run["run_id"] if self.run else tr("stand-alone measurement (no run selected)"), "eyebrow"))
        head.addWidget(label(tr(self.ui["headline"]), "h2"))
        head.addWidget(label(tr(self.ui["intro"]), "muted", wrap=True))

        top = QHBoxLayout(); root.addLayout(top)
        # --- meter
        c = Card(tr("Meter")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 1)
        self.cb_backend = QComboBox()
        for key, txt in (("sim", tr("Simulated meter (rehearsal)")), ("starlab", tr("Ophir StarBright — StarLab USB")), ("serial", tr("Ophir StarBright — serial port"))):
            self.cb_backend.addItem(txt, key)
        g.addWidget(label(tr("Backend"), "muted"), 0, 0); g.addWidget(self.cb_backend, 0, 1, 1, 2)
        self.cb_port = QComboBox(); self.cb_port.setEditable(True); b = QPushButton("⟳"); b.setProperty("kind", "ghost"); b.setFixedWidth(34); b.clicked.connect(self._ports)
        g.addWidget(label(tr("Serial port"), "muted"), 1, 0); g.addWidget(self.cb_port, 1, 1); g.addWidget(b, 1, 2)
        self.ed_baud = QLineEdit("9600"); g.addWidget(label(tr("Baud"), "muted"), 2, 0); g.addWidget(self.ed_baud, 2, 1)
        self.ed_serial = QLineEdit(); self.ed_serial.setPlaceholderText(tr("device serial (blank = first found)")); g.addWidget(label(tr("StarLab device"), "muted"), 3, 0); g.addWidget(self.ed_serial, 3, 1, 1, 2)
        self.cb_unit = QComboBox(); self.cb_unit.addItems(["mW/cm2", "mW", "W"]); g.addWidget(label(tr("Unit"), "muted"), 4, 0); g.addWidget(self.cb_unit, 4, 1)
        self.ed_aperture = QLineEdit(); self.ed_aperture.setPlaceholderText(tr("sensor aperture cm² (for mW/cm2)")); g.addWidget(label(tr("Aperture"), "muted"), 5, 0); g.addWidget(self.ed_aperture, 5, 1, 1, 2)
        # --- sequence
        c = Card(tr("Sequence")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 1)
        row = 0
        self.sp_int = QSpinBox(); self.sp_int.setRange(10, 100); self.sp_int.setValue(100); self.sp_int.setSuffix(" %")
        g.addWidget(label(tr("LED intensity"), "muted"), row, 0); g.addWidget(self.sp_int, row, 1); row += 1
        self.cb_wl = QComboBox(); self.cb_wl.addItems(["405", "450"]); g.addWidget(label(tr("Wavelength nm"), "muted"), row, 0); g.addWidget(self.cb_wl, row, 1); row += 1
        self.cb_pos = None
        if self.trigger == "led_thermistor":
            self.cb_pos = QComboBox()
            for pos in LED_POSITIONS: self.cb_pos.addItem(tr(pos), pos)
            want = str(self.defaults.get("sensor_position") or "right")
            self.cb_pos.setCurrentIndex(max(0, self.cb_pos.findData(want)))
            g.addWidget(label(tr("Sensor position"), "muted"), row, 0); g.addWidget(self.cb_pos, row, 1); row += 1
        self.cb_mode = QComboBox()
        if self.trigger == "door" or self.app.is_sim():
            self.cb_mode.addItem(tr(self.ui["auto"]), "auto")
        self.cb_mode.addItem(tr(self.ui["operator"]), "operator")
        g.addWidget(label(tr(self.ui["trigger_caption"]), "muted"), row, 0); g.addWidget(self.cb_mode, row, 1); row += 1
        self.sp_hz = QSpinBox(); self.sp_hz.setRange(5, 200); self.sp_hz.setValue(25); self.sp_hz.setSuffix(" Hz")
        g.addWidget(label(tr("Sample rate"), "muted"), row, 0); g.addWidget(self.sp_hz, row, 1); row += 1
        self.lbl_dut = label("", "muted", wrap=True); g.addWidget(self.lbl_dut, row, 0, 1, 2)
        # --- live
        c = Card(tr("Live")); root.addWidget(c, 1)
        row_ = QHBoxLayout(); c.body.addLayout(row_)
        self.p_phase = Pill(tr("idle"), T.MUTED); row_.addWidget(self.p_phase)
        self.lbl_status = label(tr("Press Start."), "instruction"); row_.addWidget(self.lbl_status, 1)
        self.btn_start = QPushButton(tr("▶ Start measurement")); self.btn_start.setProperty("kind", "big"); self.btn_start.clicked.connect(self.start); row_.addWidget(self.btn_start)
        self.btn_mark = QPushButton(tr(self.ui["marker"])); self.btn_mark.setProperty("kind", "ghost"); self.btn_mark.setEnabled(False); self.btn_mark.clicked.connect(self._marked); row_.addWidget(self.btn_mark)
        self.btn_abort = QPushButton(tr("Abort — LEDs off")); self.btn_abort.setProperty("kind", "danger"); self.btn_abort.setEnabled(False); self.btn_abort.clicked.connect(self.abort); row_.addWidget(self.btn_abort)
        self.trace = TraceWidget(); c.body.addWidget(self.trace)
        # --- result
        c = Card(tr("Result")); root.addWidget(c, 2)
        rl = QHBoxLayout(); c.body.addLayout(rl)
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(12); rl.addLayout(self.grid)
        self.res_labels = {}
        rows = [("status", tr("Status")), ("plateau", tr("Plateau")), ("t_trigger", tr(self.ui["result_caption"])), ("off", self.spec["field"]),
                ("t_1pct", tr("Below 1 %")), ("residual", tr("Residual")), ("alarm", tr("Alarm"))]
        if self.trigger == "led_thermistor":
            rows.append(("names", tr("Alarm names the sensor")))
        for i, (key, cap) in enumerate(rows):
            self.grid.addWidget(label(cap, "muted"), i, 0); w = label("—", "mono", bold=True); self.grid.addWidget(w, i, 1); self.res_labels[key] = w
        self.p_verdict = Pill(tr("not measured"), T.MUTED); self.grid.addWidget(self.p_verdict, 3, 2)
        self.graph = QLabel(); self.graph.setAlignment(Qt.AlignCenter); self.graph.setMinimumSize(520, 240); self.graph.setScaledContents(False)
        self.graph.setStyleSheet(f"background: {T.PAPER}; border: 1px solid {T.LINE};"); rl.addWidget(self.graph, 1)
        # --- buttons
        bb = QHBoxLayout(); root.addLayout(bb)
        self.lbl_files = label("", "muted", wrap=True); bb.addWidget(self.lbl_files, 1)
        self.btn_apply = QPushButton(tr("Apply to run — fill fields + attach CSV/PNG")); self.btn_apply.setProperty("kind", "big"); self.btn_apply.setEnabled(False); self.btn_apply.clicked.connect(self.apply); bb.addWidget(self.btn_apply)
        b = QPushButton(tr("Close")); b.setProperty("kind", "ghost"); b.clicked.connect(self.reject); bb.addWidget(b)
        self._ports(); self._load_settings(); self.cb_backend.currentIndexChanged.connect(self._backend_changed); self._backend_changed()

    # ------------------------------------------------------------------ settings
    def _ports(self):
        cur = self.cb_port.currentText(); self.cb_port.clear()
        for dev, desc in list_serial_ports(): self.cb_port.addItem(f"{dev}", dev); self.cb_port.setItemData(self.cb_port.count() - 1, desc, Qt.ToolTipRole)
        if cur: self.cb_port.setCurrentText(cur)

    def _load_settings(self):
        spec = self.store.get_meta("meter_spec", "sim" if self.app.is_sim() else "starlab")
        kind, _, rest = spec.partition(":")
        i = self.cb_backend.findData(kind if kind in ("sim", "starlab", "serial") else "starlab"); self.cb_backend.setCurrentIndex(max(0, i))
        if kind == "serial":
            port, _, baud = rest.partition(":"); self.cb_port.setCurrentText(port); self.ed_baud.setText(baud or "9600")
        elif kind == "starlab":
            self.ed_serial.setText(rest)
        self.cb_unit.setCurrentText(self.store.get_meta("meter_unit", "mW/cm2")); self.ed_aperture.setText(self.store.get_meta("meter_aperture", "") or "")
        st = self.app.dut_state
        self.lbl_dut.setText(trf("Machine: {url} — {mode}", url=self.app.machine_url, mode=tr(st.mode)))

    def _backend_changed(self):
        k = self.cb_backend.currentData()
        for w in (self.cb_port, self.ed_baud): w.setEnabled(k == "serial")
        self.ed_serial.setEnabled(k == "starlab")
        if k == "sim" and not self.app.is_sim():
            self.lbl_status.setText(tr("Note: the simulated meter follows the simulated machine, not the real one — pick a StarBright backend for a real run."))

    def _spec(self) -> str:
        k = self.cb_backend.currentData()
        if k == "serial": return f"serial:{self.cb_port.currentText().strip()}:{self.ed_baud.text().strip() or '9600'}"
        if k == "starlab": return "starlab" + (f":{self.ed_serial.text().strip()}" if self.ed_serial.text().strip() else "")
        return "sim"

    def _config(self, spec: str, unit: str) -> UvOffConfig:
        return UvOffConfig(trigger=self.trigger, sensor_position=self.cb_pos.currentData() if self.cb_pos else "right",
                           intensity=self.sp_int.value(), wavelength=int(self.cb_wl.currentText()), sample_hz=float(self.sp_hz.value()),
                           trigger_mode=self.cb_mode.currentData(), unit=unit if spec != "sim" else "mW/cm2")

    # ------------------------------------------------------------------ run
    def start(self):
        if self.worker is not None and self.worker.isRunning(): return
        spec = self._spec(); unit = self.cb_unit.currentText(); ap = self.ed_aperture.text().strip()
        try:
            aperture = float(ap) if ap else None
            meter = open_meter(spec, unit=unit, aperture_cm2=aperture)
        except (MeterError, ValueError) as e:
            QMessageBox.warning(self, tr("Meter"), str(e)); return
        for k, v in (("meter_spec", spec), ("meter_unit", unit), ("meter_aperture", ap)): self.store.set_meta(k, v)
        from .dut import make_client
        dut = make_client(self.app.machine_url, timeout=2.0)
        if not self.app.dut_state.online:
            QMessageBox.warning(self, tr("Machine"), tr("No machine connected — set the DUT address in the header.")); return
        cfg = self._config(spec, unit)
        if self.trigger == "led_thermistor" and self.app.is_sim() and cfg.sensor_position != "right" and cfg.trigger_mode == "auto":
            QMessageBox.information(self, tr("Simulation"), tr("The simulator models the right LED thermistor only — the right one will be disconnected; record the position you actually tested on the real machine."))
        self.result = None; self.files = []; self.trace.clear(); self.trace.unit = cfg.unit; self.graph.clear(); self.lbl_files.setText("")
        for w in self.res_labels.values(): w.setText("—")
        self.p_verdict.set(tr("measuring…"), T.WARN); self.btn_apply.setEnabled(False)
        self.btn_start.setEnabled(False); self.btn_abort.setEnabled(True); self.btn_mark.setEnabled(False)
        self.worker = UvOffWorker(dut, meter, cfg)
        self.worker.status.connect(self._on_status); self.worker.sample.connect(self._on_sample); self.worker.done.connect(self._on_done)
        self.store.log(f"{self.test_id} UV-off measurement started", self.app.operator, self.run["run_id"] if self.run else None, {"meter": spec, "cfg": cfg.__dict__})
        self.worker.start()

    def abort(self):
        if self.worker: self.worker.runner.abort()

    def _marked(self):
        if self.worker: self.worker.runner.mark_trigger(); self.trace.t_trigger = time.monotonic(); self.btn_mark.setEnabled(False)

    def _on_status(self, phase, text):
        colors = {"connect": T.INFO, "baseline": T.MUTED, "uv_on": T.WARN, "plateau": T.WARN, "trigger": T.BAD, "record": T.PURPLE, "done": T.OK}
        self.p_phase.set(tr(phase), colors.get(phase, T.MUTED)); self.lbl_status.setText(tr(text) if phase != "done" else text)
        if phase == "trigger":
            # the operator has to act when the console could not (or was told not to) fire the trigger itself
            manual = self.cb_mode.currentData() == "operator" or text == self.worker.runner.cfg.prompt
            self.btn_mark.setEnabled(manual)
            if manual: self.lbl_status.setText("⚠  " + tr(text) + "  ⚠")
        if phase == "record" and self.worker and self.worker.runner.result.t_trigger:
            self.trace.t_trigger = self.worker.runner.result.t_trigger

    def _on_sample(self, s):
        self.trace.push(s.t, s.value)

    def _on_done(self, res: UvOffResult):
        self.result = res; self.btn_start.setEnabled(True); self.btn_abort.setEnabled(False); self.btn_mark.setEnabled(False)
        if res.t_trigger: self.trace.t_trigger = res.t_trigger
        L = self.res_labels; fmt = lambda v, f="{:.3g}": "—" if v is None else f.format(v)  # noqa: E731
        L["status"].setText(res.status + (f"  ({'; '.join(res.notes)})" if res.notes else ""))
        L["plateau"].setText(f"{fmt(res.plateau)} {res.unit}  (dark {fmt(res.dark)})")
        L["t_trigger"].setText(tr(res.trigger_source) if res.t_trigger else tr("not seen"))
        L["off"].setText(fmt(res.uv_off_time, "{:.3f} s") + (f"  = {res.uv_off_time * 1000:.0f} ms" if res.uv_off_time is not None else ""))
        L["t_1pct"].setText(fmt(None if res.t_1pct is None or res.t_trigger is None else res.t_1pct - res.t_trigger, "{:.3f} s"))
        L["residual"].setText(f"{fmt(res.residual)} {res.unit}" + (f"  ({res.residual_fraction * 100:.2f} % of plateau)" if res.residual_fraction is not None else ""))
        L["alarm"].setText(f"{res.alarm_code or '—'}  {res.alarm_text or ''}")
        if "names" in L:
            L["names"].setText("—" if res.alarm_identifies_sensor is None else (tr("yes") if res.alarm_identifies_sensor else tr("no")))
        if res.uv_off_time is None:
            self.p_verdict.set(tr("no result"), T.WARN)
        else:
            ok = res.passed; ms, lim = res.uv_off_time * 1000, res.limit_s * 1000
            self.p_verdict.set(f"PASS · {ms:.0f} ms ≤ {lim:.0f} ms" if ok else f"FAIL · {ms:.0f} ms > {lim:.0f} ms", T.OK if ok else T.BAD)
        # artefacts
        tag = "uvoff" if self.trigger == "door" else "ledoff"
        stem = (self.run["run_id"].replace("|", "_") if self.run else "standalone") + time.strftime("_%Y%m%d-%H%M%S")
        out = self.app.data / "export" / "attachments" / (self.run["run_id"].replace("|", "_") if self.run else tag)
        try:
            csv_p = write_csv(res, out / f"{stem}_{tag}.csv")
            png_p = plot_png(res, out / f"{stem}_{tag}.png", title=f"{self.test_id} · {self.run['unit_id'] if self.run else 'bench'} · UV irradiance vs time")
            self.files = [csv_p, png_p]; self.lbl_files.setText(tr("Saved: ") + ", ".join(f.name for f in self.files))
            pm = QPixmap(str(png_p)); self.graph.setPixmap(pm.scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:  # noqa: BLE001
            self.lbl_files.setText(trf("Could not write the artefacts: {err}", err=e))
        self.btn_apply.setEnabled(self.run is not None and res.status in ("OK", "TIMEOUT"))
        self.store.log(f"{self.test_id} UV-off measurement finished", self.app.operator, self.run["run_id"] if self.run else None, res.summary())

    # ------------------------------------------------------------------ apply
    def values(self) -> dict:
        """Catalog fields filled from the measurement, per test."""
        r = self.result; out = {}
        if r is None: return out
        if r.uv_off_time is not None: out[self.spec["field"]] = round(r.uv_off_time, 3)
        if self.trigger == "door":
            if r.residual is not None and r.unit == "mW/cm2": out["residual_irradiance"] = round(r.residual, 4)
        else:
            out["sensor_position"] = r.sensor_position
            if r.alarm_identifies_sensor is not None: out["alarm_identifies_sensor"] = bool(r.alarm_identifies_sensor)
        if r.alarm_code is not None or r.alarm_text:
            out["alarm_raised"] = True
            if r.alarm_code is not None: out["error_code"] = r.alarm_code
        elif r.status == "OK":
            out["alarm_raised"] = False
        return out

    def apply(self):
        if not self.run or not self.result: return
        for f in self.files:
            self.store.add_attachment(self.run["run_id"], f.name, str(f), f.suffix.lstrip("."), hashlib.sha256(f.read_bytes()).hexdigest())
        vals = self.values()
        if vals: self.store.set_values(self.run["run_id"], vals, self.app.operator)
        self.store.log(f"{self.test_id} values captured from Ophir meter", self.app.operator, self.run["run_id"], {**vals, "files": [f.name for f in self.files], "meter": self.result.meter_info})
        self.app.kick_sync(); self.applied.emit(vals, [str(f) for f in self.files]); self.accept()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.files and len(self.files) > 1 and self.files[1].exists():
            self.graph.setPixmap(QPixmap(str(self.files[1])).scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
