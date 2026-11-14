"""DVT-THM-004 automatic run — the console drives the machine through the
LED-cooling fan duties and hands the operator the final answer and the graph.

Opened from the wizard on the step that carries `tool: led_fan_sweep`. On
"Apply to this unit's rows" the values of every duty row of the unit are
written (the current run's fields are filled in the wizard; the other duty
rows are completed and committed automatically), and the CSV + PNG are
attached to each of them.
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
from ..instruments.fansweep import FanSweepRunner, FanSweepConfig, FanSweepResult, PANELS, write_csv, plot_png

TEST_ID = "DVT-THM-004"
COLORS = {"right": T.BAD, "left": T.INFO, "back": T.WARN, "door": T.OK}


class FanSweepWorker(QThread):
    status = Signal(str, str)
    sample = Signal(object)
    done = Signal(object)

    def __init__(self, dut, cfg: FanSweepConfig):
        super().__init__()
        self.runner = FanSweepRunner(dut, cfg, on_status=lambda p, t: self.status.emit(p, t), on_sample=lambda s: self.sample.emit(s))

    def run(self):
        self.done.emit(self.runner.run())


class PanelTrace(QWidget):
    """Four panel temperatures against time, duty bands shaded, the limit drawn."""

    def __init__(self, limit: float = 75.0):
        super().__init__(); self.pts: deque = deque(maxlen=20000); self.limit = limit
        self.setMinimumHeight(200); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def push(self, s):
        self.pts.append(s); self.update()

    def clear(self):
        self.pts.clear(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(36, 10, -10, -22); p.fillRect(self.rect(), QColor(T.CARD)); p.setPen(QPen(QColor(T.LINE), 1)); p.drawRect(r)
        if len(self.pts) < 2:
            p.setPen(QColor(T.MUTED)); p.drawText(r, Qt.AlignCenter, tr("waiting for readings…")); return
        t0, t1 = self.pts[0].t, self.pts[-1].t; span = max(1e-3, t1 - t0)
        vals = [v for s in self.pts for v in s.temps.values() if v is not None]
        lo, hi = min(vals + [20.0]), max(vals + [self.limit + 3])
        def X(t): return r.left() + (t - t0) / span * r.width()
        def Y(v): return r.bottom() - (v - lo) / max(1e-3, hi - lo) * r.height()
        # duty bands
        cur, start = None, t0
        for s in list(self.pts) + [None]:
            d = s.duty if s else None
            if d != cur:
                if cur is not None:
                    p.fillRect(QRectF(X(start), r.top(), X(s.t if s else t1) - X(start), r.height()), QColor(124, 92, 191, 18 if (cur // 10) % 2 else 34))
                    p.setPen(QColor(T.PURPLE)); p.drawText(QRectF(X(start) + 3, r.top() + 2, 90, 14), Qt.AlignLeft, f"fan {cur} %")
                cur, start = d, (s.t if s else t1)
        p.setPen(QPen(QColor(T.BAD), 1, Qt.DashLine)); p.drawLine(int(r.left()), int(Y(self.limit)), int(r.right()), int(Y(self.limit)))
        p.setPen(QColor(T.MUTED)); p.drawText(QRectF(2, Y(self.limit) - 7, 32, 14), Qt.AlignRight, f"{self.limit:.0f}")
        for pnl in PANELS:
            p.setPen(QPen(QColor(COLORS[pnl]), 1.6)); last = None
            for s in self.pts:
                v = s.temps.get(pnl)
                if v is None: last = None; continue
                cur_pt = (X(s.t), Y(v))
                if last: p.drawLine(int(last[0]), int(last[1]), int(cur_pt[0]), int(cur_pt[1]))
                last = cur_pt
        p.setPen(QColor(T.MUTED)); p.drawText(QRectF(r.left(), r.bottom() + 4, r.width(), 16), Qt.AlignLeft, f"{(t1 - t0) / 60:.1f} min")


class FanSweepDialog(QDialog):
    applied = Signal(dict)     # {run_id: values}

    def __init__(self, app, run: dict | None = None, parent=None):
        super().__init__(parent)
        self.app, self.run, self.store = app, run, app.store
        self.result: FanSweepResult | None = None; self.worker: FanSweepWorker | None = None; self.files: list[Path] = []
        self.setWindowTitle(tr("DVT-THM-004 — LED temperature vs LED-cooling fan duty (automatic)"))
        from .screen import fit
        fit(self, 1120, 860)
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(10)
        root.addWidget(label(self.run["run_id"] if self.run else tr("stand-alone run (no wizard run selected)"), "eyebrow"))
        root.addWidget(label(tr("The console runs the whole sweep: fans to each duty, LEDs on at maximum, wait for every panel to settle, stop at the 75 °C limit, LEDs off. You get the settled temperature per panel per duty, the lowest duty with margin, and the graph."), "muted", wrap=True))
        top = QHBoxLayout(); root.addLayout(top)
        c = Card(tr("Sweep")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 1)
        self.ed_duties = QLineEdit("100, 90, 80, 70"); g.addWidget(label(tr("Fan duties %"), "muted"), 0, 0); g.addWidget(self.ed_duties, 0, 1)
        self.sp_int = QSpinBox(); self.sp_int.setRange(10, 100); self.sp_int.setValue(100); self.sp_int.setSuffix(" %"); g.addWidget(label(tr("LED intensity"), "muted"), 1, 0); g.addWidget(self.sp_int, 1, 1)
        self.sp_limit = QDoubleSpinBox(); self.sp_limit.setRange(40, 100); self.sp_limit.setValue(float((self.app.cat.thresholds.get("led_temperature_thresholds") or {}).get("working_limit") or 75)); self.sp_limit.setSuffix(" °C")
        g.addWidget(label(tr("Working limit"), "muted"), 2, 0); g.addWidget(self.sp_limit, 2, 1)
        self.sp_margin = QDoubleSpinBox(); self.sp_margin.setRange(0, 30); self.sp_margin.setValue(5.0); self.sp_margin.setSuffix(" °C"); g.addWidget(label(tr("Margin for the recommendation"), "muted"), 3, 0); g.addWidget(self.sp_margin, 3, 1)
        c = Card(tr("Settling")); g = QGridLayout(); g.setHorizontalSpacing(10); c.body.addLayout(g); top.addWidget(c, 1)
        sim = self.app.is_sim()
        self.sp_window = QSpinBox(); self.sp_window.setRange(5, 1800); self.sp_window.setValue(20 if sim else 300); self.sp_window.setSuffix(" s"); g.addWidget(label(tr("Settle window"), "muted"), 0, 0); g.addWidget(self.sp_window, 0, 1)
        self.sp_rate = QDoubleSpinBox(); self.sp_rate.setRange(0.01, 10); self.sp_rate.setDecimals(2); self.sp_rate.setValue(1.0 if sim else 0.1); self.sp_rate.setSuffix(" °C/min"); g.addWidget(label(tr("Settled below"), "muted"), 1, 0); g.addWidget(self.sp_rate, 1, 1)
        self.sp_poll = QDoubleSpinBox(); self.sp_poll.setRange(0.2, 30); self.sp_poll.setValue(1.0 if sim else 2.0); self.sp_poll.setSuffix(" s"); g.addWidget(label(tr("Poll every"), "muted"), 2, 0); g.addWidget(self.sp_poll, 2, 1)
        self.sp_timeout = QSpinBox(); self.sp_timeout.setRange(1, 180); self.sp_timeout.setValue(3 if sim else 30); self.sp_timeout.setSuffix(" min"); g.addWidget(label(tr("Row timeout"), "muted"), 3, 0); g.addWidget(self.sp_timeout, 3, 1)
        self.lbl_dut = label(trf("Machine: {url} — {mode}", url=self.app.machine_url, mode=tr(self.app.dut_state.mode)), "muted", wrap=True); g.addWidget(self.lbl_dut, 4, 0, 1, 2)
        # live
        c = Card(tr("Live")); root.addWidget(c, 1)
        row = QHBoxLayout(); c.body.addLayout(row)
        self.p_phase = Pill(tr("idle"), T.MUTED); row.addWidget(self.p_phase)
        self.lbl_status = label(tr("Press Start — the machine does the rest."), "instruction"); row.addWidget(self.lbl_status, 1)
        self.btn_start = QPushButton(tr("▶ Start sweep")); self.btn_start.setProperty("kind", "big"); self.btn_start.clicked.connect(self.start); row.addWidget(self.btn_start)
        self.btn_abort = QPushButton(tr("Abort — LEDs off, fans 100 %")); self.btn_abort.setProperty("kind", "danger"); self.btn_abort.setEnabled(False); self.btn_abort.clicked.connect(self.abort); row.addWidget(self.btn_abort)
        prow = QHBoxLayout(); c.body.addLayout(prow); self.tiles = {}
        for pnl in PANELS:
            t = label("—", "mono", size=16, bold=True, color=COLORS[pnl]); prow.addWidget(label(tr(f"{pnl} panel"), "muted")); prow.addWidget(t); self.tiles[pnl] = t
        self.lbl_duty = label("", "mono", bold=True); prow.addWidget(self.lbl_duty); prow.addStretch()
        self.trace = PanelTrace(); c.body.addWidget(self.trace)
        # result
        c = Card(tr("Result — the final answer for the operator")); root.addWidget(c, 2)
        self.lbl_final = label("", "instruction", wrap=True); c.body.addWidget(self.lbl_final)
        rl = QHBoxLayout(); c.body.addLayout(rl)
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(12); rl.addLayout(self.grid)
        self.graph = QLabel(); self.graph.setAlignment(Qt.AlignCenter); self.graph.setMinimumSize(560, 230); self.graph.setStyleSheet(f"background: {T.PAPER}; border: 1px solid {T.LINE};"); rl.addWidget(self.graph, 1)
        bb = QHBoxLayout(); root.addLayout(bb)
        self.lbl_files = label("", "muted", wrap=True); bb.addWidget(self.lbl_files, 1)
        self.btn_apply = QPushButton(tr("Apply to this unit's duty rows — fill fields, commit the other rows, attach CSV/PNG")); self.btn_apply.setProperty("kind", "big"); self.btn_apply.setEnabled(False); self.btn_apply.clicked.connect(self.apply); bb.addWidget(self.btn_apply)
        b = QPushButton(tr("Close")); b.setProperty("kind", "ghost"); b.clicked.connect(self.reject); bb.addWidget(b)

    # ------------------------------------------------------------------ run
    def _cfg(self) -> FanSweepConfig:
        duties = tuple(int(x) for x in self.ed_duties.text().replace(";", ",").split(",") if x.strip())
        return FanSweepConfig(duties=duties, intensity=self.sp_int.value(), poll_s=self.sp_poll.value(), settle_window_s=float(self.sp_window.value()),
                              settle_rate_c_per_min=self.sp_rate.value(), min_row_s=float(self.sp_window.value()), row_timeout_s=self.sp_timeout.value() * 60.0,
                              limit_c=self.sp_limit.value(), margin_c=self.sp_margin.value())

    def start(self):
        if self.worker is not None and self.worker.isRunning(): return
        if not self.app.dut_state.online:
            QMessageBox.warning(self, tr("Machine"), tr("No machine connected — set the DUT address in the header.")); return
        try:
            cfg = self._cfg()
            if not cfg.duties: raise ValueError("no duties")
        except ValueError:
            QMessageBox.warning(self, tr("Sweep"), tr("Fan duties: a comma-separated list of percentages, e.g. 100, 90, 80, 70")); return
        from .dut import make_client
        dut = make_client(self.app.machine_url, timeout=3.0)
        self.result = None; self.files = []; self.trace.clear(); self.trace.limit = cfg.limit_c; self.graph.clear(); self.lbl_final.setText(""); self.lbl_files.setText("")
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w: w.deleteLater()
        self.btn_start.setEnabled(False); self.btn_abort.setEnabled(True); self.btn_apply.setEnabled(False)
        self.worker = FanSweepWorker(dut, cfg)
        self.worker.status.connect(self._on_status); self.worker.sample.connect(self._on_sample); self.worker.done.connect(self._on_done)
        self.store.log("DVT-THM-004 fan sweep started", self.app.operator, self.run["run_id"] if self.run else None, {"cfg": cfg.__dict__})
        self.worker.start()

    def abort(self):
        if self.worker: self.worker.runner.abort()

    def _on_status(self, phase, text):
        colors = {"fans": T.INFO, "uv": T.WARN, "settle": T.PURPLE, "row": T.OK, "safe": T.MUTED, "done": T.OK}
        self.p_phase.set(tr(phase), colors.get(phase, T.MUTED))
        if phase != "done": self.lbl_status.setText(text)

    def _on_sample(self, s):
        self.trace.push(s)
        for pnl, t in self.tiles.items():
            v = s.temps.get(pnl); t.setText("—" if v is None else f"{v:.1f} °C")
        self.lbl_duty.setText(f"fan {s.duty} %" + (f" · {s.tach:.0f} rpm" if s.tach else ""))

    def _on_done(self, res: FanSweepResult):
        self.result = res; self.btn_start.setEnabled(True); self.btn_abort.setEnabled(False)
        self.lbl_status.setText(tr("Finished") + f" — {res.status}" + (f" · {'; '.join(res.notes)}" if res.notes else ""))
        self.lbl_final.setText(res.final_text())
        hdr = [tr("Duty"), tr("Status"), *[tr(f"{p}") for p in PANELS], tr("Hottest"), tr("Margin"), tr("Settle min")]
        for c, h in enumerate(hdr): self.grid.addWidget(label(h, "muted"), 0, c)
        for i, r in enumerate(res.rows, start=1):
            col = T.OK if (r.settled and r.max_settled_temp is not None and r.max_settled_temp <= res.config["limit_c"] - res.config["margin_c"]) else (T.WARN if r.settled else T.BAD)
            cells = [f"{r.duty} %", r.status, *[("—" if r.temps.get(p) is None else f"{r.temps[p]:.1f}") for p in PANELS], r.hottest_panel or "—",
                     "—" if r.margin_to_working_limit is None else f"{r.margin_to_working_limit:+.1f} °C", "—" if r.time_to_settle is None else f"{r.time_to_settle:.1f}"]
            for c, v in enumerate(cells): self.grid.addWidget(label(v, "mono", bold=(c in (0, 1)), color=col if c == 1 else None), i, c)
        stem = (self.run["run_id"].replace("|", "_") if self.run else "standalone") + time.strftime("_%Y%m%d-%H%M%S")
        out = self.app.data / "export" / "attachments" / ((self.run["test_id"] + "_" + self.run["unit_id"]) if self.run else "thm005")
        try:
            csv_p = write_csv(res, out / f"{stem}_fansweep.csv"); png_p = plot_png(res, out / f"{stem}_fansweep.png", title=f"DVT-THM-004 · {self.run['unit_id'] if self.run else 'bench'} · LED temperature vs fan duty")
            self.files = [csv_p, png_p]; self.lbl_files.setText(tr("Saved: ") + ", ".join(f.name for f in self.files))
            self.graph.setPixmap(QPixmap(str(png_p)).scaled(self.graph.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:  # noqa: BLE001
            self.lbl_files.setText(trf("Could not write the artefacts: {err}", err=e))
        self.btn_apply.setEnabled(self.run is not None and bool(res.rows))
        self.store.log("DVT-THM-004 fan sweep finished", self.app.operator, self.run["run_id"] if self.run else None, res.summary())

    # ------------------------------------------------------------------ apply
    def apply(self):
        """Write every duty row of this unit: the current run's values go back to the wizard,
        the other rows are started, filled, and committed with their verdict."""
        if not self.run or not self.result: return
        unit = self.run["unit_id"]; test_id = self.run["test_id"]
        rows_by_duty = {r.duty: r for r in self.result.rows}
        applied = {}
        for run in self.store.runs(test_id, unit):
            duty = run["variant"].get("fan_duty")
            row = rows_by_duty.get(duty)
            if row is None or run["status"] == "REJECTED": continue
            vals = row.values(); vals["raw_log_attached"] = bool(self.files)
            for f in self.files:
                self.store.add_attachment(run["run_id"], f.name, str(f), f.suffix.lstrip("."), hashlib.sha256(f.read_bytes()).hexdigest())
            if run["run_id"] == self.run["run_id"]:
                self.store.set_values(run["run_id"], vals, self.app.operator); applied[run["run_id"]] = vals
            elif run["status"] != "DONE":
                if run["status"] == "NOT_STARTED": self.store.start_run(run["run_id"], self.app.operator)
                self.store.confirm_safety(run["run_id"], self.app.operator); self.store.confirm_preconditions(run["run_id"], self.app.operator)
                self.store.set_values(run["run_id"], vals, self.app.operator)
                v, d = self.app.engine.finish(run["run_id"], self.app.operator)
                self.store.log("Auto-completed by the fan sweep", self.app.operator, run["run_id"], {"from_run": self.run["run_id"], "verdict": v, "detail": d})
                applied[run["run_id"]] = vals
        self.store.log("DVT-THM-004 values applied", self.app.operator, self.run["run_id"], {"rows": sorted(applied), "recommended_duty": self.result.recommended_duty()})
        self.app.kick_sync(); self.applied.emit(applied); self.accept()
