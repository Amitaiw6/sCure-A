"""DVT-OPT-001 / DVT-OPT-002 — the UV sweep run INLINE on the wizard step (no
dialog): meter check, Start / Abort, live progress, result; when the sweep
finishes the values are applied to the run, the CSV + PNG attached, and the
wizard moves on to the next step by itself.

The machine does the work (server/uv_sweep.py, StarBright on its USB); the
panel drives it through the DUT client and shows what is happening.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, QMessageBox, QProgressBar

from . import theme as T
from .widgets import Card, Pill, label
from .i18n import tr, trf
from .uvsweep_dialog import UvSweepWorker, SweepTrace
from ..instruments.uvsweep import UvSweepConfig, UvSweepResult, DEFAULT_STEPS, values as sweep_values, write_csv, plot_png


class UvSweepPanel(QWidget):
    applied = Signal(dict, list)     # (field values, attached files) — emitted when a finished sweep has been written to the run
    aborted = Signal()

    def __init__(self, app, run: dict, wavelength: int, parent=None):
        super().__init__(parent)
        self.app, self.run, self.store, self.wavelength = app, run, app.store, int(wavelength)
        self.result: UvSweepResult | None = None; self.worker: UvSweepWorker | None = None; self.files: list[Path] = []
        self.meter_info: dict = {}; self.checked = False; self.total_s = 1.0
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)
        # --- meter on the machine (verified live; the operator sets the wavelength on the meter or from here)
        c = Card(tr("Meter on the machine")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); root.addWidget(c)
        self.p_meter = Pill(tr("not checked"), T.MUTED); g.addWidget(self.p_meter, 0, 0)
        self.lbl_meter = label("", "muted", wrap=True); g.addWidget(self.lbl_meter, 0, 1, 1, 2)
        self.p_wl = Pill(tr("wavelength?"), T.MUTED); g.addWidget(self.p_wl, 1, 0)
        self.lbl_wl = label("", "instruction", wrap=True); g.addWidget(self.lbl_wl, 1, 1, 1, 2)
        self.lbl_instruction = label("", "banner-warn", wrap=True); g.addWidget(self.lbl_instruction, 2, 0, 1, 3)
        row = QHBoxLayout(); g.addLayout(row, 3, 0, 1, 3)
        self.btn_check = QPushButton(tr("Check the meter")); self.btn_check.setProperty("kind", "ghost"); self.btn_check.clicked.connect(self.check_meter); row.addWidget(self.btn_check)
        self.btn_setwl = QPushButton(trf("Set the meter to {nm} nm", nm=self.wavelength)); self.btn_setwl.setProperty("kind", "ghost"); self.btn_setwl.clicked.connect(self.set_wavelength); row.addWidget(self.btn_setwl)
        row.addStretch()
        # --- sweep parameters + controls
        c = Card(tr("Sweep")); root.addWidget(c)      # fixed procedure: 30 → 100 % in 10 % steps, 10 s per step, meter at 5 Hz, mean of the last 5 s — nothing to set
        row = QHBoxLayout(); c.body.addLayout(row)
        self.p_phase = Pill(tr("idle"), T.MUTED); row.addWidget(self.p_phase)
        self.lbl_status = label(tr("Check the meter, then press Start — the machine does the rest."), "instruction", wrap=True); row.addWidget(self.lbl_status, 1)
        self.btn_start = QPushButton(tr("▶ Run the UV sweep")); self.btn_start.setProperty("kind", "big"); self.btn_start.setEnabled(False); self.btn_start.clicked.connect(self.start); row.addWidget(self.btn_start)
        self.btn_abort = QPushButton(tr("Abort test — LEDs off")); self.btn_abort.setProperty("kind", "danger"); self.btn_abort.clicked.connect(self.abort); row.addWidget(self.btn_abort)
        self.bar = QProgressBar(); self.bar.setRange(0, 1000); self.bar.setValue(0); self.bar.setTextVisible(False); c.body.addWidget(self.bar)
        self.trace = SweepTrace(); self.trace.setMinimumHeight(140); c.body.addWidget(self.trace)
        # --- result
        c = Card(tr("Result — irradiance against the command")); root.addWidget(c)
        self.lbl_final = label("", "instruction", wrap=True); c.body.addWidget(self.lbl_final)
        rl = QHBoxLayout(); c.body.addLayout(rl)
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(12); rl.addLayout(self.grid)
        self.graph = QLabel(); self.graph.setAlignment(Qt.AlignCenter); self.graph.setMinimumSize(480, 200); self.graph.setStyleSheet(f"background: {T.PAPER}; border: 1px solid {T.LINE};"); rl.addWidget(self.graph, 1)
        self.lbl_files = label("", "muted", wrap=True); c.body.addWidget(self.lbl_files)

    # ------------------------------------------------------------------ meter
    def on_shown(self):
        """Called by the wizard when the step becomes visible: one live check, not at construction."""
        if not self.checked:
            self.checked = True; self.check_meter()

    def _dut(self):
        from .dut import make_client
        return make_client(self.app.machine_url, timeout=8.0)

    def check_meter(self):
        if not self.app.dut_state.online:
            self.p_meter.set(tr("machine offline"), T.BAD); self.lbl_meter.setText(tr("No machine connected — set the DUT address in the header.")); self.btn_start.setEnabled(False); return
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
            self.btn_check.setText(tr("Check the meter")); self.btn_start.setEnabled(self.worker is None or not self.worker.isRunning())
            self.store.log("StarBright wavelength verified", self.app.operator, self.run["run_id"], {"meter_nm": wl, "test_nm": self.wavelength})
        else:
            self.p_wl.set(f"{wl} nm ✗" if wl else tr("wavelength?"), T.BAD)
            self.lbl_wl.setText(trf("The meter is set to {have} nm but this test is at {want} nm.", have=wl if wl is not None else "?", want=self.wavelength))
            self.lbl_instruction.setText("⚠  " + trf("OPERATOR: on the StarBright itself, set the wavelength to {want} nm (Setup → Wavelength). Or press 'Set the meter to {want} nm' to set it from here. Either way, press 'I set the meter — check again' afterwards. The sweep stays locked until the machine reads {want} nm back from the meter.", want=self.wavelength))
            self.btn_check.setText(tr("I set the meter — check again")); self.btn_start.setEnabled(False)

    def set_wavelength(self):
        try:
            r = self._dut().meter_set_wavelength(self.wavelength)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "message": str(e)}
        if not r.get("ok"):
            QMessageBox.warning(self, tr("Meter"), str(r.get("message") or tr("could not set the wavelength")))
        self.store.log("StarBright wavelength set from the console", self.app.operator, self.run["run_id"], {"nm": self.wavelength, **r})
        self.check_meter()

    # ------------------------------------------------------------------ run
    DWELL_S, SETTLE_S, HZ = 10.0, 5.0, 5.0        # the procedure is fixed; it is not editable on the step

    def _cfg(self) -> UvSweepConfig:
        return UvSweepConfig(wavelength=self.wavelength, steps=DEFAULT_STEPS, dwell_s=self.DWELL_S, settle_s=self.SETTLE_S, hz=self.HZ)

    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def start(self):
        if self.running(): return
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
        self.total_s = cfg.baseline_s + len(cfg.steps) * cfg.dwell_s + 3.0
        self.result = None; self.files = []; self.trace.clear(); self.graph.clear(); self.lbl_final.setText(""); self.lbl_files.setText(""); self.bar.setValue(0)
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w: w.deleteLater()
        self.btn_start.setEnabled(False); self.btn_check.setEnabled(False); self.btn_setwl.setEnabled(False)
        self.worker = UvSweepWorker(self._dut(), cfg)
        self.worker.status.connect(self._on_status); self.worker.sample.connect(self._on_sample); self.worker.done.connect(self._on_done)
        self.store.log(f"{cfg.test_id} UV sweep started on the machine", self.app.operator, self.run["run_id"], {"cfg": cfg.__dict__, "meter": self.meter_info})
        self.worker.start()

    def abort(self):
        """Abort the sweep on the machine (LEDs off). Safe to press at any time — with nothing running it still tells the machine to switch the LEDs off."""
        if self.worker and self.running():
            self.worker.runner.abort(); self.lbl_status.setText(tr("Aborting — LEDs off…"))
        else:
            try: self._dut().uv_sweep_abort()
            except Exception: pass  # noqa: BLE001
            self.lbl_status.setText(tr("Nothing running — LEDs off."))
        self.store.log("UV sweep abort pressed", self.app.operator, self.run["run_id"], {"running": self.running()})
        self.aborted.emit()

    def _on_status(self, phase, text):
        colors = {"meter": T.INFO, "start": T.INFO, "baseline": T.MUTED, "step": T.WARN, "tail": T.MUTED, "done": T.OK}
        self.p_phase.set(tr(phase), colors.get(phase, T.MUTED))
        if phase != "done": self.lbl_status.setText(text)

    def _on_sample(self, s):
        self.trace.push(s)
        self.bar.setValue(int(min(1.0, s[0] / self.total_s) * 1000))

    def _on_done(self, res: UvSweepResult):
        self.result = res; self.btn_start.setEnabled(True); self.btn_check.setEnabled(True); self.btn_setwl.setEnabled(True); self.bar.setValue(1000 if res.status == "OK" else self.bar.value())
        self.lbl_status.setText(tr("Finished") + f" — {res.status}" + (f" · {'; '.join(res.notes)}" if res.notes else ""))
        self.lbl_final.setText(res.final_text())
        hdr = [tr("Command"), tr("Irradiance"), tr("SD"), tr("Fit"), tr("Deviation"), tr("Gain"), tr("Hottest LED")]
        for c_, h in enumerate(hdr): self.grid.addWidget(label(h, "muted"), 0, c_)
        for i, s in enumerate(res.steps, start=1):
            cells = [f"{s.intensity} %", "—" if s.mean is None else f"{s.mean:.3f}", "—" if s.sd is None else f"{s.sd:.3f}", "—" if s.fit is None else f"{s.fit:.3f}",
                     "—" if s.dev_pct is None else f"{s.dev_pct:+.1f} %", "—" if s.gain is None else f"{s.gain:.3f}", "—" if s.led_max_c is None else f"{s.led_max_c:.1f} °C"]
            for c_, v in enumerate(cells): self.grid.addWidget(label(v, "mono", bold=(c_ == 0)), i, c_)
        if res.steps:
            stem = self.run["run_id"].replace("|", "_") + time.strftime("_%Y%m%d-%H%M%S")
            out = self.app.data / "export" / "attachments" / (self.run["test_id"] + "_" + self.run["unit_id"])
            try:
                csv_p = write_csv(res, out / f"{stem}_uvsweep.csv"); png_p = plot_png(res, out / f"{stem}_uvsweep.png", title=f"{res.test_id} · {self.run['unit_id']} · irradiance vs command · {res.wavelength} nm")
                self.files = [csv_p, png_p]; self.lbl_files.setText(tr("Saved: ") + ", ".join(f.name for f in self.files))
                self.graph.setPixmap(QPixmap(str(png_p)).scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:  # noqa: BLE001
                self.lbl_files.setText(trf("Could not write the artefacts: {err}", err=e))
        self.store.log(f"{res.test_id} UV sweep finished", self.app.operator, self.run["run_id"], res.summary())
        if res.status == "OK" and res.steps:
            self._apply()

    def _apply(self):
        """Write the result to the run (fields + attachments) and tell the wizard — it moves to the next step."""
        for f in self.files:
            self.store.add_attachment(self.run["run_id"], f.name, str(f), f.suffix.lstrip("."), hashlib.sha256(f.read_bytes()).hexdigest())
        vals = sweep_values(self.result); vals["graph_attached"] = bool(self.files)
        self.store.set_values(self.run["run_id"], vals, self.app.operator)
        self.store.log(f"{self.result.test_id} values captured from the machine's UV sweep", self.app.operator, self.run["run_id"], {**vals, "files": [f.name for f in self.files]})
        self.app.kick_sync(); self.applied.emit(vals, [str(f) for f in self.files])
