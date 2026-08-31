"""The guided run wizard — one screen per stage, the operator is told exactly
what to do, Next/Back, animated stepper and page transitions.

Stages for a run (SRS-DVT-083/084/085/086/088):
    Overview → [Safety plan] → Equipment & calibration → Preconditions
    → Step 1 … Step N (instruction + only that step's data fields)
    → Review & verdict → Done

State is written to the store on every Next (values, current_step), so a
restart resumes at the same stage. Steps can be redlined in place. Fields
that map to a live DUT metric get a tr("⇩ from DUT") button.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit,
                               QComboBox, QCheckBox, QScrollArea, QFrame, QInputDialog, QMessageBox, QFileDialog,
                               QDialog, QDialogButtonBox, QFormLayout, QTextEdit)

from . import theme as T
from .widgets import Card, Pill, Stepper, FadeStack, PulseDot, label
from .dut import FIELD_MAP
from .i18n import tr


class WaiverDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Waive this run (SRS-DVT-087)")
        f = QFormLayout(self); self.approver = QLineEdit(); self.rationale = QTextEdit()
        f.addRow("Approver (name, role)", self.approver); f.addRow("Rationale", self.rationale)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); f.addRow(bb)


class RunWizard(QWidget):
    finished = Signal(str, str)      # (run_id, verdict or 'ABORTED')
    left = Signal()                  # operator left the wizard without finishing (state kept)

    def __init__(self, app, run_id: str):
        super().__init__()
        self.app, self.cat, self.store, self.engine = app, app.cat, app.store, app.engine
        self.run = self.store.run(run_id); self.test = self.cat.tests[self.run["test_id"]]
        self.fields = self.cat.field_map(self.run["test_id"])
        self.values = self.store.values(run_id)
        self.field_widgets: dict[str, QWidget] = {}
        self.step_started = time.monotonic()
        self._build()
        self.go(self._resume_index(), animate=False)

    # ------------------------------------------------------------------ stages
    def _stages(self) -> list[tuple[str, str]]:
        t = self.test; st = [("overview", tr("Overview"))]
        if t.get("safety_plan") or t.get("safety_critical"): st.append(("safety", tr("Safety plan")))
        if t.get("equipment"): st.append(("equipment", tr("Equipment")))
        st.append(("pre", tr("Preconditions")))
        for i, _ in enumerate(t.get("procedure_steps") or []): st.append((f"step:{i}", f"{tr('Step')} {i + 1}"))
        st += [("review", tr("Verdict")), ("done", tr("Done"))]
        return st

    def _resume_index(self) -> int:
        r = self.run
        if r["status"] == "DONE": return len(self.stages) - 2
        if r["current_step"] > 0: return next(i for i, (k, _) in enumerate(self.stages) if k == f"step:{min(r['current_step'], len(self.test.get('procedure_steps') or []) - 1)}")
        if r["preconditions_confirmed"]: return next(i for i, (k, _) in enumerate(self.stages) if k.startswith("step:"))
        return 0

    # ------------------------------------------------------------------ layout
    def _build(self):
        self.stages = self._stages()
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(12)
        head = Card(kind="raised"); hl = QHBoxLayout(); head.body.addLayout(hl)
        v = QVBoxLayout(); hl.addLayout(v, 1)
        v.addWidget(label(f"{self.run['test_id']} · {self.run['unit_id']} · {self._variant()} · rep {self.run['repetition']}", "eyebrow"))
        v.addWidget(label(self.test["title"], "h2"))
        right = QVBoxLayout(); hl.addLayout(right)
        r1 = QHBoxLayout(); self.dot = PulseDot(T.WARN); r1.addWidget(self.dot); self.lbl_timer = label("00:00", "mono", size=16, bold=True); r1.addWidget(self.lbl_timer); right.addLayout(r1)
        self.p_dut = Pill("DUT: —", T.MUTED); right.addWidget(self.p_dut, 0, Qt.AlignRight)
        root.addWidget(head)
        self.stepper = Stepper([t for _, t in self.stages]); root.addWidget(self.stepper)
        self.stack = FadeStack(); root.addWidget(self.stack, 1)
        for key, _ in self.stages:
            self.stack.addWidget(self._page(key))
        foot = QHBoxLayout()
        self.btn_leave = QPushButton(tr("Leave wizard (keeps progress)")); self.btn_leave.setProperty("kind", "ghost"); self.btn_leave.clicked.connect(self.left.emit); foot.addWidget(self.btn_leave)
        self.btn_redline = QPushButton(tr("Redline this step")); self.btn_redline.setProperty("kind", "ghost"); self.btn_redline.clicked.connect(self.redline); foot.addWidget(self.btn_redline)
        self.btn_attach = QPushButton(tr("Attach file…")); self.btn_attach.setProperty("kind", "ghost"); self.btn_attach.clicked.connect(self.attach); foot.addWidget(self.btn_attach)
        foot.addStretch()
        self.lbl_err = label("", color=T.BAD, bold=True); foot.addWidget(self.lbl_err)
        self.btn_back = QPushButton(tr("← Back")); self.btn_back.setProperty("kind", "ghost"); self.btn_back.clicked.connect(lambda: self.go(self.index - 1, forward=False)); foot.addWidget(self.btn_back)
        self.btn_next = QPushButton(tr("Next →")); self.btn_next.setProperty("kind", "big"); self.btn_next.clicked.connect(self.next); foot.addWidget(self.btn_next)
        root.addLayout(foot)
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(1000)

    def _variant(self):
        return ", ".join(f"{k}={v}" for k, v in self.run["variant"].items()) or "single"

    def _scroll(self, inner: QWidget) -> QScrollArea:
        # reading column: keep the instruction and fields at a comfortable width, centred on wide screens
        inner.setMaximumWidth(1040)
        host = QWidget(); hl = QHBoxLayout(host); hl.setContentsMargins(0, 0, 0, 0); hl.addStretch(1); hl.addWidget(inner, 8); hl.addStretch(1)
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame); sa.setWidget(host); return sa

    def _page(self, key: str) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(4, 0, 4, 0); l.setSpacing(12); l.setAlignment(Qt.AlignTop)
        t = self.test
        if key == "overview":
            l.addWidget(label(tr("What this run verifies"), "h1"))
            l.addWidget(label(t.get("purpose", "").strip(), "instruction", wrap=True))
            c = Card(tr("Run")); g = QGridLayout(); c.body.addLayout(g)
            rows = [(tr("Method"), t["method"]), (tr("Phase"), str(self.cat.phase_of(self.run["test_id"])["id"])),
                    (tr("Applicability"), t["applicability"]["rule"] + (f" ({t['applicability'].get('unit')})" if t["applicability"]["rule"] == "SINGLE" else "")),
                    (tr("Variant"), self._variant()), (tr("Repetition"), str(self.run["repetition"])), (tr("Estimated"), f"{t.get('duration_est_min')} min"),
                    (tr("Requirements"), ", ".join(f"REQ-{r}" for r in t.get("requirement_ids") or []) or "— (VCRM pending)"),
                    (tr("Dependencies"), ", ".join(t.get("dependencies") or []) or tr("none"))]
            for i, (k, v) in enumerate(rows):
                g.addWidget(label(k, "muted"), i, 0); g.addWidget(label(v, wrap=True), i, 1)
            l.addWidget(c)
            if t.get("sample_rationale"):
                l.addWidget(label("Why this sample: " + t["sample_rationale"].strip(), "muted", wrap=True))
            l.addWidget(label(tr("Press Next to begin. The wizard will tell you what to do at every stage; nothing is submitted until the verdict page."), "banner-info", wrap=True))
        elif key == "safety":
            l.addWidget(label(tr("Safety plan — read before touching the unit"), "h1"))
            for s in t.get("safety_plan") or ["Safety-critical test"]:
                l.addWidget(label("⚠  " + str(s), "banner-warn", wrap=True))
            self.cb_safety = QCheckBox(tr("I have read the safety plan; the area, PPE and remote controls are prepared")); self.cb_safety.setChecked(bool(self.run["safety_confirmed"]))
            l.addWidget(self.cb_safety)
        elif key == "equipment":
            l.addWidget(label(tr("Equipment and calibration"), "h1"))
            l.addWidget(label(tr("Put these instruments on the bench. A missing or expired calibration record blocks the run (SRS-DVT-085)."), "muted", wrap=True))
            c = Card(); g = QGridLayout(); c.body.addLayout(g); self.eq_ok = True
            for i, e in enumerate(t["equipment"]):
                cal = self.store.calibration(e["name"]); ok = bool(cal and cal["valid_until"])
                self.eq_ok &= ok
                g.addWidget(label(e["name"], wrap=True), i, 0)
                g.addWidget(Pill(f"cal {cal['calibration_id']} → {cal['valid_until']}" if ok else tr("NO CALIBRATION RECORD"), T.OK if ok else T.WARN), i, 1)
                b = QPushButton(tr("Record calibration…")); b.setProperty("kind", "ghost"); b.clicked.connect(lambda _, n=e["name"]: self._calibrate(n)); g.addWidget(b, i, 2)
            l.addWidget(c)
        elif key == "pre":
            l.addWidget(label(tr("Preconditions — confirm each one"), "h1"))
            l.addWidget(label(tr("The data fields stay locked until every precondition is ticked (SRS-DVT-083). Use DUT Control to bring the machine to the required state."), "muted", wrap=True))
            self.pre_boxes = []
            c = Card();
            for p in t.get("preconditions") or [tr("none")]:
                cb = QCheckBox(str(p)); cb.setChecked(bool(self.run["preconditions_confirmed"])); c.body.addWidget(cb); self.pre_boxes.append(cb)
            l.addWidget(c)
            self.dut_hint = label("", "banner-info", wrap=True); l.addWidget(self.dut_hint)
        elif key.startswith("step:"):
            i = int(key.split(":")[1]); s = t["procedure_steps"][i]
            l.addWidget(label(f"{tr('Step')} {i + 1} / {len(t['procedure_steps'])}", "eyebrow"))
            l.addWidget(label(str(s["step"]), "instruction", wrap=True))
            caps = s.get("capture") or []
            if caps:
                c = Card(tr("Record now")); g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8); c.body.addLayout(g)
                for r, name in enumerate(caps):
                    f = self.fields[name]
                    g.addWidget(label(f"{name}" + (f"  [{f['unit']}]" if f.get("unit") else ""), "mono"), r, 0)
                    w_ = self._field_widget(f, name); g.addWidget(w_, r, 1); self.field_widgets[name] = w_
                    if f.get("note"): g.addWidget(label(f["note"], "muted", wrap=True), r, 3)
                    if name in FIELD_MAP and name not in self.run["variant"]:
                        b = QPushButton(tr("⇩ from DUT")); b.setProperty("kind", "ghost"); b.setToolTip(f"insert live {FIELD_MAP[name]} from the connected machine")
                        b.clicked.connect(lambda _, n=name: self._from_dut(n)); g.addWidget(b, r, 2)
                l.addWidget(c)
            else:
                l.addWidget(label(tr("No data to record for this step — perform it, then press Next."), "muted"))
            self._redline_box(l, i)
        elif key == "review":
            l.addWidget(label(tr("Review and verdict"), "h1"))
            self.review_grid = QGridLayout(); c = Card(tr("Recorded values")); c.body.addLayout(self.review_grid); l.addWidget(c)
            self.lbl_criteria = label(t["pass_criteria"].strip(), "mono", wrap=True); self.lbl_criteria.setStyleSheet(f"font-family: Consolas; color: {T.MUTED};")
            c = Card(tr("Pass criteria")); c.body.addWidget(self.lbl_criteria); l.addWidget(c)
            row = QHBoxLayout(); self.p_verdict = Pill(tr("not evaluated"), T.MUTED); row.addWidget(self.p_verdict); self.lbl_vdetail = label("", "muted"); row.addWidget(self.lbl_vdetail); row.addStretch(); l.addLayout(row)
            row = QHBoxLayout()
            b = QPushButton(tr("Evaluate")); b.setProperty("kind", "ghost"); b.clicked.connect(self.evaluate); row.addWidget(b)
            self.btn_finish = QPushButton(tr("Finish run — commit verdict")); self.btn_finish.setProperty("kind", "big"); self.btn_finish.clicked.connect(self.finish); row.addWidget(self.btn_finish)
            b = QPushButton(tr("Waive…")); b.setProperty("kind", "ghost"); b.clicked.connect(self.waive); row.addWidget(b)
            b = QPushButton(tr("Reject run…")); b.setProperty("kind", "danger"); b.clicked.connect(self.reject); row.addWidget(b)
            row.addStretch(); l.addLayout(row)
            self.lbl_witness = QLineEdit(); self.lbl_witness.setPlaceholderText(tr("Witness (optional — name, role)")); l.addWidget(self.lbl_witness)
        elif key == "done":
            self.done_title = label("", "h1"); l.addWidget(self.done_title)
            self.done_body = label("", "instruction", wrap=True); l.addWidget(self.done_body)
            self.done_next = label("", "banner-info", wrap=True); l.addWidget(self.done_next)
        return self._scroll(w)

    def _redline_box(self, l, i):
        rls = [x for x in self.store.redlines(self.run["run_id"]) if x["step_index"] == i]
        if rls:
            for x in rls:
                l.addWidget(label(f"Redlined by {x['by_whom']}: {x['as_run']} — {x['reason']}", "banner-warn", wrap=True))

    def _field_widget(self, f, name):
        fixed = self.run["variant"].get(name); v = self.values.get(name)
        if fixed is not None:
            w = QLineEdit(str(fixed)); w.setReadOnly(True); w.setToolTip("set by the sweep / case matrix"); return w
        if f["type"] == "bool":
            w = QComboBox(); w.addItems(["", "yes / true", "no / false"]); w.setCurrentIndex(0 if v is None else (1 if v else 2)); return w
        if f["type"] == "enum":
            w = QComboBox(); w.addItems([""] + [str(x) for x in f["values"]]); w.setCurrentText("" if v is None else str(v)); return w
        w = QLineEdit("" if v is None else str(v)); w.setPlaceholderText({"float": "number", "int": "integer"}.get(f["type"], "text") + (f" · {f['range'][0]}–{f['range'][1]}" if f.get("range") else ""))
        return w

    # ------------------------------------------------------------------ navigation
    @property
    def index(self): return self.stack.currentIndex()

    def key(self, i=None): return self.stages[self.index if i is None else i][0]

    def go(self, i: int, forward=True, animate=True):
        i = max(0, min(i, len(self.stages) - 1))
        if animate: self.stack.set_page(i, forward)
        else: self.stack.setCurrentIndex(i)
        self.stepper.set_current(i); self.lbl_err.setText("")
        k = self.key(i); is_step = k.startswith("step:")
        self.btn_back.setEnabled(i > 0 and k != "done"); self.btn_redline.setVisible(is_step); self.btn_attach.setVisible(is_step or k == "review")
        self.btn_next.setVisible(k not in ("review", "done")); self.btn_leave.setVisible(k != "done")
        if is_step:
            self.store.set_step(self.run["run_id"], int(k.split(":")[1])); self.step_started = time.monotonic()
        if k == "pre":
            self.dut_hint.setText(self._dut_hint())
        if k == "review":
            self._fill_review(); self.evaluate()

    def next(self):
        k = self.key()
        if k == "safety":
            if not self.cb_safety.isChecked(): self.lbl_err.setText(tr("Acknowledge the safety plan to continue.")); return
            self.store.confirm_safety(self.run["run_id"], self.app.operator)
        elif k == "equipment":
            if not self.eq_ok and QMessageBox.question(self, "Calibration", "An instrument has no valid calibration record (SRS-DVT-085).\nRecord it now, or continue with a supervisor override (logged)?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            if not self.eq_ok: self.store.log("Blocker override", self.app.operator, self.run["run_id"], {"blockers": ["calibration"], "reason": "operator override in wizard"})
        elif k == "pre":
            if not all(cb.isChecked() for cb in self.pre_boxes): self.lbl_err.setText(tr("Tick every precondition first.")); return
            self.store.confirm_preconditions(self.run["run_id"], self.app.operator)
        elif k.startswith("step:"):
            try:
                vals = self._collect(step=int(k.split(":")[1]))
            except ValueError as e:
                self.lbl_err.setText(str(e)); return
            if vals: self.store.set_values(self.run["run_id"], vals, self.app.operator); self.values.update(vals)
            self.app.kick_sync()
        self.go(self.index + 1)

    # ------------------------------------------------------------------ data
    def _collect(self, step: int | None = None) -> dict:
        names = self.test["procedure_steps"][step].get("capture") or [] if step is not None else list(self.field_widgets)
        out = {}
        for name in names:
            if name in self.run["variant"] or name not in self.field_widgets: continue
            f, w = self.fields[name], self.field_widgets[name]
            if isinstance(w, QComboBox):
                s = w.currentText()
                if not s: continue
                out[name] = s.startswith("yes") if f["type"] == "bool" else s
            else:
                s = w.text().strip(); w.setProperty("state", "")
                if not s: continue
                try:
                    out[name] = float(s) if f["type"] == "float" else int(float(s)) if f["type"] == "int" else s
                except ValueError:
                    w.setProperty("state", "error"); w.style().unpolish(w); w.style().polish(w)
                    raise ValueError(f"{name}: enter a {'number' if f['type'] == 'float' else 'whole number'}")
                rng = f.get("range")
                if rng and not (rng[0] <= out[name] <= rng[1]):
                    w.setProperty("state", "error"); w.style().unpolish(w); w.style().polish(w)
                    raise ValueError(f"{name}: {out[name]} is outside the plausible range {rng[0]}–{rng[1]}")
                w.style().unpolish(w); w.style().polish(w)
        return out

    def _from_dut(self, name):
        st = self.app.dut_state
        if not st.online:
            self.lbl_err.setText(tr("No machine connected — set the DUT address in the header.")); return
        v = st.metrics.get(FIELD_MAP[name])
        if v is None:
            self.lbl_err.setText(f"The machine does not report {FIELD_MAP[name]} right now."); return
        w = self.field_widgets[name]
        if isinstance(w, QLineEdit):
            w.setText(f"{v:.2f}" if isinstance(v, float) else str(v)); w.setProperty("state", "fromdut"); w.style().unpolish(w); w.style().polish(w)
            self.store.log("Value captured from DUT", self.app.operator, self.run["run_id"], {"field": name, "metric": FIELD_MAP[name], "value": v, "url": st.url})

    def _dut_hint(self):
        st = self.app.dut_state
        if not st.online: return "Machine: not connected. Connect it in the header to capture values and drive it from DUT Control."
        m = st.metrics
        return f"Machine {st.url}: {st.mode} · chamber {m.get('chamberTemp')} °C · LED max {m.get('ledTempMax')} °C · door {'OPEN' if st.flags.get('doorOpen') else 'closed'} — use DUT Control if the preconditions need a different state."

    def _fill_review(self):
        while self.review_grid.count():
            w = self.review_grid.takeAt(0).widget()
            if w: w.deleteLater()
        try:
            self.values.update(self._collect())
        except ValueError as e:
            self.lbl_err.setText(str(e))
        vals = {**self.run["variant"], **self.values}
        r = 0
        for name, f in self.fields.items():
            v = vals.get(name)
            self.review_grid.addWidget(label(name, "mono"), r, 0)
            lb = label("—" if v is None else str(v), bold=v is not None, color=T.INK if v is not None else T.MUTED); self.review_grid.addWidget(lb, r, 1)
            self.review_grid.addWidget(label(f.get("unit") or "", "muted"), r, 2); r += 1

    def evaluate(self):
        try:
            vals = self._collect()
        except ValueError as e:
            self.lbl_err.setText(str(e)); return
        if vals: self.store.set_values(self.run["run_id"], vals, self.app.operator); self.values.update(vals)
        v, d = self.engine.evaluate(self.run["run_id"])
        self.p_verdict.set(v, T.VERDICT.get(v, T.WARN)); self.lbl_vdetail.setText(d)

    def finish(self):
        if hasattr(self, "cb_safety") and not self.cb_safety.isChecked():
            self.lbl_err.setText(tr("Acknowledge the safety plan first.")); return
        try:
            vals = self._collect()
        except ValueError as e:
            self.lbl_err.setText(str(e)); return
        self.store.set_values(self.run["run_id"], vals, self.app.operator)
        v, d = self.engine.finish(self.run["run_id"], self.app.operator, self.lbl_witness.text().strip() or None)
        self._done(v, d)

    def waive(self):
        dlg = WaiverDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        try:
            self.store.waive(self.run["run_id"], dlg.approver.text(), dlg.rationale.toPlainText(), self.app.operator)
        except ValueError as e:
            self.lbl_err.setText(str(e)); return
        self._done("WAIVED", f"approved by {dlg.approver.text()}")

    def reject(self):
        reason, ok = QInputDialog.getText(self, "Reject run", "Reason (ambient drift, warm start, instrumentation fault…):")
        if not ok or not reason.strip(): return
        n = self.store.reject_run(self.run["run_id"], reason, self.app.operator)
        self.app.kick_sync(); self.finished.emit(self.run["run_id"], "REJECTED")
        self.app.toast(f"Run rejected ({len(n)} run(s) affected)", T.WARN)

    def _done(self, verdict, detail):
        col = T.VERDICT.get(verdict, T.WARN)
        self.done_title.setText(tr(f"Run finished — {verdict}")); self.done_title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {col};")
        self.done_body.setText({"PASS": tr("All pass criteria met. The result is committed and exported."),
                                "FAIL": tr("Pass criteria not met. An NCR was opened automatically — describe the anomaly in the NCR list."),
                                "BLOCKED": f"The criterion could not be evaluated: {detail}. The run is recorded as BLOCKED, not as a pass.",
                                "WAIVED": f"Waived ({detail}). Counted separately from PASS in every view."}.get(verdict, detail))
        na = self.engine.next_action(self.run["unit_id"])
        self.done_next.setText(tr("Next for this unit: ") + na.message)
        self.dot.set_color(col); self._t.stop()
        self.go(len(self.stages) - 1); self.app.kick_sync(); self.finished.emit(self.run["run_id"], verdict)

    # ------------------------------------------------------------------ misc
    def redline(self):
        k = self.key()
        if not k.startswith("step:"): return
        i = int(k.split(":")[1])
        as_run, ok = QInputDialog.getMultiLineText(self, f"Redline step {i + 1}", "How was the step actually performed?")
        if not ok or not as_run.strip(): return
        reason, ok = QInputDialog.getText(self, "Redline", "Reason:")
        if not ok or not reason.strip(): return
        self.store.add_redline(self.run["run_id"], i, as_run, reason, self.app.operator); self.app.toast("Redline recorded", T.WARN)

    def attach(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach file (log, capture, photo)")
        if not path: return
        import hashlib, shutil
        from pathlib import Path
        src = Path(path); dst_dir = self.app.data / "export" / "attachments" / self.run["run_id"].replace("|", "_"); dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name; shutil.copy2(src, dst)
        self.store.add_attachment(self.run["run_id"], src.name, str(dst), src.suffix.lstrip("."), hashlib.sha256(dst.read_bytes()).hexdigest())
        self.app.kick_sync(); self.app.toast(f"Attached {src.name}", T.OK)

    def _calibrate(self, instrument):
        cid, ok = QInputDialog.getText(self, "Calibration record", f"{instrument}\nCertificate id:")
        if not ok: return
        until, ok = QInputDialog.getText(self, "Calibration record", "Valid until (YYYY-MM-DD):")
        if not ok: return
        self.store.set_calibration(instrument, cid, until)
        idx = self.index; self.stack.removeWidget(self.stack.widget(idx)); self.stack.insertWidget(idx, self._page("equipment")); self.stack.setCurrentIndex(idx)

    def _tick(self):
        el = int(time.monotonic() - self.step_started); self.lbl_timer.setText(f"{el // 60:02d}:{el % 60:02d}")
        st = self.app.dut_state
        self.p_dut.set(f"DUT: {st.mode}" + (f" · {st.metrics.get('chamberTemp')} °C" if st.online and st.metrics.get("chamberTemp") is not None else ""),
                       T.OK if st.online and st.mode == "IDLE" else T.WARN if st.online else T.MUTED)
