#!/usr/bin/env python3
"""sCure DVT — desktop application (PySide6).

    python -m dvt_tool.app [--catalog ../catalog/DVT_test_catalog.yaml] [--data ~/.scure-dvt]

Left: units + progress. Centre: the wizard for the selected unit — next
action, blockers, preconditions checklist, safety plan, step-by-step data
entry, redlines, verdict. Right: run list for the current test, NCRs,
Drive sync status. Every saved result is exported and pushed to Google
Drive in the background (SRS-DVT-110…112).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QGridLayout, QGroupBox, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QMessageBox, QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QScrollArea, QFrame,
                               QInputDialog, QFileDialog, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
                               QDialog, QDialogButtonBox, QTextEdit, QFormLayout, QStackedWidget)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dvt_tool.catalog import Catalog  # noqa: E402
from dvt_tool.store import Store  # noqa: E402
from dvt_tool.engine import Engine  # noqa: E402
from dvt_tool.export import Exporter  # noqa: E402
from dvt_tool.drive import SyncConfig, Syncer, SyncStatus  # noqa: E402
from dvt_tool.dashboard import DashboardPage, SUBSYSTEM_COLORS, SUBSYSTEM_ICONS  # noqa: E402

C_OK, C_WARN, C_BAD, C_MUTE, C_ACC = "#5cbf86", "#d9a93a", "#e06a60", "#93a4b3", "#3fb8ba"
STYLE = """
QMainWindow, QWidget { background: #0f1418; color: #e6ebf0; font-family: 'Segoe UI'; font-size: 13px; }
QGroupBox { border: 1px solid #2a353f; border-radius: 8px; margin-top: 14px; padding: 10px 12px 8px; background: #171f26; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #93a4b3; font-size: 11px; letter-spacing: 1px; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QPlainTextEdit { background: #0f1418; border: 1px solid #2a353f; border-radius: 6px; padding: 6px 8px; }
QPushButton { background: #3fb8ba; color: #04191a; border: 0; border-radius: 7px; padding: 8px 14px; font-weight: 700; }
QPushButton:disabled { background: #26313a; color: #6c7a86; }
QPushButton[secondary="true"] { background: #26313a; color: #e6ebf0; }
QPushButton[danger="true"] { background: #6b2a24; color: #ffd6d2; }
QListWidget, QTableWidget { background: #0f1418; border: 1px solid #2a353f; border-radius: 6px; font-size: 12px; }
QHeaderView::section { background: #171f26; color: #93a4b3; border: 0; padding: 4px; }
QCheckBox { spacing: 8px; }
QLabel[role="pill"] { border-radius: 9px; padding: 2px 9px; font-weight: 700; font-size: 12px; }
QLabel[role="err"] { background: #4a1f1b; color: #ffb4ad; padding: 8px 12px; font-weight: 600; border-radius: 6px; }
QLabel[role="info"] { background: #1e2a33; color: #c5d0da; padding: 8px 12px; border-radius: 6px; }
QLabel[role="safety"] { background: #5a3d05; color: #ffd98a; padding: 10px 12px; border-radius: 6px; font-weight: 600; }
"""


def pill(text, color):
    lb = QLabel(text); lb.setProperty("role", "pill"); lb.setStyleSheet(f"background: {color}33; color: {color};"); return lb


def set_pill(lb, text, color):
    lb.setText(text); lb.setStyleSheet(f"background: {color}33; color: {color};")


class SyncWorker(QThread):
    done = Signal(object)

    def __init__(self, exporter: Exporter, syncer: Syncer):
        super().__init__(); self.exporter, self.syncer = exporter, syncer

    def run(self):
        try:
            files = self.exporter.export_all()
            self.done.emit(self.syncer.sync(files))
        except Exception as e:  # noqa: BLE001
            self.done.emit(SyncStatus(self.syncer.cfg.mode, False, None, f"{type(e).__name__}: {e}"))


class WaiverDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Waive this run (SRS-DVT-087)")
        f = QFormLayout(self)
        self.approver = QLineEdit(); self.rationale = QTextEdit()
        f.addRow("Approver (name, role)", self.approver); f.addRow("Rationale", self.rationale)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)


class MainWindow(QMainWindow):
    def __init__(self, catalog: Catalog, data_dir: Path):
        super().__init__()
        self.cat = catalog
        self.data = data_dir; self.data.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data / "campaign.db")
        self.engine = Engine(self.cat, self.store)
        self.cfg = SyncConfig.load(self.data / "sync.json")
        if not self.cfg.credentials_file.is_absolute():
            self.cfg.credentials_file = self.data / self.cfg.credentials_file
        if not self.cfg.token_file.is_absolute():
            self.cfg.token_file = self.data / self.cfg.token_file
        self.exporter = Exporter(self.cat, self.store, self.data / "export", self.cfg.campaign)
        try:
            self.syncer = Syncer(self.cfg, self.store, self.data / "export")
        except Exception as e:  # noqa: BLE001
            self.syncer = Syncer(SyncConfig(mode="off"), self.store, self.data / "export")
            self._sync_err = str(e)
        else:
            self._sync_err = None
        self.operator = getpass.getuser()
        self.current_run: dict | None = None
        self.field_widgets: dict[str, QWidget] = {}
        self.setWindowTitle(f"sCure DVT — catalog v{self.cat.version}")
        self.resize(1440, 900)
        self._build()
        self.refresh_all()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(14, 10, 14, 10)
        head = QHBoxLayout()
        t = QLabel("sCure DVT"); t.setFont(QFont("Segoe UI", 15, QFont.DemiBold)); head.addWidget(t)
        self.lbl_prog = QLabel(""); self.lbl_prog.setStyleSheet(f"color: {C_MUTE}; font-family: Consolas;"); head.addWidget(self.lbl_prog)
        head.addStretch()
        head.addWidget(QLabel("Operator")); self.ed_operator = QLineEdit(self.operator); self.ed_operator.setFixedWidth(160)
        self.ed_operator.textChanged.connect(lambda s: setattr(self, "operator", s.strip())); head.addWidget(self.ed_operator)
        self.p_sync = pill("Drive: —", C_MUTE); head.addWidget(self.p_sync)
        b = QPushButton("Sync now"); b.setProperty("secondary", True); b.clicked.connect(self.sync_now); head.addWidget(b)
        b = QPushButton("Drive settings"); b.setProperty("secondary", True); b.clicked.connect(self.drive_settings); head.addWidget(b)
        v.addLayout(head)

        body = QHBoxLayout(); body.setSpacing(12); v.addLayout(body, 1)
        # ---- navigation rail
        nav = QFrame(); nav.setFixedWidth(200); nav.setStyleSheet("QFrame { background: #121920; border: 1px solid #2a353f; border-radius: 8px; }")
        nl = QVBoxLayout(nav); nl.setContentsMargins(8, 10, 8, 10); nl.setSpacing(4)
        self.nav_buttons = {}
        def nav_btn(key, text):
            b = QPushButton(text); b.setProperty("secondary", True); b.setCheckable(True)
            b.setStyleSheet("QPushButton { text-align: left; padding: 9px 12px; background: transparent; color: #e6ebf0; border-radius: 6px; }"
                            "QPushButton:checked { background: #1e2a33; color: #3fb8ba; }")
            b.clicked.connect(lambda: self.show_page(key)); nl.addWidget(b); self.nav_buttons[key] = b; return b
        nav_btn("dashboard", "🏠  Dashboard"); nav_btn("console", "📋  Test Console"); nav_btn("reports", "📊  Reports (Drive folder)")
        sec = QLabel("TEST SUBSYSTEMS"); sec.setStyleSheet("color: #93a4b3; font-size: 10px; letter-spacing: 1px; margin-top: 10px;"); nl.addWidget(sec)
        self.nav_sub = {}
        for name in ("Thermal", "Electrical", "Safety", "Environmental"):
            row = QHBoxLayout(); lb = QLabel(f"{SUBSYSTEM_ICONS.get(name, '')}  {name}"); lb.setStyleSheet(f"color: #c5d0da; padding-left: 6px;")
            cnt = QLabel("0"); cnt.setAlignment(Qt.AlignCenter); cnt.setFixedSize(26, 18)
            cnt.setStyleSheet(f"background: #1e2a33; color: {SUBSYSTEM_COLORS.get(name, '#93a4b3')}; border-radius: 9px; font-size: 11px; font-weight: 700;")
            row.addWidget(lb); row.addStretch(); row.addWidget(cnt); w = QWidget(); w.setLayout(row); nl.addWidget(w); self.nav_sub[name] = cnt
            w.mousePressEvent = lambda ev, n=name: (self.show_page("dashboard"), self.dashboard.set_filter(n))
        nl.addStretch()
        self.health = QLabel("● System Health\nAll systems nominal"); self.health.setStyleSheet("color: #5cbf86; font-size: 11px; padding: 6px;"); nl.addWidget(self.health)
        body.addWidget(nav)
        self.pages = QStackedWidget(); body.addWidget(self.pages, 1)
        # page 0: dashboard
        self.dashboard = DashboardPage(self.engine, self.store.get_meta("machine_url", "http://testingcm5.local:3001"))
        self.dashboard.openTest.connect(self.open_test_from_dashboard)
        self.dashboard.machine.editingFinished.connect(lambda: self.store.set_meta("machine_url", self.dashboard.machine.text().strip()))
        self.pages.addWidget(self.dashboard)
        # page 1: test console (the wizard)
        split = QSplitter(Qt.Horizontal); self.pages.addWidget(split)

        # ---- left: units
        left = QWidget(); ll = QVBoxLayout(left)
        g = QGroupBox("UNITS"); gl = QVBoxLayout(g)
        self.units = QListWidget(); self.units.currentItemChanged.connect(lambda *_: self.refresh_unit()); gl.addWidget(self.units)
        row = QHBoxLayout()
        b = QPushButton("Freeze config"); b.setProperty("secondary", True); b.clicked.connect(self.freeze_config); row.addWidget(b)
        b = QPushButton("Sign phase TRR"); b.setProperty("secondary", True); b.clicked.connect(self.sign_phase); row.addWidget(b)
        gl.addLayout(row)
        b = QPushButton("Calibration records"); b.setProperty("secondary", True); b.clicked.connect(self.calibration_dialog); gl.addWidget(b)
        ll.addWidget(g)
        g = QGroupBox("SEARCH"); gl = QVBoxLayout(g)
        self.search = QLineEdit(); self.search.setPlaceholderText("run, error code, NCR text…"); self.search.returnPressed.connect(self.do_search); gl.addWidget(self.search)
        self.search_out = QListWidget(); gl.addWidget(self.search_out); ll.addWidget(g, 1)
        split.addWidget(left)

        # ---- centre: wizard
        centre = QWidget(); cl = QVBoxLayout(centre)
        self.lbl_next = QLabel(""); self.lbl_next.setProperty("role", "info"); self.lbl_next.setWordWrap(True); cl.addWidget(self.lbl_next)
        self.lbl_block = QLabel(""); self.lbl_block.setProperty("role", "err"); self.lbl_block.setWordWrap(True); self.lbl_block.hide(); cl.addWidget(self.lbl_block)
        row = QHBoxLayout()
        self.btn_start = QPushButton("Start this run"); self.btn_start.clicked.connect(self.start_run); row.addWidget(self.btn_start)
        self.btn_override = QPushButton("Start anyway (supervisor)"); self.btn_override.setProperty("danger", True); self.btn_override.clicked.connect(lambda: self.start_run(override=True)); row.addWidget(self.btn_override)
        row.addStretch(); cl.addLayout(row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.wiz = QWidget(); self.wiz_l = QVBoxLayout(self.wiz); self.wiz_l.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.wiz); cl.addWidget(self.scroll, 1)
        split.addWidget(centre)

        # ---- right: runs of current test, NCRs
        right = QWidget(); rl = QVBoxLayout(right)
        g = QGroupBox("RUNS — CURRENT TEST"); gl = QVBoxLayout(g)
        self.runs_tbl = QTableWidget(0, 5); self.runs_tbl.setHorizontalHeaderLabels(["Unit", "Variant", "Rep", "Status", "Verdict"])
        self.runs_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.runs_tbl.verticalHeader().hide()
        gl.addWidget(self.runs_tbl); rl.addWidget(g, 2)
        g = QGroupBox("OPEN NCRs"); gl = QVBoxLayout(g)
        self.ncr_list = QListWidget(); gl.addWidget(self.ncr_list)
        b = QPushButton("Close selected NCR"); b.setProperty("secondary", True); b.clicked.connect(self.close_ncr); gl.addWidget(b)
        rl.addWidget(g, 1)
        g = QGroupBox("LOG"); gl = QVBoxLayout(g)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(400); gl.addWidget(self.log); rl.addWidget(g, 1)
        split.addWidget(right)
        split.setSizes([260, 760, 420])
        self.show_page("dashboard")

    # ------------------------------------------------------------------ pages
    def show_page(self, key):
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        if key == "reports":
            import subprocess, os as _os
            target = self.cfg.folder_path if (self.cfg.mode == "folder" and self.cfg.folder_path) else (self.data / "export")
            try:
                _os.startfile(str(target))       # Windows Explorer
            except Exception:  # noqa: BLE001
                subprocess.Popen(["xdg-open", str(target)])
            self.nav_buttons["reports"].setChecked(False); return
        self.pages.setCurrentIndex(0 if key == "dashboard" else 1)
        if key == "dashboard":
            self.dashboard.refresh()

    def open_test_from_dashboard(self, test_id):
        """Double-click on a matrix row: jump to the console on the first unit
        that still owes a run of this test (or the first applicable unit)."""
        units = self.cat.applicable_units(test_id)
        pending = [r["unit_id"] for r in self.store.runs(test_id) if r["status"] in ("NOT_STARTED", "IN_PROGRESS")]
        target = pending[0] if pending else (units[0] if units else None)
        self.show_page("console")
        if target:
            for i in range(self.units.count()):
                if self.units.item(i).data(Qt.UserRole) == target:
                    self.units.setCurrentRow(i); break
        self._fill_runs(test_id)

    # ------------------------------------------------------------------ refresh
    def refresh_all(self):
        cur = self.units.currentItem().text() if self.units.currentItem() else None
        self.units.blockSignals(True); self.units.clear()
        prog = self.engine.progress()
        for u in self.cat.unit_ids():
            d = prog["perUnit"][u]
            it = QListWidgetItem(f"{u}   phase {d['phase']}   {d['done']}/{d['total']}")
            it.setData(Qt.UserRole, u); self.units.addItem(it)
            if u == cur: self.units.setCurrentItem(it)
        if self.units.currentItem() is None and self.units.count():
            self.units.setCurrentRow(0)
        self.units.blockSignals(False)
        self.lbl_prog.setText(f"{prog['done']}/{prog['total']} runs · PASS {prog['PASS']} · FAIL {prog['FAIL']} · BLOCKED {prog['BLOCKED']} · WAIVED {prog['WAIVED']} · NCR open {prog['openNcrs']}")
        self.ncr_list.clear()
        for n in self.store.ncrs(open_only=True):
            it = QListWidgetItem(f"{n['ncr_id']}  {n['run_id']}  {n['description'][:60]}"); it.setData(Qt.UserRole, n["ncr_id"]); self.ncr_list.addItem(it)
        self._show_sync(self.syncer.status if not self._sync_err else SyncStatus(self.cfg.mode, False, None, self._sync_err))
        summ = self.engine.subsystem_summary()
        for name, cnt in self.nav_sub.items():
            cnt.setText(str(summ.get(name, {}).get("tests", 0)))
        failed = sum(s["failed"] for s in summ.values()); blocked = sum(s["blocked"] for s in summ.values())
        if failed:
            self.health.setText(f"● System Health\n{failed} test(s) FAILED · {prog['openNcrs']} NCR open"); self.health.setStyleSheet("color: #e06a60; font-size: 11px; padding: 6px;")
        elif blocked:
            self.health.setText(f"● System Health\n{blocked} test(s) BLOCKED (missing data / threshold)"); self.health.setStyleSheet("color: #d9a93a; font-size: 11px; padding: 6px;")
        else:
            self.health.setText(f"● System Health\nAll systems nominal\nSRS-DVT-SW Rev B · catalog v{self.cat.version}"); self.health.setStyleSheet("color: #5cbf86; font-size: 11px; padding: 6px;")
        if self.pages.currentIndex() == 0:
            self.dashboard.refresh()
        self.refresh_unit()

    def unit_id(self) -> str | None:
        it = self.units.currentItem(); return it.data(Qt.UserRole) if it else None

    def refresh_unit(self):
        u = self.unit_id()
        if not u:
            return
        na = self.engine.next_action(u)
        self.lbl_next.setText(na.message)
        if na.blockers:
            self.lbl_block.setText("Blocked:\n• " + "\n• ".join(b.text for b in na.blockers)); self.lbl_block.show()
        else:
            self.lbl_block.hide()
        self.btn_start.setEnabled(na.run is not None and not na.blockers and na.run["status"] == "NOT_STARTED")
        self.btn_override.setEnabled(na.run is not None and bool(na.blockers) and na.run["status"] == "NOT_STARTED")
        self.btn_start.setText("Start this run" if not (na.run and na.run["status"] == "IN_PROGRESS") else "Resume")
        self._fill_runs(na.run["test_id"] if na.run else None)
        if na.run and na.run["status"] == "IN_PROGRESS":
            self.open_run(na.run["run_id"])
        elif self.current_run and self.current_run["status"] == "DONE":
            pass
        else:
            self._clear_wizard()
            if na.run:
                self._show_test_header(na.run)

    def _fill_runs(self, test_id):
        self.runs_tbl.setRowCount(0)
        if not test_id:
            return
        for r in self.store.runs(test_id):
            i = self.runs_tbl.rowCount(); self.runs_tbl.insertRow(i)
            cells = [r["unit_id"], ", ".join(f"{k}={v}" for k, v in r["variant"].items()) or "—", str(r["repetition"]), r["status"], r["verdict"] or ""]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c == 4 and txt:
                    it.setForeground(QColor({"PASS": C_OK, "FAIL": C_BAD, "BLOCKED": C_WARN, "WAIVED": "#b39ddb"}.get(txt, C_MUTE)))
                self.runs_tbl.setItem(i, c, it)

    def _clear_wizard(self):
        while self.wiz_l.count():
            w = self.wiz_l.takeAt(0).widget()
            if w: w.deleteLater()
        self.field_widgets = {}

    def _show_test_header(self, run):
        t = self.cat.tests[run["test_id"]]
        g = QGroupBox(f"{run['test_id']} — {t['title']}"); l = QVBoxLayout(g)
        p = QLabel(t.get("purpose", "").strip()); p.setWordWrap(True); l.addWidget(p)
        meta = QLabel(f"Method {t['method']} · phase {self.cat.phase_of(run['test_id'])['id']} · applicability {t['applicability']['rule']} · "
                      f"variant {', '.join(f'{k}={v}' for k, v in run['variant'].items()) or '—'} · rep {run['repetition']} · est. {t.get('duration_est_min')} min")
        meta.setStyleSheet(f"color: {C_MUTE};"); meta.setWordWrap(True); l.addWidget(meta)
        if t.get("requirement_ids"):
            l.addWidget(QLabel("Requirements: " + ", ".join(f"REQ-{r}" for r in t["requirement_ids"])))
        self.wiz_l.addWidget(g)

    # ------------------------------------------------------------------ run lifecycle
    def start_run(self, override=False):
        u = self.unit_id(); na = self.engine.next_action(u)
        if not na.run:
            return
        if not self.operator:
            QMessageBox.warning(self, "Operator", "Enter the operator name first."); return
        if na.run["status"] == "IN_PROGRESS":
            self.open_run(na.run["run_id"]); return
        if override:
            reason, ok = QInputDialog.getText(self, "Supervisor override", "Reason for starting despite blockers (recorded):")
            if not ok or not reason.strip():
                return
            self.store.log("Blocker override", self.operator, na.run["run_id"], {"blockers": [b.text for b in na.blockers], "reason": reason})
        self.store.start_run(na.run["run_id"], self.operator)
        self._log(f"started {na.run['run_id']}")
        self.open_run(na.run["run_id"])

    def open_run(self, run_id):
        self.current_run = run = self.store.run(run_id)
        t = self.cat.tests[run["test_id"]]
        self._clear_wizard(); self._show_test_header(run)
        # safety plan (SRS-DVT-084)
        if t.get("safety_critical") or t.get("safety_plan"):
            g = QGroupBox("SAFETY PLAN — read before proceeding"); l = QVBoxLayout(g)
            lb = QLabel("\n".join("• " + s for s in t.get("safety_plan") or ["Safety-critical test"])); lb.setProperty("role", "safety"); lb.setWordWrap(True); l.addWidget(lb)
            cb = QCheckBox("I have read the safety plan and the area is prepared"); cb.setChecked(bool(run["safety_confirmed"]))
            cb.toggled.connect(lambda on: on and self.store.confirm_safety(run_id, self.operator)); l.addWidget(cb)
            self.cb_safety = cb; self.wiz_l.addWidget(g)
        else:
            self.cb_safety = None
        # equipment
        if t.get("equipment"):
            g = QGroupBox("EQUIPMENT / CALIBRATION"); l = QVBoxLayout(g)
            for e in t["equipment"]:
                c = self.store.calibration(e["name"])
                txt = f"{e['name']}  —  {'cal ' + c['calibration_id'] + ' valid to ' + c['valid_until'] if c and c['valid_until'] else 'NO CALIBRATION RECORD'}"
                lb = QLabel(txt); lb.setStyleSheet(f"color: {C_OK if c and c['valid_until'] else C_WARN};"); lb.setWordWrap(True); l.addWidget(lb)
            self.wiz_l.addWidget(g)
        # preconditions (SRS-DVT-083)
        g = QGroupBox("PRECONDITIONS — confirm each"); l = QVBoxLayout(g)
        self.pre_boxes = []
        for p in t.get("preconditions") or []:
            cb = QCheckBox(str(p)); cb.setChecked(bool(run["preconditions_confirmed"])); cb.toggled.connect(self._pre_changed); l.addWidget(cb); self.pre_boxes.append(cb)
        if not self.pre_boxes:
            l.addWidget(QLabel("none"))
        self.wiz_l.addWidget(g)
        # steps with bound fields
        self.step_boxes = []
        fm = self.cat.field_map(run["test_id"])
        values = self.store.values(run_id)
        for i, s in enumerate(t.get("procedure_steps") or []):
            g = QGroupBox(f"STEP {i + 1}"); l = QVBoxLayout(g)
            lb = QLabel(str(s["step"])); lb.setWordWrap(True); l.addWidget(lb)
            grid = QGridLayout(); r = 0
            for name in s.get("capture") or []:
                f = fm[name]; w = self._field_widget(f, values.get(name), run["variant"].get(name))
                grid.addWidget(QLabel(f"{name}" + (f" [{f['unit']}]" if f.get("unit") else "")), r, 0)
                grid.addWidget(w, r, 1); self.field_widgets[name] = w; r += 1
            l.addLayout(grid)
            row = QHBoxLayout()
            rb = QPushButton("Redline this step"); rb.setProperty("secondary", True); rb.clicked.connect(lambda _, i=i: self.redline(i)); row.addWidget(rb)
            for rl_ in [x for x in self.store.redlines(run_id) if x["step_index"] == i]:
                row.addWidget(QLabel(f"redlined: {rl_['as_run']} ({rl_['reason']})"))
            row.addStretch(); l.addLayout(row)
            g.setEnabled(bool(run["preconditions_confirmed"]))
            self.step_boxes.append(g); self.wiz_l.addWidget(g)
        # actions
        g = QGroupBox("RESULT"); l = QVBoxLayout(g)
        self.lbl_verdict = pill("not evaluated", C_MUTE); l.addWidget(self.lbl_verdict)
        row = QHBoxLayout()
        b = QPushButton("Save values"); b.setProperty("secondary", True); b.clicked.connect(self.save_values); row.addWidget(b)
        b = QPushButton("Evaluate"); b.setProperty("secondary", True); b.clicked.connect(self.evaluate); row.addWidget(b)
        b = QPushButton("Finish run"); b.clicked.connect(self.finish_run); row.addWidget(b)
        b = QPushButton("Waive…"); b.setProperty("secondary", True); b.clicked.connect(self.waive); row.addWidget(b)
        b = QPushButton("Attach file…"); b.setProperty("secondary", True); b.clicked.connect(self.attach); row.addWidget(b)
        b = QPushButton("Reject run…"); b.setProperty("danger", True); b.clicked.connect(self.reject_run); row.addWidget(b)
        row.addStretch(); l.addLayout(row)
        if run["status"] == "DONE":
            set_pill(self.lbl_verdict, f"{run['verdict']} {run['verdict_detail'] or ''}", {"PASS": C_OK, "FAIL": C_BAD, "WAIVED": "#b39ddb"}.get(run["verdict"], C_WARN))
        self.wiz_l.addWidget(g)
        self._fill_runs(run["test_id"])

    def _field_widget(self, f, value, fixed=None):
        t = f["type"]
        if fixed is not None:                          # sweep/case variable: shown, not edited
            w = QLineEdit(str(fixed)); w.setReadOnly(True); return w
        if t == "bool":
            w = QComboBox(); w.addItems(["", "true", "false"])
            if value is not None: w.setCurrentText("true" if value else "false")
            return w
        if t == "enum":
            w = QComboBox(); w.addItems([""] + [str(x) for x in f["values"]])
            if value is not None: w.setCurrentText(str(value))
            return w
        if t in ("float", "int"):
            w = QLineEdit("" if value is None else str(value)); w.setPlaceholderText(f.get("unit", "")); return w
        w = QLineEdit("" if value is None else str(value)); return w

    def _collect(self) -> dict:
        run = self.current_run; fm = self.cat.field_map(run["test_id"]); out = {}
        for name, w in self.field_widgets.items():
            f = fm[name]
            if name in run["variant"]:
                continue
            if isinstance(w, QComboBox):
                s = w.currentText()
                if s == "": continue
                out[name] = (s == "true") if f["type"] == "bool" else s
            else:
                s = w.text().strip()
                if s == "": continue
                if f["type"] == "float":
                    try: out[name] = float(s)
                    except ValueError: raise ValueError(f"{name}: not a number")
                elif f["type"] == "int":
                    try: out[name] = int(float(s))
                    except ValueError: raise ValueError(f"{name}: not an integer")
                else:
                    out[name] = s
            rng = f.get("range")
            if rng and name in out and not (rng[0] <= out[name] <= rng[1]):
                raise ValueError(f"{name}: {out[name]} outside plausible range {rng}")
        return out

    def _pre_changed(self, *_):
        if all(cb.isChecked() for cb in self.pre_boxes):
            self.store.confirm_preconditions(self.current_run["run_id"], self.operator)
            for g in self.step_boxes: g.setEnabled(True)
            self._log("preconditions confirmed")

    def save_values(self):
        try:
            vals = self._collect()
        except ValueError as e:
            QMessageBox.warning(self, "Value", str(e)); return
        self.store.set_values(self.current_run["run_id"], vals, self.operator)
        self._log(f"saved {len(vals)} values"); self.kick_sync()

    def evaluate(self):
        self.save_values()
        v, d = self.engine.evaluate(self.current_run["run_id"])
        set_pill(self.lbl_verdict, f"{v} {d}", {"PASS": C_OK, "FAIL": C_BAD}.get(v, C_WARN))

    def finish_run(self):
        run = self.current_run
        t = self.cat.tests[run["test_id"]]
        if (t.get("safety_critical") or t.get("safety_plan")) and self.cb_safety and not self.cb_safety.isChecked():
            QMessageBox.warning(self, "Safety", "Acknowledge the safety plan first."); return
        try:
            vals = self._collect()
        except ValueError as e:
            QMessageBox.warning(self, "Value", str(e)); return
        self.store.set_values(run["run_id"], vals, self.operator)
        v, d = self.engine.finish(run["run_id"], self.operator)
        set_pill(self.lbl_verdict, f"{v} {d}", {"PASS": C_OK, "FAIL": C_BAD}.get(v, C_WARN))
        self._log(f"{run['run_id']} → {v} {d}")
        if v == "FAIL":
            QMessageBox.information(self, "NCR", "FAIL — an NCR was opened for this run.")
        self.current_run = self.store.run(run["run_id"])
        self.kick_sync(); self.refresh_all()

    def waive(self):
        dlg = WaiverDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.store.waive(self.current_run["run_id"], dlg.approver.text(), dlg.rationale.toPlainText(), self.operator)
        except ValueError as e:
            QMessageBox.warning(self, "Waiver", str(e)); return
        self._log("waived"); self.kick_sync(); self.refresh_all()

    def redline(self, step_index):
        as_run, ok = QInputDialog.getMultiLineText(self, f"Redline step {step_index + 1}", "How was the step actually performed?")
        if not ok or not as_run.strip(): return
        reason, ok = QInputDialog.getText(self, "Redline", "Reason:")
        if not ok or not reason.strip(): return
        self.store.add_redline(self.current_run["run_id"], step_index, as_run, reason, self.operator)
        self._log(f"redline step {step_index + 1}"); self.open_run(self.current_run["run_id"])

    def attach(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach file")
        if not path: return
        import hashlib, shutil
        src = Path(path); dst_dir = self.data / "export" / "attachments" / self.current_run["run_id"].replace("|", "_")
        dst_dir.mkdir(parents=True, exist_ok=True); dst = dst_dir / src.name; shutil.copy2(src, dst)
        self.store.add_attachment(self.current_run["run_id"], src.name, str(dst), src.suffix.lstrip("."), hashlib.sha256(dst.read_bytes()).hexdigest())
        self._log(f"attached {src.name}"); self.kick_sync()

    def reject_run(self):
        reason, ok = QInputDialog.getText(self, "Reject run", "Reason (e.g. ambient left the band, warm start):")
        if not ok or not reason.strip(): return
        affected = self.store.reject_run(self.current_run["run_id"], reason, self.operator)
        self._log(f"rejected {len(affected)} run(s)"); self.current_run = None; self.kick_sync(); self.refresh_all()

    # ------------------------------------------------------------------ unit actions
    def freeze_config(self):
        u = self.unit_id()
        serial, ok = QInputDialog.getText(self, "Freeze configuration", f"{u}: machine serial / configuration id (recorded, then frozen):")
        if not ok: return
        self.store.freeze_config(u, self.operator, serial.strip() or None); self.kick_sync(); self.refresh_all()

    def sign_phase(self):
        u = self.unit_id(); ph = self.engine.current_phase(u)
        if not ph or ph["id"] == 0:
            QMessageBox.information(self, "TRR", "Freeze the configuration first (Phase 0)."); return
        checklist = [f"Phase {ph['id']} — {ph['name']}: readiness reviewed", "Equipment on the bench, calibrations checked",
                     "Preceding phase closed for this unit", f"Gate: {ph.get('gate')}"]
        if QMessageBox.question(self, "Test Readiness Review", "\n".join("☐ " + c for c in checklist) + f"\n\nSign as {self.operator}?") == QMessageBox.Yes:
            self.store.sign_phase(u, ph["id"], self.operator, checklist); self.kick_sync(); self.refresh_all()

    def calibration_dialog(self):
        names = sorted({e["name"] for t in self.cat.tests.values() for e in t.get("equipment") or []})
        inst, ok = QInputDialog.getItem(self, "Calibration record", "Instrument", names, 0, False)
        if not ok: return
        cid, ok = QInputDialog.getText(self, "Calibration record", f"{inst}\nCalibration certificate id:")
        if not ok: return
        until, ok = QInputDialog.getText(self, "Calibration record", "Valid until (YYYY-MM-DD):")
        if not ok: return
        self.store.set_calibration(inst, cid, until); self.kick_sync(); self.refresh_unit()

    def close_ncr(self):
        it = self.ncr_list.currentItem()
        if not it: return
        disp, ok = QInputDialog.getMultiLineText(self, "Close NCR", "Disposition:")
        if not ok or not disp.strip(): return
        self.store.close_ncr(it.data(Qt.UserRole), disp, self.operator); self.kick_sync(); self.refresh_all()

    def do_search(self):
        self.search_out.clear()
        for r in self.store.search(self.search.text().strip())[:200]:
            self.search_out.addItem(" · ".join(str(v) for v in r.values()))

    # ------------------------------------------------------------------ sync
    def kick_sync(self):
        if getattr(self, "_sw", None) and self._sw.isRunning():
            return
        self._sw = SyncWorker(self.exporter, self.syncer); self._sw.done.connect(self._show_sync); self._sw.start()

    def sync_now(self):
        self.kick_sync()

    def _show_sync(self, st: SyncStatus):
        if st.mode == "off":
            set_pill(self.p_sync, "Drive: OFF (settings)", C_MUTE)
        elif st.ok:
            set_pill(self.p_sync, f"Drive: synced {st.last_sync or ''} → {st.target or ''}", C_OK)
        else:
            set_pill(self.p_sync, f"Drive: {st.last_error or 'pending'} ({st.pending} queued)", C_BAD if st.last_error else C_WARN)
        if st.uploaded:
            self._log(f"synced {len(st.uploaded)} files")

    def drive_settings(self):
        modes = ["api — Google Drive API (your Google account)", "folder — Google Drive for Desktop / OneDrive folder", "off"]
        cur = {"api": 0, "folder": 1, "off": 2}[self.cfg.mode]
        m, ok = QInputDialog.getItem(self, "Drive settings", "Sync mode", modes, cur, False)
        if not ok: return
        self.cfg.mode = m.split(" ")[0]
        if self.cfg.mode == "folder":
            d = QFileDialog.getExistingDirectory(self, "Choose the synced folder (e.g. G:\\My Drive\\sCure DVT)")
            if not d: return
            self.cfg.folder_path = Path(d)
        if self.cfg.mode == "api" and not self.cfg.credentials_file.exists():
            p, _ = QFileDialog.getOpenFileName(self, "Select credentials.json (Google Cloud OAuth client, Desktop app)", filter="JSON (*.json)")
            if p:
                import shutil; shutil.copy2(p, self.cfg.credentials_file)
        self.cfg.save(self.data / "sync.json")
        try:
            self.syncer = Syncer(self.cfg, self.store, self.data / "export"); self._sync_err = None
        except Exception as e:  # noqa: BLE001
            self._sync_err = str(e)
        self.refresh_all(); self.kick_sync()

    def _log(self, text):
        self.log.appendPlainText(text)


    def closeEvent(self, ev):
        try:
            self.dashboard.shutdown()
        finally:
            super().closeEvent(ev)


def main(argv=None):
    ap = argparse.ArgumentParser(description="sCure DVT desktop application")
    ap.add_argument("--catalog", default=str(HERE.parent / "catalog" / "DVT_test_catalog.yaml"))
    ap.add_argument("--data", default=os.path.expanduser("~/.scure-dvt"))
    a = ap.parse_args(argv)
    cat = Catalog.load(a.catalog)
    app = QApplication(sys.argv[:1]); app.setStyleSheet(STYLE)
    w = MainWindow(cat, Path(a.data)); w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
