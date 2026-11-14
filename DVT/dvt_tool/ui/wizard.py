"""The guided run wizard — one screen per stage, the operator is told exactly
what to do, Next/Back, animated stepper and page transitions.

Stages for a run (SRS-DVT-083/084/085/086/088):
    Overview → [Safety plan] → Equipment & calibration → Preconditions
    → Step 1 … Step N (instruction + only that step's data fields)
    → Review & verdict → Done

State is written to the store on every Next (values, current_step), so a
restart resumes at the same stage. Steps can be redlined in place. Fields
that map to a live DUT metric get a tr("⇩ from DUT") button.

A step that records an alarm (`alarm_raised`, `error_code`, `alarm_text`,
`time_to_alarm`) is watched by the console itself: the DUT poller hands the
machine's active alerts to an `alarms.AlarmWatch`, the code / text / seconds
are filled in from what it saw, and Next stays locked until the machine
really raised something (SRS-DVT-198). See `dvt_tool/alarms.py`.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QTimer, QByteArray
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit,
                               QComboBox, QCheckBox, QScrollArea, QFrame, QInputDialog, QMessageBox, QFileDialog,
                               QDialog, QDialogButtonBox, QFormLayout, QTextEdit)

from . import theme as T
from .widgets import Card, Pill, Stepper, FadeStack, PulseDot, label
from .dut import FIELD_MAP
from ..instruments.uvoff import TOOL_TRIGGERS
from .. import alarms
from .. import figures
from .i18n import tr, trf


class FigureWidget(QSvgWidget):
    """The process figure, scaled to the available width at its own aspect ratio."""

    def __init__(self, svg: str, max_width: int = 860):
        super().__init__()
        self.load(QByteArray(svg.encode("utf-8")))
        self.setMaximumWidth(max_width); self.setMinimumHeight(int(360 * figures.H / figures.W))
        self.setStyleSheet(f"background: {T.PAPER}; border: 1px solid {T.LINE}; border-radius: 6px;")

    def hasHeightForWidth(self): return True

    def heightForWidth(self, w): return int(w * figures.H / figures.W)


def figure_card(test_id: str, step: int | None = None, caption: bool = True, max_width: int = 860, title: str | None = None, rev: str | None = None) -> QWidget | None:
    """Card with the test's engineering sheet (step highlights when a step is given), or None if the test has no figure.
    The drawing is English in every console language — only the card title is translated."""
    if not figures.has_figure(test_id):
        return None
    c = Card(tr("Process figure")); c.body.addWidget(FigureWidget(figures.figure_svg(test_id, step, title, rev=rev), max_width), 0, Qt.AlignLeft)
    if caption and figures.figure_caption(test_id):
        c.body.addWidget(label(figures.figure_caption(test_id), "muted", wrap=True))
    return c


class WaiverDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle(tr("Waive this run (SRS-DVT-087)"))
        f = QFormLayout(self); self.approver = QLineEdit(); self.rationale = QTextEdit()
        f.addRow(tr("Approver (name, role)"), self.approver); f.addRow(tr("Rationale"), self.rationale)
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
        self.alarm_watches: dict[int, alarms.AlarmWatch] = {}      # step index -> what the console saw
        self.alarm_cards: dict[int, dict] = {}                     # step index -> that card's widgets
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
        v.addWidget(label(f"{self.run['test_id']} · {self.run['unit_id']} · {self._variant()} · {tr('rep')} {self.run['repetition']}", "eyebrow"))
        v.addWidget(label(self.test["title"], "h2"))
        right = QVBoxLayout(); hl.addLayout(right)
        r1 = QHBoxLayout(); self.dot = PulseDot(T.WARN); r1.addWidget(self.dot); self.lbl_timer = label("00:00", "mono", size=16, bold=True); r1.addWidget(self.lbl_timer); right.addLayout(r1)
        self.p_dut = Pill("DUT: —", T.MUTED); right.addWidget(self.p_dut, 0, Qt.AlignRight)
        root.addWidget(head)
        self.stepper = Stepper([t for _, t in self.stages]); root.addWidget(self.stepper)
        self.stack = FadeStack(); root.addWidget(self.stack, 1)
        self.tool_panels = {}            # step index -> inline tool panel (UV sweep runs on the step itself)
        for key, _ in self.stages:
            self.stack.addWidget(self._page(key))
        foot = QHBoxLayout()
        self.btn_leave = QPushButton(tr("Leave wizard (keeps progress)")); self.btn_leave.setProperty("kind", "ghost"); self.btn_leave.clicked.connect(self.left.emit); foot.addWidget(self.btn_leave)
        self.btn_redline = QPushButton(tr("Redline this step")); self.btn_redline.setProperty("kind", "ghost"); self.btn_redline.clicked.connect(self.redline); foot.addWidget(self.btn_redline)
        self.btn_attach = QPushButton(tr("Attach file…")); self.btn_attach.setProperty("kind", "ghost"); self.btn_attach.clicked.connect(self.attach); foot.addWidget(self.btn_attach)
        foot.addStretch()
        self.lbl_err = label("", color=T.BAD, bold=True); foot.addWidget(self.lbl_err)
        self.btn_back = QPushButton(tr("← Back")); self.btn_back.setProperty("kind", "ghost"); self.btn_back.clicked.connect(self._back); foot.addWidget(self.btn_back)
        self.btn_next = QPushButton(tr("Next →")); self.btn_next.setProperty("kind", "big"); self.btn_next.clicked.connect(self.next); foot.addWidget(self.btn_next)
        root.addLayout(foot)
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(1000)

    def _variant(self):
        return ", ".join(f"{k}={v}" for k, v in self.run["variant"].items()) or tr("single")

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
            fc = figure_card(self.run["test_id"], title=self.test["title"], rev=self.cat.version)
            if fc: l.addWidget(fc)
            c = Card(tr("Run")); g = QGridLayout(); c.body.addLayout(g)
            rule = t["applicability"]["rule"]
            rows = [(tr("Method"), self.cat.label("methods", t["method"])), (tr("Phase"), str(self.cat.phase_of(self.run["test_id"])["id"])),
                    (tr("Applicability"), self.cat.label("rules", rule) + (f" ({t['applicability'].get('unit')})" if rule == "SINGLE" else "")),
                    (tr("Variant"), self._variant()), (tr("Repetition"), str(self.run["repetition"])),
                    (tr("Estimated"), f"{t.get('duration_est_min')} {tr('min')}" if t.get("duration_est_min") is not None else "—"),
                    (tr("Requirements"), ", ".join(f"REQ-{r}" for r in t.get("requirement_ids") or []) or tr("— (VCRM pending)")),
                    (tr("Dependencies"), ", ".join(t.get("dependencies") or []) or tr("none"))]
            for i, (k, v) in enumerate(rows):
                g.addWidget(label(k, "muted"), i, 0); g.addWidget(label(v, wrap=True), i, 1)
            l.addWidget(c)
            if t.get("sample_rationale"):
                l.addWidget(label(tr("Why this sample: ") + t["sample_rationale"].strip(), "muted", wrap=True))
            l.addWidget(label(tr("Press Next to begin. The wizard will tell you what to do at every stage; nothing is submitted until the verdict page."), "banner-info", wrap=True))
        elif key == "safety":
            l.addWidget(label(tr("Safety plan — read before touching the unit"), "h1"))
            for s in t.get("safety_plan") or [tr("Safety-critical test")]:
                l.addWidget(label("⚠  " + str(s), "banner-warn", wrap=True))
            self.cb_safety = QCheckBox(tr("I have read the safety plan; the area, PPE and remote controls are prepared")); self.cb_safety.setChecked(bool(self.run["safety_confirmed"]))
            l.addWidget(self.cb_safety)
        elif key == "equipment":
            l.addWidget(label(tr("Equipment and calibration"), "h1"))
            l.addWidget(label(tr("Put these instruments on the bench. A missing or expired calibration record blocks the run (SRS-DVT-085)."), "muted", wrap=True))
            c = Card(); g = QGridLayout(); c.body.addLayout(g); self.eq_ok = True; self.live_pills = {}
            for i, e in enumerate(t["equipment"]):
                g.addWidget(label(self.cat.equipment_label(e), wrap=True), i, 0)
                verify = e.get("verify")
                from .. import bench
                if verify == "none" or bench.instrument_key(e["name"]) is None:      # fixture / consumable / access note
                    g.addWidget(Pill(tr("no calibration needed"), T.MUTED), i, 1)
                elif verify == "live_meter":
                    # verified by the DVT itself: the machine must see the meter and get readings from it — no certificate
                    pill = Pill(tr("checking…"), T.MUTED); g.addWidget(pill, i, 1); self.live_pills[e["name"]] = pill
                    b = QPushButton(tr("Check the meter now")); b.setProperty("kind", "ghost"); b.clicked.connect(self._check_live_meter); g.addWidget(b, i, 2)
                else:
                    cal = self.store.calibration(e["name"]); ok = bool(cal and cal["valid_until"])
                    self.eq_ok &= ok
                    g.addWidget(Pill(trf("cal {id} → {until}", id=cal["calibration_id"], until=cal["valid_until"]) if ok else tr("NO CALIBRATION RECORD"), T.OK if ok else T.WARN), i, 1)
                    b = QPushButton(tr("Record calibration…")); b.setProperty("kind", "ghost"); b.clicked.connect(lambda _, n=e["name"]: self._calibrate(n)); g.addWidget(b, i, 2)
            l.addWidget(c)
            if self.live_pills:
                self.lbl_live = label("", "banner-info", wrap=True); l.addWidget(self.lbl_live)
                self.live_ok = False; self._check_live_meter()
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
            fc = figure_card(self.run["test_id"], i, caption=False, max_width=720, title=self.test["title"], rev=self.cat.version)   # the step text is the caption
            if fc: l.addWidget(fc)
            caps = s.get("capture") or []
            if caps and s.get("auto"):
                # the tool records every value itself — nothing to type; the fields still exist for the review page and the criteria
                l.addWidget(label(tr("Recorded automatically by the test — nothing to type on this step."), "banner-info", wrap=True))
            elif caps:
                c = Card(tr("Record now")); g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8); c.body.addLayout(g)
                for r, name in enumerate(caps):
                    f = self.fields[name]
                    g.addWidget(label(f"{name}" + (f"  [{f['unit']}]" if f.get("unit") else ""), "mono"), r, 0)
                    w_ = self._field_widget(f, name); g.addWidget(w_, r, 1); self.field_widgets[name] = w_
                    if f.get("note"): g.addWidget(label(f["note"], "muted", wrap=True), r, 3)
                    if name in FIELD_MAP and name not in self.run["variant"]:
                        b = QPushButton(tr("⇩ from DUT")); b.setProperty("kind", "ghost"); b.setToolTip(trf("insert live {metric} from the connected machine", metric=FIELD_MAP[name]))
                        b.clicked.connect(lambda _, n=name: self._from_dut(n)); g.addWidget(b, r, 2)
                l.addWidget(c)
            else:
                l.addWidget(label(tr("No data to record for this step — perform it, then press Next."), "muted"))
            if alarms.watches(s):
                self._alarm_card(l, i, s)
            if s.get("tool") in TOOL_TRIGGERS:
                # instrumented step (DVT-SAF-008 door / DVT-SAF-004 thermistor): the console drives the machine and reads the Ophir meter
                b = QPushButton(tr("Measure with the Ophir meter…")); b.setProperty("kind", "big"); b.clicked.connect(lambda _, tool=s["tool"]: self._uvoff_tool(tool)); l.addWidget(b, 0, Qt.AlignLeft)
            if s.get("tool") == "uv_linearity":
                # DVT-OPT-001/002: the sweep runs INLINE on this step (no dialog) — progress here, abort here, and when
                # it finishes the values are written to the run and the wizard moves on to the next step by itself
                from .uvsweep_panel import UvSweepPanel
                panel = UvSweepPanel(self.app, self.run, int(t.get("uv_wavelength_nm") or 405)); self.tool_panels[i] = panel
                panel.applied.connect(lambda vals, files, step=i: self._uvsweep_finished(vals, files, step)); l.addWidget(panel)
            if s.get("tool") == "led_fan_sweep":
                # automatic step (DVT-THM-004): the console drives the fans and the LEDs, waits for settling, hands back the answer and the graph
                b = QPushButton(tr("Run the fan-duty sweep automatically…")); b.setProperty("kind", "big"); b.clicked.connect(self._fansweep_tool); l.addWidget(b, 0, Qt.AlignLeft)
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
                l.addWidget(label(trf("Redlined by {who}: {as_run} — {reason}", who=x["by_whom"], as_run=x["as_run"], reason=x["reason"]), "banner-warn", wrap=True))

    # ------------------------------------------------------------------ alarms
    def _alarm_card(self, l, i: int, s: dict):
        """"Alarms from the machine" — the console's own witness that the alarm popped up.

        Everything on this card comes from the machine's active-alarm list (`/api/state`),
        polled by the DUT monitor: the code, the machine's own text, and the seconds from the
        moment the step opened. Next stays locked until something is seen (or the operator
        records that nothing did, which is a FAIL, not missing data)."""
        expect = [str(c) for c in (s.get("expect_alert") or [])]
        c = Card(tr("Alarms from the machine"))
        c.body.addWidget(label(tr("The console watches the machine's own alarm list — the code, its text and the time are recorded from what it sees, not typed."), "muted", wrap=True))
        if expect:
            c.body.addWidget(label(trf("This step expects: {codes}", codes=", ".join(expect)), "mono"))
        row = QHBoxLayout()
        pill = Pill(tr("watching…"), T.MUTED); row.addWidget(pill)
        detail = label("", "muted", wrap=True); row.addWidget(detail, 1); c.body.addLayout(row)
        live = label("", "mono", wrap=True); c.body.addWidget(live)
        seen = label("", "mono", wrap=True); c.body.addWidget(seen)
        btns = QHBoxLayout()
        b_none = QPushButton(tr("No alarm appeared — record as a failure")); b_none.setProperty("kind", "ghost")
        b_none.setToolTip(tr("Records alarm_raised = false: the machine stayed silent. The run ends FAIL, not BLOCKED."))
        b_none.clicked.connect(lambda _, n=i: self._alarm_none(n)); btns.addWidget(b_none)
        b_hand = QPushButton(tr("No link to the machine — record by hand")); b_hand.setProperty("kind", "ghost")
        b_hand.setToolTip(tr("For the tests that take the machine off the air on purpose (firmware hang, software stack failure): read the alarm off the machine's screen and type it. Logged as recorded by hand."))
        b_hand.clicked.connect(lambda _, n=i: self._alarm_by_hand(n)); btns.addWidget(b_hand)
        btns.addStretch(); c.body.addLayout(btns)
        l.addWidget(c)
        self.alarm_cards[i] = {"pill": pill, "detail": detail, "live": live, "seen": seen, "none": b_none, "hand": b_hand, "expect": s.get("expect_alert") or []}

    def _alarm_watch(self, i: int) -> alarms.AlarmWatch | None:
        """The watch for step `i`, opened the first time that step is shown."""
        if i in self.alarm_watches:
            return self.alarm_watches[i]
        s = (self.test.get("procedure_steps") or [])[i]
        if not alarms.watches(s):
            return None
        st = self.app.dut_state
        w = alarms.AlarmWatch(fields=s.get("capture") or [], expect=s.get("expect_alert") or [],
                              active_now=st.alerts if st.online else ())      # already active = evidence, but not timed
        self.alarm_watches[i] = w
        if w.seen:
            self.store.log("Alarm already active when the step opened", self.app.operator, self.run["run_id"],
                           {"step": i, "codes": [x.alert.raw for x in w.seen]})
        return w

    def _alarm_tick(self):
        """One poll of the machine's alarm list for the step on screen."""
        k = self.key()
        if not k.startswith("step:"):
            return
        i = int(k.split(":")[1])
        w = self.alarm_watches.get(i)
        if w is None:
            return
        st = self.app.dut_state
        new = w.observe(st.alerts, time.monotonic() - self.step_started) if st.online else []
        if new:
            for x in new:
                self.store.log("Alarm seen on the machine", self.app.operator, self.run["run_id"],
                               {"step": i, "code": x.alert.raw, "text": x.alert.text, "at_sec": x.at,
                                "expected": [str(c) for c in (self.alarm_cards.get(i, {}).get("expect") or [])]})
            self._alarm_apply(i, w)
            codes = ", ".join(x.alert.raw for x in new)
            self.app.toast(trf("Alarm from the machine: {codes} — recorded", codes=codes),
                           T.OK if w.state() == alarms.MATCH else T.WARN)
        self._alarm_refresh(i, w)

    def _alarm_apply(self, i: int, w: alarms.AlarmWatch):
        """Write what the console saw into this step's fields and into the run."""
        vals = w.captured()
        for name, v in vals.items():
            widget = self.field_widgets.get(name)
            if widget is None or name in self.run["variant"]:
                continue
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(1 if v else 2)
            else:
                widget.setText(str(v)); widget.setProperty("state", "fromdut")
                widget.style().unpolish(widget); widget.style().polish(widget)
        if vals:
            self.store.set_values(self.run["run_id"], vals, self.app.operator); self.values.update(vals)
            self.app.kick_sync()

    def _alarm_refresh(self, i: int, w: alarms.AlarmWatch):
        card = self.alarm_cards.get(i)
        if not card:
            return
        st = self.app.dut_state
        state = w.state(st.online)
        txt, col = {
            alarms.MATCH: (tr("alarm captured"), T.OK),
            alarms.PRE: (tr("already active"), T.WARN),
            alarms.WRONG: (tr("unexpected code"), T.BAD),
            alarms.NONE: (tr("no alarm — recorded as a failure"), T.BAD),
            alarms.MANUAL: (tr("recorded by hand"), T.WARN),
            alarms.OFFLINE: (tr("no machine"), T.MUTED),
        }.get(state, (tr("watching…"), T.MUTED))
        card["pill"].set(txt, col)
        m = w.match
        if state == alarms.MATCH:
            card["detail"].setText(trf("{code} raised {sec} s after the step opened.", code=m.alert.raw, sec=f"{m.at:.0f}"))
        elif state == alarms.PRE:
            card["detail"].setText(trf("{code} was already active when the step opened — recorded, but the time to the alarm was not measured.", code=m.alert.raw))
        elif state == alarms.WRONG:
            card["detail"].setText(trf("The machine raised {got}, not the expected {want} — recorded as it happened; judge it on the review page.",
                                       got=", ".join(x.alert.raw for x in w.wrong), want=", ".join(str(c) for c in w.expect)))
        elif state == alarms.OFFLINE:
            card["detail"].setText(tr("No link to the machine — the console cannot witness the alarm. Connect it in the header, or record by hand."))
        elif state == alarms.WAITING:
            card["detail"].setText(tr("The machine has raised nothing yet. This step unlocks when it does."))
        else:
            card["detail"].setText("")
        card["live"].setText(trf("active now: {list}", list="  ·  ".join(a.label() for a in st.alerts) if st.alerts else tr("none")))
        card["seen"].setText(trf("seen on this step: {list}", list="  ·  ".join(
            (f"{x.alert.raw} @ {x.at:.0f} s" if x.at is not None else trf("{code} (already active)", code=x.alert.raw)) for x in w.seen) or tr("nothing")))
        card["none"].setVisible(not w.witnessed and not w.by_hand)
        card["hand"].setVisible(not w.witnessed and not st.online and not w.no_alarm)
        if self.key() == f"step:{i}":
            self.btn_next.setEnabled(w.open)

    def _alarm_none(self, i: int):
        w = self.alarm_watches.get(i)
        if w is None or QMessageBox.question(
                self, tr("No alarm"),
                tr("Record that the machine raised no alarm on this step?\n\nalarm_raised = false is written, so this run ends FAIL — a silent machine is a result, not missing data."),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        w.no_alarm = True
        self.store.log("No alarm on the machine", self.app.operator, self.run["run_id"], {"step": i})
        self._alarm_apply(i, w); self._alarm_refresh(i, w)

    def _alarm_by_hand(self, i: int):
        w = self.alarm_watches.get(i)
        if w is None or QMessageBox.question(
                self, tr("Record by hand"),
                tr("The console has no link to the machine, so it cannot witness the alarm.\n\nRecord this step's alarm by hand from the machine's screen? The run keeps a note that it was not witnessed by the console."),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        w.by_hand = True
        self.store.log("Alarm recorded by hand (no link to the machine)", self.app.operator, self.run["run_id"], {"step": i})
        self._alarm_refresh(i, w)

    def _field_widget(self, f, name):
        fixed = self.run["variant"].get(name); v = self.values.get(name)
        if fixed is not None:
            w = QLineEdit(str(fixed)); w.setReadOnly(True); w.setToolTip(tr("set by the sweep / case matrix")); return w
        if f["type"] == "bool":
            w = QComboBox(); w.addItems(["", tr("yes / true"), tr("no / false")]); w.setCurrentIndex(0 if v is None else (1 if v else 2)); return w
        if f["type"] == "enum":
            w = QComboBox(); w.addItems([""] + [str(x) for x in f["values"]]); w.setCurrentText("" if v is None else str(v)); return w
        w = QLineEdit("" if v is None else str(v)); w.setPlaceholderText(tr({"float": "number", "int": "integer"}.get(f["type"], "text")) + (f" · {f['range'][0]}–{f['range'][1]}" if f.get("range") else ""))
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
        # on the done page the run is committed: Back cannot re-open a stage, so it leaves the wizard (back to the console)
        self.btn_back.setEnabled(i > 0); self.btn_back.setText(tr("← Back to console") if k == "done" else tr("← Back"))
        self.btn_redline.setVisible(is_step); self.btn_attach.setVisible(is_step or k == "review")
        self.btn_next.setVisible(k not in ("review", "done")); self.btn_leave.setVisible(k != "done")
        self.btn_next.setEnabled(True)
        if is_step:
            self.store.set_step(self.run["run_id"], int(k.split(":")[1])); self.step_started = time.monotonic()
            panel = self.tool_panels.get(int(k.split(":")[1]))
            if panel is not None: panel.on_shown()          # one live meter check when the step becomes visible
            w = self._alarm_watch(int(k.split(":")[1]))     # the step's alarm watch opens with it
            if w is not None: self._alarm_refresh(int(k.split(":")[1]), w)
        if k == "pre":
            self.dut_hint.setText(self._dut_hint())
        if k == "review":
            self._fill_review(); self.evaluate()

    def _back(self):
        if self.key() == "done":
            self.left.emit()           # the app closes the wizard and shows the console with the next action
        else:
            self.go(self.index - 1, forward=False)

    def next(self):
        k = self.key()
        if k == "safety":
            if not self.cb_safety.isChecked(): self.lbl_err.setText(tr("Acknowledge the safety plan to continue.")); return
            self.store.confirm_safety(self.run["run_id"], self.app.operator)
        elif k == "equipment":
            if getattr(self, "live_pills", None) and not self._check_live_meter():
                self.lbl_err.setText(tr("The machine does not see the StarBright, or it gives no reading — connect it to the machine's USB, switch it on, press 'Check the meter now'.")); return
            if not self.eq_ok and QMessageBox.question(self, tr("Calibration"), tr("An instrument has no valid calibration record (SRS-DVT-085).\nRecord it now, or continue with a supervisor override (logged)?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            if not self.eq_ok: self.store.log("Blocker override", self.app.operator, self.run["run_id"], {"blockers": ["calibration"], "reason": "operator override in wizard"})
        elif k == "pre":
            if not all(cb.isChecked() for cb in self.pre_boxes): self.lbl_err.setText(tr("Tick every precondition first.")); return
            self.store.confirm_preconditions(self.run["run_id"], self.app.operator)
        elif k.startswith("step:"):
            w = self.alarm_watches.get(int(k.split(":")[1]))
            if w is not None and not w.open:
                # the console must witness the alarm before the step is passed; if the machine
                # stayed silent that is recorded as such (alarm_raised = false), not skipped
                self.lbl_err.setText(tr("The machine has raised no alarm yet — wait for it, or record that none appeared.")
                                     if self.app.dut_state.online else
                                     tr("No link to the machine — connect it in the header, or record this step by hand."))
                return
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
                out[name] = (w.currentIndex() == 1) if f["type"] == "bool" else s      # index, not text: the labels are translated
            else:
                s = w.text().strip(); w.setProperty("state", "")
                if not s: continue
                try:
                    out[name] = float(s) if f["type"] == "float" else int(float(s)) if f["type"] == "int" else s
                except ValueError:
                    w.setProperty("state", "error"); w.style().unpolish(w); w.style().polish(w)
                    raise ValueError(trf("{name}: enter a {kind}", name=name, kind=tr("number" if f["type"] == "float" else "whole number")))
                rng = f.get("range")
                if rng and not (rng[0] <= out[name] <= rng[1]):
                    w.setProperty("state", "error"); w.style().unpolish(w); w.style().polish(w)
                    raise ValueError(trf("{name}: {value} is outside the plausible range {lo}–{hi}", name=name, value=out[name], lo=rng[0], hi=rng[1]))
                w.style().unpolish(w); w.style().polish(w)
        return out

    def _from_dut(self, name):
        st = self.app.dut_state
        if not st.online:
            self.lbl_err.setText(tr("No machine connected — set the DUT address in the header.")); return
        v = st.metrics.get(FIELD_MAP[name])
        if v is None:
            self.lbl_err.setText(trf("The machine does not report {metric} right now.", metric=FIELD_MAP[name])); return
        w = self.field_widgets[name]
        if isinstance(w, QLineEdit):
            w.setText(f"{v:.2f}" if isinstance(v, float) else str(v)); w.setProperty("state", "fromdut"); w.style().unpolish(w); w.style().polish(w)
            self.store.log("Value captured from DUT", self.app.operator, self.run["run_id"], {"field": name, "metric": FIELD_MAP[name], "value": v, "url": st.url})

    def _uvsweep_finished(self, vals: dict, files: list, step: int):
        """The inline sweep wrote the run: fill the fields on every page, then move to the next step."""
        self._uvoff_applied(vals, files)
        self.app.toast(tr("Sweep finished — moving to the next step"), T.OK)
        if self.key() == f"step:{step}":
            QTimer.singleShot(1200, lambda: self.key() == f"step:{step}" and self.go(self.index + 1))

    def _uvsweep_tool(self):
        from .uvsweep_dialog import UvSweepDialog
        dlg = UvSweepDialog(self.app, self.run, self, wavelength=int(self.test.get("uv_wavelength_nm") or 405))
        dlg.applied.connect(self._uvoff_applied)
        dlg.exec()

    def _fansweep_tool(self):
        from .fansweep_dialog import FanSweepDialog
        dlg = FanSweepDialog(self.app, self.run, self)
        dlg.applied.connect(self._fansweep_applied)
        dlg.exec()

    def _fansweep_applied(self, by_run: dict):
        """The sweep wrote every duty row of this unit; this run's values come back into the wizard fields."""
        vals = by_run.get(self.run["run_id"], {})
        for name, v in vals.items():
            w = self.field_widgets.get(name)
            if isinstance(w, QLineEdit):
                w.setText(f"{v:.2f}" if isinstance(v, float) else str(v)); w.setProperty("state", "fromdut"); w.style().unpolish(w); w.style().polish(w)
            elif isinstance(w, QComboBox) and self.fields[name]["type"] == "bool":
                w.setCurrentIndex(1 if v else 2)
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
        self.values.update(vals)
        others = [r for r in by_run if r != self.run["run_id"]]
        self.app.toast(trf("Fan sweep applied: this row filled, {n} other duty rows completed automatically", n=len(others)), T.OK)
        self.app.refresh_all()

    def _uvoff_tool(self, tool: str = "uv_off_timing"):
        from .uvoff_dialog import UvOffDialog
        try: defaults = self._collect()          # e.g. sensor_position already recorded on step 1 of DVT-SAF-004
        except Exception: defaults = {}  # noqa: BLE001
        dlg = UvOffDialog(self.app, self.run, self, trigger=TOOL_TRIGGERS.get(tool, "door"), defaults=defaults)
        dlg.applied.connect(self._uvoff_applied)
        dlg.exec()

    def _uvoff_applied(self, vals: dict, files: list):
        """Values measured by the Ophir sequence: fill the widgets (any step — all pages exist) and remember them."""
        for name, v in vals.items():
            w = self.field_widgets.get(name)
            if isinstance(w, QLineEdit):
                w.setText(f"{v:.3f}" if isinstance(v, float) else str(v)); w.setProperty("state", "fromdut"); w.style().unpolish(w); w.style().polish(w)
            elif isinstance(w, QComboBox) and self.fields[name]["type"] == "bool":
                w.setCurrentIndex(1 if v else 2)
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
        self.values.update(vals)
        self.app.toast(trf("Ophir measurement applied: {names}", names=", ".join(vals) or "—") + (f" · {len(files)} " + tr("files attached") if files else ""), T.OK)

    def _dut_hint(self):
        st = self.app.dut_state
        if not st.online: return tr("Machine: not connected. Connect it in the header to capture values and drive it from DUT Control.")
        m = st.metrics
        door = st.flags.get("doorOpen")
        return trf("Machine {url}: {mode} · chamber {chamber} °C · LED max {led} °C · door {door} — use DUT Control if the preconditions need a different state.",
                   url=st.url, mode=tr(st.mode), chamber=m.get("chamberTemp"), led=m.get("ledTempMax"),
                   door=tr("not reported") if door is None else tr("OPEN" if door else "closed"))

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
        self._done("WAIVED", trf("approved by {who}", who=dlg.approver.text()))

    def reject(self):
        reason, ok = QInputDialog.getText(self, tr("Reject run"), tr("Reason (ambient drift, warm start, instrumentation fault…):"))
        if not ok or not reason.strip(): return
        n = self.store.reject_run(self.run["run_id"], reason, self.app.operator)
        self.app.kick_sync(); self.finished.emit(self.run["run_id"], "REJECTED")
        self.app.toast(trf("Run rejected ({n} run(s) affected)", n=len(n)), T.WARN)

    def _done(self, verdict, detail):
        col = T.VERDICT.get(verdict, T.WARN)
        self.done_title.setText(tr(f"Run finished — {verdict}")); self.done_title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {col};")
        self.done_body.setText({"PASS": tr("All pass criteria met. The result is committed and exported."),
                                "FAIL": tr("Pass criteria not met. An NCR was opened automatically — describe the anomaly in the NCR list."),
                                "BLOCKED": trf("The criterion could not be evaluated: {detail}. The run is recorded as BLOCKED, not as a pass.", detail=detail),
                                "WAIVED": trf("Waived ({detail}). Counted separately from PASS in every view.", detail=detail)}.get(verdict, detail))
        na = self.engine.next_action(self.run["unit_id"])
        self.done_next.setText(tr("Next for this unit: ") + na.message)
        self.dot.set_color(col); self._t.stop()
        self.go(len(self.stages) - 1); self.app.kick_sync(); self.finished.emit(self.run["run_id"], verdict)

    # ------------------------------------------------------------------ misc
    def redline(self):
        k = self.key()
        if not k.startswith("step:"): return
        i = int(k.split(":")[1])
        as_run, ok = QInputDialog.getMultiLineText(self, trf("Redline step {n}", n=i + 1), tr("How was the step actually performed?"))
        if not ok or not as_run.strip(): return
        reason, ok = QInputDialog.getText(self, tr("Redline"), tr("Reason:"))
        if not ok or not reason.strip(): return
        self.store.add_redline(self.run["run_id"], i, as_run, reason, self.app.operator); self.app.toast(tr("Redline recorded"), T.WARN)

    def attach(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Attach file (log, capture, photo)"))
        if not path: return
        import hashlib, shutil
        from pathlib import Path
        src = Path(path); dst_dir = self.app.data / "export" / "attachments" / self.run["run_id"].replace("|", "_"); dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name; shutil.copy2(src, dst)
        self.store.add_attachment(self.run["run_id"], src.name, str(dst), src.suffix.lstrip("."), hashlib.sha256(dst.read_bytes()).hexdigest())
        self.app.kick_sync(); self.app.toast(trf("Attached {name}", name=src.name), T.OK)

    def _check_live_meter(self) -> bool:
        """Equipment `verify: live_meter`: ask the machine whether the StarBright is on its USB and delivering readings."""
        st = self.app.dut_state
        if not st.online:
            info, ok, text = {}, False, tr("machine offline")
        else:
            try:
                from .dut import make_client
                info = make_client(self.app.machine_url, timeout=8.0).meter() or {}
            except Exception as e:  # noqa: BLE001
                info = {"present": False, "message": str(e)}
            reading = info.get("reading_mw_cm2")
            ok = bool(info.get("present")) and isinstance(reading, (int, float))
            text = (trf("connected · {head} · {reading} mW/cm²", head=(info.get("head") or "").split()[2] if len((info.get("head") or "").split()) > 2 else (info.get("head") or "?"), reading=f"{reading:.3f}") if ok
                    else (tr("connected, no reading") if info.get("present") else tr("NOT DETECTED")))
        for pill in self.live_pills.values():
            pill.set(text, T.OK if ok else T.BAD)
        self.live_ok = ok
        if hasattr(self, "lbl_live"):
            self.lbl_live.setText(tr("Verified by the DVT through the machine: the meter is connected and delivering readings — no calibration certificate is required for this test.") if ok
                                  else tr("The DVT verifies the meter itself: plug the StarBright's USB cable into the machine, switch it on and press 'Check the meter now'. Next stays locked until the machine reports a reading.") + (f" ({info.get('message')})" if info.get("message") else ""))
        self.store.log("Live meter check", self.app.operator, self.run["run_id"], {"ok": ok, "info": {k: info.get(k) for k in ("present", "head", "wavelength_nm", "reading_mw_cm2", "message")}})
        return ok

    def _calibrate(self, instrument):
        cid, ok = QInputDialog.getText(self, tr("Calibration record"), f"{instrument}\n{tr('Certificate id:')}")
        if not ok: return
        until, ok = QInputDialog.getText(self, tr("Calibration record"), tr("Valid until (YYYY-MM-DD):"))
        if not ok: return
        self.store.set_calibration(instrument, cid, until)
        idx = self.index; self.stack.removeWidget(self.stack.widget(idx)); self.stack.insertWidget(idx, self._page("equipment")); self.stack.setCurrentIndex(idx)

    def _tick(self):
        el = int(time.monotonic() - self.step_started); self.lbl_timer.setText(f"{el // 60:02d}:{el % 60:02d}")
        self._alarm_tick()               # the machine's alarm list, every second (DUT poll: 2 s)
        st = self.app.dut_state
        self.p_dut.set(f"DUT: {st.mode}" + (f" · {st.metrics.get('chamberTemp')} °C" if st.online and st.metrics.get("chamberTemp") is not None else ""),
                       T.OK if st.online and st.mode == "IDLE" else T.WARN if st.online else T.MUTED)
