"""DVT-OPT-001 / DVT-OPT-002 — UV irradiance against commanded LED power, run
by the machine with the Ophir StarBright on ITS USB port.

Opened from the wizard on the step that carries `tool: uv_linearity`. The
dialog first checks the meter through the machine (present? head? which
wavelength is it SET to?) and refuses to start until the meter is on the
test's wavelength; then it starts the sweep on the machine, follows it live,
draws the graph of measured irradiance against the command, and on "Apply"
fills the run's fields and attaches the CSV + PNG.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit, QSpinBox, QLabel,
                               QMessageBox, QSizePolicy, QDoubleSpinBox)

from . import theme as T
from .widgets import Card, Pill, label
from .i18n import tr, trf
from ..instruments.uvsweep import UvSweepRunner, UvSweepConfig, UvSweepResult, DEFAULT_STEPS, values as sweep_values, write_csv, plot_png


class UvSweepWorker(QThread):
    status = Signal(str, str)
    sample = Signal(object)
    done = Signal(object)

    def __init__(self, dut, cfg: UvSweepConfig):
        super().__init__()
        self.runner = UvSweepRunner(dut, cfg, on_status=lambda p, t: self.status.emit(p, t), on_sample=lambda s: self.sample.emit(s))

    def run(self):
        self.done.emit(self.runner.run())


class SweepTrace(QWidget):
    """Live irradiance against time with the commanded staircase behind it."""

    def __init__(self):
        super().__init__(); self.pts: deque = deque(maxlen=6000); self.setMinimumHeight(160); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def push(self, s):
        self.pts.append((s[0], s[1], s[2])); self.update()

    def clear(self):
        self.pts.clear(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8, 8, -8, -8)
        p.fillRect(self.rect(), QColor(T.CARD)); p.setPen(QPen(QColor(T.LINE), 1)); p.drawRect(r)
        pts = [x for x in self.pts if x[1] is not None]
        if len(self.pts) < 2:
            p.setPen(QColor(T.MUTED)); p.drawText(r, Qt.AlignCenter, tr("waiting for readings…")); return
        t0, t1 = self.pts[0][0], max(self.pts[-1][0], self.pts[0][0] + 1); vmax = max((v for _, v, _ in pts), default=1.0) or 1.0
        def X(t): return r.left() + (t - t0) / (t1 - t0) * r.width()
        def Yv(v): return r.bottom() - min(1.0, v / (vmax * 1.08)) * r.height()
        def Yc(c): return r.bottom() - c / 110.0 * r.height()
        p.setPen(QPen(QColor(T.ACCENT), 1, Qt.DashLine)); last = None
        for t, _, c in self.pts:
            cur = (X(t), Yc(c))
            if last: p.drawLine(int(last[0]), int(last[1]), int(cur[0]), int(last[1])); p.drawLine(int(cur[0]), int(last[1]), int(cur[0]), int(cur[1]))
            last = cur
        p.setPen(QPen(QColor(T.PURPLE), 2)); last = None
        for t, v, _ in pts:
            cur = (X(t), Yv(v))
            if last: p.drawLine(int(last[0]), int(last[1]), int(cur[0]), int(cur[1]))
            last = cur
        p.setPen(QColor(T.MUTED)); p.drawText(QRectF(r.left() + 6, r.top() + 4, 320, 18), Qt.AlignLeft, f"{pts[-1][1]:.3f} mW/cm²   max {vmax:.3f}   ·   {self.pts[-1][2]} %" if pts else "—")


class UvSweepDialog(QDialog):
    applied = Signal(dict, list)       # (field values, attached file paths)

    def __init__(self, app, run: dict | None = None, parent=None, wavelength: int = 405):
        super().__init__(parent)
        self.app, self.run, self.store, self.wavelength = app, run, app.store, int(wavelength)
        self.result: UvSweepResult | None = None; self.worker: UvSweepWorker | None = None; self.files: list[Path] = []
        self.meter_info: dict = {}
        self.setWindowTitle(trf("{test} — UV irradiance vs commanded power at {nm} nm (StarBright on the machine)", test=UvSweepConfig(wavelength=self.wavelength).test_id, nm=self.wavelength))
        from .screen import fit
        fit(self, 1120, 880)
        self._build(); self.check_meter()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(10)
        root.addWidget(label(self.run["run_id"] if self.run else tr("stand-alone run (no wizard run selected)"), "eyebrow"))
        root.addWidget(label(trf("Plug the StarBright into the machine's USB port, switch it on, set it to {nm} nm on the meter itself, put the head at the chamber centre facing the LEDs and close the door. The machine takes a dark reading, then steps the LEDs 30 → 100 % ({nm} nm), 15 s per step, and switches them off. You get the graph of measured irradiance against the command.", nm=self.wavelength), "muted", wrap=True))
        top = QHBoxLayout(); root.addLayout(top)
        # --- meter on the machine
        c = Card(tr("Meter on the machine")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 3)
        self.p_meter = Pill(tr("not checked"), T.MUTED); g.addWidget(self.p_meter, 0, 0)
        self.lbl_meter = label("", "muted", wrap=True); g.addWidget(self.lbl_meter, 0, 1, 1, 2)
        self.p_wl = Pill(tr("wavelength?"), T.MUTED); g.addWidget(self.p_wl, 1, 0)
        self.lbl_wl = label("", "instruction", wrap=True); g.addWidget(self.lbl_wl, 1, 1, 1, 2)
        # the operator sets the wavelength ON THE METER; the console only reads it back — nothing is set remotely
        self.lbl_instruction = label("", "banner-warn", wrap=True); g.addWidget(self.lbl_instruction, 2, 0, 1, 3)
        row = QHBoxLayout(); g.addLayout(row, 3, 0, 1, 3)
        self.btn_check = QPushButton(tr("Check the meter")); self.btn_check.setProperty("kind", "big"); self.btn_check.clicked.connect(self.check_meter); row.addWidget(self.btn_check)
        self.btn_setwl = QPushButton(trf("Set the meter to {nm} nm", nm=self.wavelength)); self.btn_setwl.setProperty("kind", "ghost"); self.btn_setwl.clicked.connect(self.set_wavelength); row.addWidget(self.btn_setwl)
        row.addStretch()
        # --- sweep
        c = Card(tr("Sweep")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 2)
        self.ed_steps = QLineEdit(", ".join(map(str, DEFAULT_STEPS))); g.addWidget(label(tr("Steps %"), "muted"), 0, 0); g.addWidget(self.ed_steps, 0, 1)
        self.sp_dwell = QDoubleSpinBox(); self.sp_dwell.setRange(1, 300); self.sp_dwell.setValue(15); self.sp_dwell.setSuffix(" s"); g.addWidget(label(tr("Dwell per step"), "muted"), 1, 0); g.addWidget(self.sp_dwell, 1, 1)
        self.sp_settle = QDoubleSpinBox(); self.sp_settle.setRange(0.5, 60); self.sp_settle.setValue(5); self.sp_settle.setSuffix(" s"); g.addWidget(label(tr("Average the last"), "muted"), 2, 0); g.addWidget(self.sp_settle, 2, 1)
        self.sp_hz = QSpinBox(); self.sp_hz.setRange(1, 10); self.sp_hz.setValue(5); self.sp_hz.setSuffix(" Hz"); g.addWidget(label(tr("Meter rate"), "muted"), 3, 0); g.addWidget(self.sp_hz, 3, 1)
        self.lbl_dut = label(trf("Machine: {url} — {mode}", url=self.app.machine_url, mode=tr(self.app.dut_state.mode)), "muted", wrap=True); g.addWidget(self.lbl_dut, 4, 0, 1, 2)
        # --- live
        c = Card(tr("Live")); root.addWidget(c, 1)
        row = QHBoxLayout(); c.body.addLayout(row)
        self.p_phase = Pill(tr("idle"), T.MUTED); row.addWidget(self.p_phase)
        self.lbl_status = label(tr("Check the meter, then press Start — the machine does the rest."), "instruction"); row.addWidget(self.lbl_status, 1)
        self.btn_start = QPushButton(tr("▶ Run the UV sweep")); self.btn_start.setProperty("kind", "big"); self.btn_start.setEnabled(False); self.btn_start.clicked.connect(self.start); row.addWidget(self.btn_start)
        self.btn_abort = QPushButton(tr("Abort — LEDs off")); self.btn_abort.setProperty("kind", "danger"); self.btn_abort.setEnabled(False); self.btn_abort.clicked.connect(self.abort); row.addWidget(self.btn_abort)
        self.trace = SweepTrace(); c.body.addWidget(self.trace)
        # --- result
        c = Card(tr("Result — irradiance against the command")); root.addWidget(c, 2)
        self.lbl_final = label("", "instruction", wrap=True); c.body.addWidget(self.lbl_final)
        rl = QHBoxLayout(); c.body.addLayout(rl)
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(12); rl.addLayout(self.grid)
        self.graph = QLabel(); self.graph.setAlignment(Qt.AlignCenter); self.graph.setMinimumSize(560, 240); self.graph.setStyleSheet(f"background: {T.PAPER}; border: 1px solid {T.LINE};"); rl.addWidget(self.graph, 1)
        bb = QHBoxLayout(); root.addLayout(bb)
        self.lbl_files = label("", "muted", wrap=True); bb.addWidget(self.lbl_files, 1)
        self.btn_apply = QPushButton(tr("Apply to run — fill fields + attach CSV/PNG")); self.btn_apply.setProperty("kind", "big"); self.btn_apply.setEnabled(False); self.btn_apply.clicked.connect(self.apply); bb.addWidget(self.btn_apply)
        b = QPushButton(tr("Close")); b.setProperty("kind", "ghost"); b.clicked.connect(self.reject); bb.addWidget(b)

    # ------------------------------------------------------------------ meter
    def _dut(self):
        from .dut import make_client
        return make_client(self.app.machine_url, timeout=8.0)

    def check_meter(self):
        if not self.app.dut_state.online:
            self.p_meter.set(tr("machine offline"), T.BAD); self.lbl_meter.setText(tr("No machine connected — set the DUT address in the header.")); return
        try:
            m = self._dut().meter()
        except Exception as e:  # noqa: BLE001
            m = {"present": False, "message": str(e)}
        self.meter_info = m
        if not m.get("present"):
            self.p_meter.set(tr("NO METER"), T.BAD); self.lbl_meter.setText(tr("The machine does not see a StarBright on its USB: ") + str(m.get("message") or ""))
            self.p_wl.set(tr("wavelength?"), T.MUTED); self.lbl_wl.setText("")
            self.lbl_instruction.setText("⚠  " + tr("Plug the StarBright's USB cable into the machine, switch the meter on, then press 'Check the meter'."))
            self.btn_start.setEnabled(False); self.btn_check.setText(tr("Check the meter")); return
        self.p_meter.set(tr("meter present"), T.OK)
        self.lbl_meter.setText(f"{m.get('instrument') or ''} · {m.get('head') or ''} · {m.get('unit_name') or m.get('units') or ''}" + (f" · {m['reading_mw_cm2']:.3f} mW/cm²" if m.get("reading_mw_cm2") is not None else ""))
        wl = m.get("wavelength_nm")
        if wl == self.wavelength:
            self.p_wl.set(f"{wl} nm ✓", T.OK); self.lbl_wl.setText(trf("The meter is set to {nm} nm — correct for this test.", nm=wl))
            self.lbl_instruction.setText("✓  " + trf("Wavelength verified on the meter: {nm} nm. You can run the sweep.", nm=wl))
            self.btn_check.setText(tr("Check the meter")); self.btn_start.setEnabled(True)
            self.store.log("StarBright wavelength verified", self.app.operator, self.run["run_id"] if self.run else None, {"meter_nm": wl, "test_nm": self.wavelength})
        else:
            self.p_wl.set(f"{wl} nm ✗" if wl else tr("wavelength?"), T.BAD)
            self.lbl_wl.setText(trf("The meter is set to {have} nm but this test is at {want} nm.", have=wl if wl is not None else "?", want=self.wavelength))
            self.lbl_instruction.setText("⚠  " + trf("OPERATOR: on the StarBright itself, set the wavelength to {want} nm (Setup → Wavelength). Or press 'Set the meter to {want} nm' to set it from here. Either way, press 'I set the meter — check again' afterwards. The sweep stays locked until the machine reads {want} nm back from the meter.", want=self.wavelength))
            self.btn_check.setText(tr("I set the meter — check again")); self.btn_start.setEnabled(False)

    def set_wavelength(self):
        """Set the meter's wavelength through the machine (the operator can also do it on the meter); the readback decides."""
        try:
            r = self._dut().meter_set_wavelength(self.wavelength)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "message": str(e)}
        if not r.get("ok"):
            QMessageBox.warning(self, tr("Meter"), str(r.get("message") or tr("could not set the wavelength")))
        self.store.log("StarBright wavelength set from the console", self.app.operator, self.run["run_id"] if self.run else None, {"nm": self.wavelength, **r})
        self.check_meter()

    # ------------------------------------------------------------------ run
    def _cfg(self) -> UvSweepConfig:
        steps = tuple(int(x) for x in self.ed_steps.text().replace(";", ",").split(",") if x.strip())
        return UvSweepConfig(wavelength=self.wavelength, steps=steps, dwell_s=self.sp_dwell.value(), settle_s=self.sp_settle.value(), hz=float(self.sp_hz.value()))

    def start(self):
        if self.worker is not None and self.worker.isRunning(): return
        if not self.app.dut_state.online:
            QMessageBox.warning(self, tr("Machine"), tr("No machine connected — set the DUT address in the header.")); return
        if not self.meter_info.get("present"):
            self.check_meter()
            if not self.meter_info.get("present"):
                QMessageBox.warning(self, tr("Meter"), tr("The machine does not see the StarBright. Plug it into the machine's USB port, switch it on and press 'Check the meter'.")); return
        if self.meter_info.get("wavelength_nm") != self.wavelength:
            QMessageBox.warning(self, tr("Meter"), trf("The StarBright is set to {have} nm — set it to {want} nm on the meter before the sweep.", have=self.meter_info.get("wavelength_nm"), want=self.wavelength)); return
        try:
            cfg = self._cfg()
        except ValueError as e:
            QMessageBox.warning(self, tr("Sweep"), str(e)); return
        self.result = None; self.files = []; self.trace.clear(); self.graph.clear(); self.lbl_final.setText(""); self.lbl_files.setText("")
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w: w.deleteLater()
        self.btn_start.setEnabled(False); self.btn_abort.setEnabled(True); self.btn_apply.setEnabled(False); self.btn_check.setEnabled(False); self.btn_setwl.setEnabled(False)
        self.worker = UvSweepWorker(self._dut(), cfg)
        self.worker.status.connect(self._on_status); self.worker.sample.connect(self._on_sample); self.worker.done.connect(self._on_done)
        self.store.log(f"{cfg.test_id} UV sweep started on the machine", self.app.operator, self.run["run_id"] if self.run else None, {"cfg": cfg.__dict__, "meter": self.meter_info})
        self.worker.start()

    def abort(self):
        if self.worker: self.worker.runner.abort()

    def _on_status(self, phase, text):
        colors = {"meter": T.INFO, "start": T.INFO, "baseline": T.MUTED, "step": T.WARN, "tail": T.MUTED, "done": T.OK}
        self.p_phase.set(tr(phase), colors.get(phase, T.MUTED))
        if phase != "done": self.lbl_status.setText(text)

    def _on_sample(self, s):
        self.trace.push(s)

    def _on_done(self, res: UvSweepResult):
        self.result = res; self.btn_start.setEnabled(True); self.btn_abort.setEnabled(False); self.btn_check.setEnabled(True); self.btn_setwl.setEnabled(True)
        self.lbl_status.setText(tr("Finished") + f" — {res.status}" + (f" · {'; '.join(res.notes)}" if res.notes else ""))
        self.lbl_final.setText(res.final_text())
        hdr = [tr("Command"), tr("Irradiance"), tr("SD"), tr("Fit"), tr("Deviation"), tr("Gain"), tr("Hottest LED")]
        for c_, h in enumerate(hdr): self.grid.addWidget(label(h, "muted"), 0, c_)
        for i, s in enumerate(res.steps, start=1):
            cells = [f"{s.intensity} %", "—" if s.mean is None else f"{s.mean:.3f}", "—" if s.sd is None else f"{s.sd:.3f}", "—" if s.fit is None else f"{s.fit:.3f}",
                     "—" if s.dev_pct is None else f"{s.dev_pct:+.1f} %", "—" if s.gain is None else f"{s.gain:.3f}", "—" if s.led_max_c is None else f"{s.led_max_c:.1f} °C"]
            for c_, v in enumerate(cells): self.grid.addWidget(label(v, "mono", bold=(c_ == 0)), i, c_)
        if res.steps:
            stem = (self.run["run_id"].replace("|", "_") if self.run else "standalone") + time.strftime("_%Y%m%d-%H%M%S")
            out = self.app.data / "export" / "attachments" / ((self.run["test_id"] + "_" + self.run["unit_id"]) if self.run else res.test_id.lower())
            try:
                csv_p = write_csv(res, out / f"{stem}_uvsweep.csv"); png_p = plot_png(res, out / f"{stem}_uvsweep.png", title=f"{res.test_id} · {self.run['unit_id'] if self.run else 'bench'} · irradiance vs command · {res.wavelength} nm")
                self.files = [csv_p, png_p]; self.lbl_files.setText(tr("Saved: ") + ", ".join(f.name for f in self.files))
                self.graph.setPixmap(QPixmap(str(png_p)).scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:  # noqa: BLE001
                self.lbl_files.setText(trf("Could not write the artefacts: {err}", err=e))
        self.btn_apply.setEnabled(self.run is not None and bool(res.steps))
        self.store.log(f"{res.test_id} UV sweep finished", self.app.operator, self.run["run_id"] if self.run else None, res.summary())

    # ------------------------------------------------------------------ apply
    def apply(self):
        if not self.run or not self.result: return
        for f in self.files:
            self.store.add_attachment(self.run["run_id"], f.name, str(f), f.suffix.lstrip("."), hashlib.sha256(f.read_bytes()).hexdigest())
        vals = sweep_values(self.result); vals["graph_attached"] = bool(self.files)
        self.store.set_values(self.run["run_id"], vals, self.app.operator)
        self.store.log(f"{self.result.test_id} values captured from the machine's UV sweep", self.app.operator, self.run["run_id"], {**vals, "files": [f.name for f in self.files]})
        self.app.kick_sync(); self.applied.emit(vals, [str(f) for f in self.files]); self.accept()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.files and len(self.files) > 1 and self.files[1].exists():
            self.graph.setPixmap(QPixmap(str(self.files[1])).scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
