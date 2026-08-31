#!/usr/bin/env python3
"""sCure DVT — Qualification & Acceptance Test Console (desktop, PySide6).

    python -m dvt_tool.app [--catalog ../catalog/DVT_test_catalog.yaml] [--data ~/.scure-dvt] [--machine http://ip:3001]

Shell: header (DUT · operator · campaign · test plan · system status · UTC clock)
+ navigation rail + pages:
    Dashboard      distribution, grouped matrix, live telemetry
    Test Plans     the catalog, browsable per test
    Test Console   per unit: what to do next, then the guided wizard
    DUT Control    connect to the machine, watch it, drive it safely
    Instruments    calibration records (SRS-DVT-085)
    Reports        open the Drive folder / export now
    Settings       Drive sync, machines, motion
Every committed result is exported and synced to Google Drive in the background.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QGridLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QMessageBox,
                               QComboBox, QScrollArea, QFrame, QInputDialog, QFileDialog, QTableWidget, QTableWidgetItem,
                               QHeaderView, QTreeWidget, QTreeWidgetItem, QStackedWidget, QSizePolicy)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dvt_tool.catalog import Catalog  # noqa: E402
from dvt_tool.store import Store  # noqa: E402
from dvt_tool.engine import Engine  # noqa: E402
from dvt_tool.export import Exporter  # noqa: E402
from dvt_tool.drive import SyncConfig, Syncer, SyncStatus  # noqa: E402
from dvt_tool.dashboard import DashboardPage  # noqa: E402
from dvt_tool.ui import theme as T  # noqa: E402
from dvt_tool.ui.widgets import Card, Pill, StatTile, PulseDot, Toast, FadeStack, label  # noqa: E402
from dvt_tool.ui.dut import DutMonitor, DutPanel, DutState, DutClient, SIM_URL  # noqa: E402
from dvt_tool.ui.wizard import RunWizard  # noqa: E402
from dvt_tool.ui.stats import StatisticsPage  # noqa: E402
from dvt_tool.ui.i18n import tr, set_language, is_rtl, LANGUAGES  # noqa: E402

DEFAULT_MACHINES = ["http://192.168.2.155:3001", "http://testingcm5.local:3001", "http://127.0.0.1:3001", SIM_URL]


class SyncWorker(QThread):
    """Export + sync in the background. Opens its OWN SQLite connection —
    sqlite3 connections must not be shared between threads (the UI thread
    keeps reading the campaign while the export runs)."""
    done = Signal(object)

    def __init__(self, app):
        super().__init__(); self.app = app

    def run(self):
        a = self.app
        try:
            st = Store(a.store.path)
            exporter = Exporter(a.cat, st, a.data / "export", a.cfg.campaign)
            syncer = Syncer(a.cfg, st, a.data / "export", backend=a.syncer.backend)
            self.done.emit(syncer.sync(exporter.export_all()))
        except Exception as e:  # noqa: BLE001
            self.done.emit(SyncStatus(a.cfg.mode, False, None, f"{type(e).__name__}: {e}"))


class MainWindow(QMainWindow):
    NAV = [("dashboard", "🏠", "Dashboard"), ("plans", "📋", "Test Plans"), ("console", "🧭", "Test Console"),
           ("dut", "🔌", "DUT Control"), ("instruments", "🔧", "Instruments"), ("stats", "📈", "Statistics"),
           ("reports", "📊", "Reports"), ("settings", "⚙", "Settings")]

    def __init__(self, catalog: Catalog, data_dir: Path, machine: str | None = None):
        super().__init__()
        self.cat, self.data = catalog, data_dir; self.data.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data / "campaign.db"); self.engine = Engine(self.cat, self.store)
        self.cfg = SyncConfig.load(self.data / "sync.json")
        for attr in ("credentials_file", "token_file"):
            if not getattr(self.cfg, attr).is_absolute(): setattr(self.cfg, attr, self.data / getattr(self.cfg, attr))
        self.exporter = Exporter(self.cat, self.store, self.data / "export", self.cfg.campaign)
        try:
            self.syncer = Syncer(self.cfg, self.store, self.data / "export"); self._sync_err = None
        except Exception as e:  # noqa: BLE001
            self.syncer = Syncer(SyncConfig(mode="off"), self.store, self.data / "export"); self._sync_err = str(e)
        self.operator = getpass.getuser()
        self.machine_url = machine or self.store.get_meta("machine_url", DEFAULT_MACHINES[0])
        self.dut_state = DutState(url=self.machine_url); self.dut_monitor = None
        self.wizard: RunWizard | None = None
        self.setWindowTitle(tr("sCure / CureBox — DVT Qualification & Acceptance Test Console"))
        self.resize(1500, 920)
        self._build(); self.toast_w = Toast(self)
        self.set_machine(self.machine_url); self.refresh_all(); self.show_page("dashboard")
        last = self.store.get_meta("last_unit")
        if last: self.select_unit(last)
        self._clock = QTimer(self); self._clock.timeout.connect(self._tick_clock); self._clock.start(1000)
        QTimer.singleShot(1500, self.kick_sync)          # first export/sync of the session in the background

    # ------------------------------------------------------------------ shell
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        # ---- header
        hdr = QFrame(); hdr.setProperty("card", "header"); hl = QHBoxLayout(hdr); hl.setContentsMargins(18, 10, 18, 10); hl.setSpacing(24)
        hl.addWidget(label(tr("sCure / CureBox — DVT Qualification & Acceptance Test Console"), size=16, bold=True))
        hl.addStretch()
        def block(eyebrow, w):
            b = QVBoxLayout(); b.setSpacing(0); b.addWidget(label(eyebrow, "eyebrow")); b.addWidget(w); hl.addLayout(b)
        self.cb_machine = QComboBox(); self.cb_machine.setEditable(True); self.cb_machine.setMinimumWidth(230)
        for u in self.known_machines(): self.cb_machine.addItem(u)
        self.cb_machine.setCurrentText(self.machine_url); self.cb_machine.lineEdit().returnPressed.connect(lambda: self.set_machine(self.cb_machine.currentText().strip()))
        self.cb_machine.activated.connect(lambda _: self.set_machine(self.cb_machine.currentText().strip()))
        block(tr("DUT"), self.cb_machine)
        self.cb_unit = QComboBox(); self.cb_unit.setMinimumWidth(110)
        for u in self.cat.units: self.cb_unit.addItem(f"{u['id']}" + (f"  ·  {u.get('role')}" if u.get("role") else ""), u["id"])
        self.cb_unit.currentIndexChanged.connect(self._unit_from_header)
        block(tr("UNIT UNDER TEST"), self.cb_unit)
        self.ed_operator = QLineEdit(self.operator); self.ed_operator.setFixedWidth(130); self.ed_operator.textChanged.connect(lambda s: setattr(self, "operator", s.strip()))
        block(tr("OPERATOR"), self.ed_operator)
        block(tr("CAMPAIGN"), label(self.cfg.campaign, bold=True)); block(tr("TEST PLAN"), label(f"SRS-DVT-SW Rev B · cat v{self.cat.version}", bold=True))
        sysbox = QHBoxLayout(); self.dot_sys = PulseDot(T.MUTED); sysbox.addWidget(self.dot_sys); self.lbl_sys = label(tr("OFFLINE"), bold=True, size=15, color=T.MUTED); sysbox.addWidget(self.lbl_sys)
        w = QWidget(); w.setLayout(sysbox); block(tr("SYSTEM STATUS"), w)
        self.lbl_clock = label("", "mono", bold=True); block(tr("DATE / TIME (UTC)"), self.lbl_clock)
        self.p_sync = Pill("Drive: —", T.MUTED); hl.addWidget(self.p_sync)
        v.addWidget(hdr)
        self.sim_banner = QLabel(tr("◉  SIMULATION MODE — you are connected to the built-in simulated machine. Nothing here touches real hardware. Inject faults from DUT Control."))
        self.sim_banner.setStyleSheet(f"background: #efe9fb; color: #3d2a7a; border-bottom: 1px solid #cdbdf0; padding: 8px 18px; font-weight: 600;"); self.sim_banner.hide()
        v.addWidget(self.sim_banner)
        # ---- body
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0); v.addLayout(body, 1)
        side = QFrame(); side.setProperty("card", "sidebar"); side.setFixedWidth(230); sl = QVBoxLayout(side); sl.setContentsMargins(10, 14, 10, 14); sl.setSpacing(4)
        self.nav_buttons = {}
        for key, icon, text in self.NAV:
            b = QPushButton(f"{icon}   {tr(text)}"); b.setProperty("kind", "nav"); b.setCheckable(True); b.clicked.connect(lambda _, k=key: self.show_page(k)); sl.addWidget(b); self.nav_buttons[key] = b
        sl.addSpacing(10); sl.addWidget(label(tr("TEST SUBSYSTEMS"), "eyebrow-rail"))
        self.nav_sub = {}
        for name in ("Thermal", "Electrical", "Safety", "Environmental"):
            b = QPushButton(f"{T.SUBSYSTEM_ICON[name]}   {name}"); b.setProperty("kind", "nav"); b.clicked.connect(lambda _, n=name: (self.show_page("dashboard"), self.dashboard.set_filter(n)))
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(b, 1)
            cnt = QLabel("0"); cnt.setStyleSheet(f"background: {T.RAIL_2}; color: {T.SUBSYSTEM[name]}; border-radius: 10px; padding: 2px 9px; font-weight: 700; font-size: 11px;")
            row.addWidget(cnt); w = QWidget(); w.setLayout(row); w.setStyleSheet("background: transparent;"); sl.addWidget(w); self.nav_sub[name] = cnt
        sl.addStretch()
        self.sim_toggle = QPushButton("◉   " + tr("Simulation mode: OFF")); self.sim_toggle.setProperty("kind", "nav"); self.sim_toggle.setCheckable(True)
        self.sim_toggle.clicked.connect(self.toggle_sim); sl.addWidget(self.sim_toggle)
        self.health = QFrame(); self.health.setStyleSheet(f"QFrame {{ background: {T.RAIL_2}; border-radius: 10px; }}"); hb = QVBoxLayout(self.health); hb.setContentsMargins(12, 10, 12, 10)
        self.health_dot = PulseDot(T.OK); hr = QHBoxLayout(); hr.addWidget(self.health_dot); hr.addWidget(label(tr("System Health"), bold=True, color="#ffffff")); hr.addStretch(); hb.addLayout(hr)
        self.health_text = label(tr("All systems nominal"), "rail", wrap=True); hb.addWidget(self.health_text); sl.addWidget(self.health)
        body.addWidget(side)
        self.pages = FadeStack(); body.addWidget(self.pages, 1)
        self.page_index = {}
        self.dashboard = DashboardPage(self.engine, self.machine_url); self.dashboard.openTest.connect(self.open_test)
        self.stats = StatisticsPage(self.engine)
        for key, page in (("dashboard", self._wrap(self.dashboard)), ("plans", self._plans_page()), ("console", self._console_page()),
                          ("dut", self._wrap(DutPanel(self))), ("instruments", self._instruments_page()), ("stats", self._wrap(self.stats)),
                          ("reports", self._reports_page()), ("settings", self._settings_page())):
            self.page_index[key] = self.pages.count(); self.pages.addWidget(page)
        self.dut_panel = self.pages.widget(self.page_index["dut"]).findChild(DutPanel)

    def _wrap(self, w: QWidget) -> QWidget:
        outer = QWidget(); l = QVBoxLayout(outer); l.setContentsMargins(18, 16, 18, 16); l.addWidget(w); return outer

    def show_page(self, key):
        for k, b in self.nav_buttons.items(): b.setChecked(k == key)
        self.pages.set_page(self.page_index[key])
        if key == "dashboard": self.dashboard.refresh()
        if key == "plans": self._fill_plans()
        if key == "console": self.refresh_console()
        if key == "instruments": self._fill_instruments()
        if key == "stats": self.stats.refresh()

    def toast(self, text, color=None): self.toast_w.show_message(text, color)

    def _tick_clock(self): self.lbl_clock.setText(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    def current_run_id(self): return self.wizard.run["run_id"] if self.wizard else None

    # ------------------------------------------------------------------ DUT
    def known_machines(self) -> list[str]:
        saved = (self.store.get_meta("machines", "") or "").split("|")
        return [m for m in dict.fromkeys([*saved, *DEFAULT_MACHINES]) if m]

    def is_sim(self) -> bool:
        return self.machine_url.startswith("sim://")

    def set_machine(self, url: str):
        if not url: return
        if url.lower() in ("sim", "simulator", "simulation"): url = SIM_URL
        if not url.startswith(("http://", "https://", "sim://")): url = f"http://{url}"
        if url.startswith("http") and ":" not in url.split("//", 1)[1]: url += ":3001"
        self.machine_url = url; self.store.set_meta("machine_url", url)
        self.store.set_meta("machines", "|".join(dict.fromkeys([url, *self.known_machines()])))
        if self.cb_machine.findText(url) < 0: self.cb_machine.insertItem(0, url)
        self.cb_machine.setCurrentText(url)
        if self.dut_monitor: self.dut_monitor.stop(); self.dut_monitor.wait(3000)
        self.dut_monitor = DutMonitor(url); self.dut_monitor.state.connect(self._on_dut); self.dut_monitor.start()
        self.store.log("DUT selected", self.operator, None, {"url": url})

    def toggle_sim(self):
        if self.machine_url.startswith("sim://"):
            prev = self.store.get_meta("machine_url_real", DEFAULT_MACHINES[0]); self.set_machine(prev)
        else:
            self.store.set_meta("machine_url_real", self.machine_url); self.set_machine(SIM_URL)

    def _on_dut(self, st: DutState):
        self.dut_state = st
        sim = bool(st.online and st.flags.get("simulated"))
        self.sim_banner.setVisible(sim); self.sim_toggle.setChecked(sim)
        if hasattr(self, "rb_mode_sim") and self.rb_mode_sim.isChecked() != sim:
            self.rb_mode_sim.blockSignals(True); self.rb_mode_normal.blockSignals(True)
            (self.rb_mode_sim if sim else self.rb_mode_normal).setChecked(True)
            self.rb_mode_sim.blockSignals(False); self.rb_mode_normal.blockSignals(False); self.sim_toggle.setText("◉   " + tr("Simulation mode: ON" if sim else "Simulation mode: OFF"))
        col = T.MODE.get(st.mode, T.MUTED)
        txt = tr("RUNNING") if st.mode in ("CURING", "HEATING", "COOLING") else tr(st.mode)
        self.dot_sys.set_color(col if not sim or st.mode != "IDLE" else T.PURPLE); self.lbl_sys.setText(("SIM · " if sim else "") + txt); self.lbl_sys.setStyleSheet(f"font-weight: 700; font-size: 15px; color: {col};")
        if self.dut_panel: self.dut_panel.on_state(st)
        self.dashboard.on_dut(st)

    # ------------------------------------------------------------------ pages: plans
    def _plans_page(self):
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(18, 16, 18, 16); l.setSpacing(14)
        self.plan_tree = QTreeWidget(); self.plan_tree.setHeaderLabels([tr("Test"), tr("Test name"), tr("Method"), tr("Appl."), tr("Runs")]); self.plan_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.plan_tree.currentItemChanged.connect(lambda it, _: it and it.data(0, Qt.UserRole) and self._show_plan(it.data(0, Qt.UserRole)))
        l.addWidget(self.plan_tree, 2)
        self.plan_detail = QPlainTextEdit(); self.plan_detail.setReadOnly(True); l.addWidget(self.plan_detail, 3)
        return w

    def _fill_plans(self):
        self.plan_tree.clear()
        for p in sorted(self.cat.phases, key=lambda p: p["id"]):
            top = QTreeWidgetItem([f"Phase {p['id']} — {p['name']}", p.get("gate") or "", "", "", ""]); top.setExpanded(True); self.plan_tree.addTopLevelItem(top)
            for tid in p.get("tests", []):
                t = self.cat.tests[tid]; st = self.engine.test_status(tid)
                it = QTreeWidgetItem([tid, t["title"], t["method"], st["applicability"], f"{st['runsDone']}/{st['runsTotal']}"]); it.setData(0, Qt.UserRole, tid); top.addChild(it)

    def _show_plan(self, tid):
        import yaml
        t = self.cat.tests[tid]
        self.plan_detail.setPlainText(yaml.safe_dump(t, sort_keys=False, allow_unicode=True, width=100))

    # ------------------------------------------------------------------ pages: console
    def _console_page(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(18, 16, 18, 16); l.setSpacing(14)
        self.console_stack = FadeStack(); l.addWidget(self.console_stack, 1)
        home = QWidget(); hl = QHBoxLayout(home); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(14)
        left = QVBoxLayout(); hl.addLayout(left, 1)
        c = Card(tr("Units under test")); self.units = QListWidget(); self.units.currentItemChanged.connect(lambda *_: self.refresh_console()); c.body.addWidget(self.units)
        row = QHBoxLayout()
        b = QPushButton(tr("Freeze config")); b.setProperty("kind", "ghost"); b.clicked.connect(self.freeze_config); row.addWidget(b)
        b = QPushButton(tr("Sign phase TRR")); b.setProperty("kind", "ghost"); b.clicked.connect(self.sign_phase); row.addWidget(b)
        c.body.addLayout(row); left.addWidget(c)
        c = Card(tr("Open NCRs")); self.ncr_list = QListWidget(); c.body.addWidget(self.ncr_list)
        b = QPushButton(tr("Close selected NCR…")); b.setProperty("kind", "ghost"); b.clicked.connect(self.close_ncr); c.body.addWidget(b); left.addWidget(c)
        c = Card(tr("Search")); self.search = QLineEdit(); self.search.setPlaceholderText(tr("run, value, error code, NCR text…")); self.search.returnPressed.connect(self.do_search); c.body.addWidget(self.search)
        self.search_out = QListWidget(); c.body.addWidget(self.search_out); left.addWidget(c, 1)
        centre = QVBoxLayout(); hl.addLayout(centre, 2)
        self.next_card = Card(tr("Next action"), kind="raised")
        self.lbl_next = label("", "instruction", wrap=True); self.next_card.body.addWidget(self.lbl_next)
        self.lbl_block = label("", "banner-bad", wrap=True); self.lbl_block.hide(); self.next_card.body.addWidget(self.lbl_block)
        fix = QHBoxLayout(); self.fix_buttons = {}
        for key, text, slot in (("CONFIG", tr("Freeze configuration now"), self.freeze_config), ("TRR", tr("Sign phase readiness now"), self.sign_phase),
                                ("CAL", tr("Record calibrations…"), lambda: self.show_page("instruments")), ("EARTH", tr("Go to ELE-001 (earth first)"), lambda: self.open_test("DVT-ELE-001"))):
            b = QPushButton(text); b.setProperty("kind", "ghost"); b.clicked.connect(slot); b.hide(); fix.addWidget(b); self.fix_buttons[key] = b
        fix.addStretch(); self.next_card.body.addLayout(fix)
        row = QHBoxLayout()
        self.btn_start = QPushButton(tr("Start guided run →")); self.btn_start.setProperty("kind", "big"); self.btn_start.clicked.connect(self.start_run); row.addWidget(self.btn_start)
        self.btn_override = QPushButton(tr("Start anyway (supervisor)")); self.btn_override.setProperty("kind", "danger"); self.btn_override.clicked.connect(lambda: self.start_run(override=True)); row.addWidget(self.btn_override)
        row.addStretch(); self.next_card.body.addLayout(row); centre.addWidget(self.next_card)
        c = Card(tr("Runs of this test"), hint=tr("double-click a NOT_STARTED / IN_PROGRESS run to open it"))
        self.runs_tbl = QTableWidget(0, 6); self.runs_tbl.setHorizontalHeaderLabels([tr("Unit"), tr("Variant"), tr("Rep"), tr("Status"), tr("Verdict"), tr("Operator")])
        self.runs_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.runs_tbl.verticalHeader().hide(); self.runs_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.runs_tbl.cellDoubleClicked.connect(self._open_run_row); c.body.addWidget(self.runs_tbl); centre.addWidget(c, 1)
        self.console_stack.addWidget(home)
        return w

    def unit_id(self):
        it = self.units.currentItem(); return it.data(Qt.UserRole) if it else None

    def _unit_from_header(self, _idx):
        """Header tr('UNIT UNDER TEST') drives the console unit list (and vice versa)."""
        u = self.cb_unit.currentData()
        for i in range(self.units.count()):
            if self.units.item(i).data(Qt.UserRole) == u and self.units.currentRow() != i:
                self.units.setCurrentRow(i); break
        self.store.set_meta("last_unit", u or "")

    def select_unit(self, u: str):
        i = self.cb_unit.findData(u)
        if i >= 0 and self.cb_unit.currentIndex() != i: self.cb_unit.setCurrentIndex(i)

    def refresh_console(self):
        if self.wizard: return
        u = self.unit_id()
        if not u: return
        self.select_unit(u)
        na = self.engine.next_action(u)
        self.lbl_next.setText(na.message)
        self.lbl_block.setVisible(bool(na.blockers)); self.lbl_block.setText(tr("Blocked:") + "\n• " + "\n• ".join(b.text for b in na.blockers))
        codes = {b.code for b in na.blockers}
        for k, b in self.fix_buttons.items(): b.setVisible(k in codes)
        startable = na.run is not None and na.run["status"] in ("NOT_STARTED", "IN_PROGRESS")
        self.btn_start.setEnabled(startable and not na.blockers); self.btn_override.setEnabled(startable and bool(na.blockers))
        self.btn_start.setText(tr("Resume guided run →") if na.run and na.run["status"] == "IN_PROGRESS" else tr("Start guided run →"))
        self._fill_runs(na.run["test_id"] if na.run else None)

    def _fill_runs(self, test_id):
        self.runs_tbl.setRowCount(0); self._runs_cache = []
        if not test_id: return
        for r in self.store.runs(test_id):
            i = self.runs_tbl.rowCount(); self.runs_tbl.insertRow(i); self._runs_cache.append(r)
            cells = [r["unit_id"], ", ".join(f"{k}={v}" for k, v in r["variant"].items()) or "—", str(r["repetition"]), r["status"], r["verdict"] or "", r["operator"] or ""]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c == 4 and txt: it.setForeground(Qt.GlobalColor.white); it.setBackground(Qt.GlobalColor.transparent); it.setText(txt)
                self.runs_tbl.setItem(i, c, it)

    def _open_run_row(self, row, _col):
        r = self._runs_cache[row]
        if r["status"] in ("NOT_STARTED", "IN_PROGRESS"):
            self.units.setCurrentRow(self.cat.unit_ids().index(r["unit_id"]))
            self._launch_wizard(r, override_check=False)

    def open_test(self, test_id):
        self.show_page("console"); self._fill_runs(test_id)
        pending = [r for r in self.store.runs(test_id) if r["status"] in ("NOT_STARTED", "IN_PROGRESS")]
        if pending: self.units.setCurrentRow(self.cat.unit_ids().index(pending[0]["unit_id"]))

    def start_run(self, override=False):
        na = self.engine.next_action(self.unit_id() or "")
        if not na.run: return
        if override:
            reason, ok = QInputDialog.getText(self, "Supervisor override", "Reason for starting despite blockers (recorded):")
            if not ok or not reason.strip(): return
            self.store.log("Blocker override", self.operator, na.run["run_id"], {"blockers": [b.text for b in na.blockers], "reason": reason})
        self._launch_wizard(na.run, override_check=not override)

    def _launch_wizard(self, run, override_check=True):
        if not self.operator:
            QMessageBox.warning(self, "Operator", tr("Enter the operator name in the header first.")); return
        if run["status"] == "NOT_STARTED":
            self.store.start_run(run["run_id"], self.operator)
        self.wizard = RunWizard(self, run["run_id"])
        self.wizard.finished.connect(self._wizard_finished); self.wizard.left.connect(self._wizard_left)
        self.console_stack.addWidget(self.wizard); self.console_stack.set_page(1)

    def _close_wizard(self):
        w = self.wizard; self.wizard = None
        self.console_stack.set_page(0, forward=False); self.console_stack.removeWidget(w); w.deleteLater()
        self.refresh_all()

    def _wizard_finished(self, run_id, verdict):
        self.refresh_all()
        if verdict == "REJECTED": self._close_wizard()

    def _wizard_left(self): self._close_wizard()

    # ------------------------------------------------------------------ pages: instruments
    def _instruments_page(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(18, 16, 18, 16); l.setSpacing(14)
        c = Card(tr("Instruments & calibration records"), hint="SRS-DVT-085 — a run is blocked while any of its instruments has no valid record")
        self.inst_tbl = QTableWidget(0, 4); self.inst_tbl.setHorizontalHeaderLabels([tr("Instrument"), tr("Calibration id"), tr("Valid until"), tr("Used by")])
        self.inst_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.inst_tbl.verticalHeader().hide(); c.body.addWidget(self.inst_tbl)
        b = QPushButton(tr("Record calibration for selected…")); b.clicked.connect(self._record_calibration); c.body.addWidget(b, 0, Qt.AlignLeft)
        l.addWidget(c)
        return w

    def _fill_instruments(self):
        names = {}
        for tid, t in self.cat.tests.items():
            for e in t.get("equipment") or []: names.setdefault(e["name"], []).append(tid)
        self.inst_tbl.setRowCount(0)
        for name, used in sorted(names.items()):
            cal = self.store.calibration(name); i = self.inst_tbl.rowCount(); self.inst_tbl.insertRow(i)
            for c, txt in enumerate([name, cal["calibration_id"] if cal else "—", cal["valid_until"] if cal else "MISSING", ", ".join(used)]):
                it = QTableWidgetItem(txt)
                if c == 2: it.setForeground(Qt.GlobalColor.green if cal and cal["valid_until"] >= datetime.now().date().isoformat() else Qt.GlobalColor.red)
                self.inst_tbl.setItem(i, c, it)

    def _record_calibration(self):
        r = self.inst_tbl.currentRow()
        if r < 0: return
        name = self.inst_tbl.item(r, 0).text()
        cid, ok = QInputDialog.getText(self, "Calibration record", f"{name}\nCertificate id:")
        if not ok: return
        until, ok = QInputDialog.getText(self, "Calibration record", "Valid until (YYYY-MM-DD):")
        if not ok: return
        self.store.set_calibration(name, cid, until); self._fill_instruments(); self.kick_sync()

    # ------------------------------------------------------------------ pages: reports / settings
    def _reports_page(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(18, 16, 18, 16); l.setSpacing(14)
        c = Card(tr("Reports & exports")); l.addWidget(c)
        self.lbl_reports = label("", "muted", wrap=True); c.body.addWidget(self.lbl_reports)
        row = QHBoxLayout()
        b = QPushButton(tr("Export + sync now")); b.clicked.connect(self.kick_sync); row.addWidget(b)
        b = QPushButton(tr("Open Drive folder")); b.setProperty("kind", "ghost"); b.clicked.connect(self.open_reports); row.addWidget(b)
        b = QPushButton(tr("Open local export folder")); b.setProperty("kind", "ghost"); b.clicked.connect(lambda: os.startfile(str(self.data / "export"))); row.addWidget(b)
        row.addStretch(); c.body.addLayout(row)
        self.events = QPlainTextEdit(); self.events.setReadOnly(True); c2 = Card(tr("Campaign events (latest)")); c2.body.addWidget(self.events); l.addWidget(c2, 1)
        return w

    def open_reports(self):
        target = self.cfg.folder_path if (self.cfg.mode == "folder" and self.cfg.folder_path) else (self.data / "export")
        try: os.startfile(str(target))
        except Exception as e: self.toast(f"cannot open {target}: {e}", T.BAD)  # noqa: BLE001

    def _settings_page(self):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(18, 16, 18, 16); l.setSpacing(14); l.setAlignment(Qt.AlignTop)
        c = Card(tr("Google Drive sync")); g = QGridLayout(); c.body.addLayout(g)
        self.cb_mode = QComboBox(); self.cb_mode.addItems(["folder", "api", "off"]); self.cb_mode.setCurrentText(self.cfg.mode)
        self.ed_folder = QLineEdit(str(self.cfg.folder_path or "")); b = QPushButton(tr("Browse…")); b.setProperty("kind", "ghost"); b.clicked.connect(self._browse_folder)
        g.addWidget(label("Mode"), 0, 0); g.addWidget(self.cb_mode, 0, 1); g.addWidget(label(tr("Synced folder (mode=folder)")), 1, 0); g.addWidget(self.ed_folder, 1, 1); g.addWidget(b, 1, 2)
        g.addWidget(label(tr("OAuth client (mode=api)")), 2, 0); self.lbl_cred = label(str(self.cfg.credentials_file), "mono"); g.addWidget(self.lbl_cred, 2, 1)
        b2 = QPushButton(tr("Select credentials.json…")); b2.setProperty("kind", "ghost"); b2.clicked.connect(self._pick_credentials); g.addWidget(b2, 2, 2)
        b3 = QPushButton(tr("Apply")); b3.clicked.connect(self._apply_sync); g.addWidget(b3, 3, 1, alignment=Qt.AlignLeft); l.addWidget(c)
        c = Card(tr("Work mode")); mrow = QHBoxLayout(); c.body.addLayout(mrow)
        from PySide6.QtWidgets import QRadioButton
        self.rb_mode_normal = QRadioButton(tr("Normal — real machine")); self.rb_mode_sim = QRadioButton(tr("Simulation — built-in simulated machine"))
        (self.rb_mode_sim if self.machine_url.startswith("sim://") else self.rb_mode_normal).setChecked(True)
        self.rb_mode_normal.toggled.connect(lambda on: on and self.machine_url.startswith("sim://") and self.toggle_sim())
        self.rb_mode_sim.toggled.connect(lambda on: on and not self.machine_url.startswith("sim://") and self.toggle_sim())
        mrow.addWidget(self.rb_mode_normal); mrow.addWidget(self.rb_mode_sim); mrow.addStretch(); l.addWidget(c)
        c = Card(tr("Language")); lrow = QHBoxLayout(); c.body.addLayout(lrow)
        self.cb_lang = QComboBox()
        for code, name in LANGUAGES.items(): self.cb_lang.addItem(name, code)
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(self.store.get_meta("language", "en"))))
        lrow.addWidget(self.cb_lang); lrow.addWidget(label(tr("Language / mode changes apply after the console restarts."), "muted"))
        b = QPushButton(tr("Restart console now")); b.setProperty("kind", "ghost"); b.clicked.connect(self.restart); lrow.addWidget(b); lrow.addStretch(); l.addWidget(c)
        c = Card(tr("Motion")); self.cb_motion = QComboBox(); self.cb_motion.addItems([tr("animations on"), tr("reduced motion")]); self.cb_motion.currentIndexChanged.connect(lambda i: setattr(FadeStack, "duration", 0 if i else 260))
        c.body.addWidget(self.cb_motion); l.addWidget(c)
        c = Card(tr("About")); c.body.addWidget(label(f"sCure DVT · SRS-DVT-SW Rev B · catalog v{self.cat.version} · data {self.data}", "muted", wrap=True)); l.addWidget(c)
        return w

    RESTART_CODE = 42

    def restart(self):
        self.store.set_meta("language", self.cb_lang.currentData())
        self.store.set_meta("show_start_dialog", "0")
        QApplication.instance().exit(self.RESTART_CODE)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Synced folder (e.g. G:\\My Drive\\sCure DVT)")
        if d: self.ed_folder.setText(d)

    def _pick_credentials(self):
        p, _ = QFileDialog.getOpenFileName(self, "credentials.json", filter="JSON (*.json)")
        if p:
            import shutil; shutil.copy2(p, self.cfg.credentials_file); self.lbl_cred.setText(str(self.cfg.credentials_file))

    def _apply_sync(self):
        self.cfg.mode = self.cb_mode.currentText(); self.cfg.folder_path = Path(self.ed_folder.text()) if self.ed_folder.text().strip() else None
        self.cfg.save(self.data / "sync.json")
        try:
            self.syncer = Syncer(self.cfg, self.store, self.data / "export"); self._sync_err = None; self.toast("Sync settings applied", T.OK)
        except Exception as e:  # noqa: BLE001
            self._sync_err = str(e); self.toast(str(e), T.BAD)
        self.kick_sync()

    # ------------------------------------------------------------------ unit actions
    def freeze_config(self):
        u = self.unit_id()
        if not u: return
        serial, ok = QInputDialog.getText(self, "Freeze configuration", f"{u}: machine serial / configuration id (recorded, then frozen):")
        if not ok: return
        self.store.freeze_config(u, self.operator, serial.strip() or None); self.kick_sync(); self.refresh_all()

    def sign_phase(self):
        u = self.unit_id(); ph = self.engine.current_phase(u) if u else None
        if not ph or ph["id"] == 0:
            QMessageBox.information(self, "TRR", "Freeze the configuration first (Phase 0)."); return
        checklist = [f"Phase {ph['id']} — {ph['name']}: readiness reviewed", "Equipment on the bench, calibrations checked", "Preceding phase closed for this unit", f"Gate: {ph.get('gate')}"]
        if QMessageBox.question(self, "Test Readiness Review", "\n".join("☐ " + c for c in checklist) + f"\n\nSign as {self.operator}?") == QMessageBox.Yes:
            self.store.sign_phase(u, ph["id"], self.operator, checklist); self.kick_sync(); self.refresh_all()

    def close_ncr(self):
        it = self.ncr_list.currentItem()
        if not it: return
        disp, ok = QInputDialog.getMultiLineText(self, "Close NCR", "Disposition:")
        if not ok or not disp.strip(): return
        self.store.close_ncr(it.data(Qt.UserRole), disp, self.operator); self.kick_sync(); self.refresh_all()

    def do_search(self):
        self.search_out.clear()
        for r in self.store.search(self.search.text().strip())[:200]: self.search_out.addItem(" · ".join(str(v) for v in r.values()))

    # ------------------------------------------------------------------ refresh / sync
    def refresh_all(self):
        cur = self.unit_id(); self.units.blockSignals(True); self.units.clear()
        prog = self.engine.progress()
        for u in self.cat.unit_ids():
            d = prog["perUnit"][u]; it = QListWidgetItem(f"{u}    phase {d['phase']}    {d['done']}/{d['total']} runs"); it.setData(Qt.UserRole, u); self.units.addItem(it)
            if u == cur: self.units.setCurrentItem(it)
        if self.units.currentItem() is None and self.units.count(): self.units.setCurrentRow(0)
        self.units.blockSignals(False)
        self.ncr_list.clear()
        for n in self.store.ncrs(open_only=True):
            it = QListWidgetItem(f"{n['ncr_id']}  {n['run_id']}  {n['description'][:50]}"); it.setData(Qt.UserRole, n["ncr_id"]); self.ncr_list.addItem(it)
        summ = self.engine.subsystem_summary()
        for name, cnt in self.nav_sub.items(): cnt.setText(str(summ.get(name, {}).get("tests", 0)))
        failed = sum(s["failed"] for s in summ.values()); blocked = sum(s["blocked"] for s in summ.values())
        if failed: self.health_dot.set_color(T.BAD); self.health_text.setText(f"{failed} test(s) FAILED · {prog['openNcrs']} NCR open")
        elif blocked: self.health_dot.set_color(T.WARN); self.health_text.setText(f"{blocked} test(s) BLOCKED — missing data or threshold")
        else: self.health_dot.set_color(T.OK); self.health_text.setText(f"All systems nominal\n{prog['done']}/{prog['total']} runs done")
        self._show_sync(self.syncer.status if not self._sync_err else SyncStatus(self.cfg.mode, False, None, self._sync_err))
        self.lbl_reports.setText(f"Mode {self.cfg.mode} → {self.syncer.backend.describe() if self.syncer.backend else 'off'} · pending {len(self.store.pending_sync())}")
        self.events.setPlainText("\n".join(f"{e['at']}  {e['actor'] or '-':10}  {e['event']:32}  {e['run_id'] or ''}" for e in self.store.events(200)))
        if self.pages.currentIndex() == self.page_index.get("dashboard", -1): self.dashboard.refresh()
        self.refresh_console()

    def kick_sync(self):
        if getattr(self, "_sw", None) and self._sw.isRunning(): return
        self._sw = SyncWorker(self); self._sw.done.connect(self._show_sync); self._sw.start()

    def _show_sync(self, st: SyncStatus):
        if st.mode == "off": self.p_sync.set("Drive: OFF", T.MUTED)
        elif st.ok: self.p_sync.set(f"Drive ✓ {(st.last_sync or '')[11:19]}", T.OK)
        else: self.p_sync.set(f"Drive: {st.pending} queued — {st.last_error or 'pending'}", T.BAD if st.last_error else T.WARN)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)

    def closeEvent(self, ev):
        try:
            if self.dut_monitor: self.dut_monitor.stop(); self.dut_monitor.wait(2000)
            sw = getattr(self, "_sw", None)
            if sw and sw.isRunning(): sw.wait(8000)          # let the last export/sync finish
            self.dashboard.shutdown()
        finally:
            super().closeEvent(ev)


def main(argv=None):
    ap = argparse.ArgumentParser(description="sCure DVT desktop application")
    ap.add_argument("--catalog", default=str(HERE.parent / "catalog" / "DVT_test_catalog.yaml"))
    ap.add_argument("--data", default=os.path.expanduser("~/.scure-dvt"))
    ap.add_argument("--machine", help="DUT address, e.g. http://192.168.2.155:3001, or 'sim'")
    ap.add_argument("--lang", choices=list(LANGUAGES), help="UI language (en / he)")
    ap.add_argument("--no-dialog", action="store_true", help="skip the start dialog")
    a = ap.parse_args(argv)
    cat = Catalog.load(a.catalog)
    data = Path(a.data); data.mkdir(parents=True, exist_ok=True)
    while True:
        meta = Store(data / "campaign.db")
        lang = a.lang or meta.get_meta("language", "en"); set_language(lang)
        app = QApplication(sys.argv[:1]); app.setStyleSheet(T.QSS); app.setLayoutDirection(Qt.RightToLeft if is_rtl() else Qt.LeftToRight)
        machine = a.machine
        if machine is None and not a.no_dialog and meta.get_meta("show_start_dialog", "1") != "0":
            from dvt_tool.ui.start import StartDialog
            saved = (meta.get_meta("machines", "") or "").split("|")
            machines = [m for m in dict.fromkeys([*saved, *DEFAULT_MACHINES]) if m]
            cur = meta.get_meta("machine_url", DEFAULT_MACHINES[0])
            dlg = StartDialog(machines, cat.units, getpass.getuser(), lang, "sim" if cur.startswith("sim://") else "normal", cur, meta.get_meta("last_unit"))
            if dlg.exec() != StartDialog.Accepted or not dlg.result_:
                return 0
            r = dlg.result_
            if r["lang"] != lang:
                meta.set_meta("language", r["lang"]); set_language(r["lang"]); app.setLayoutDirection(Qt.RightToLeft if is_rtl() else Qt.LeftToRight)
            machine = SIM_URL if r["mode"] == "sim" else (r["machine"] or DEFAULT_MACHINES[0])
            meta.set_meta("last_unit", r["unit"] or ""); meta.set_meta("operator", r["operator"] or "")
        meta.set_meta("show_start_dialog", "1"); meta.db.close()
        w = MainWindow(cat, data, machine)
        op = w.store.get_meta("operator")
        if op: w.ed_operator.setText(op)
        w.show()
        rc = app.exec()
        del w; del app
        if rc != MainWindow.RESTART_CODE:
            return rc
        a.machine = None; a.lang = None          # restart: re-read the saved language, skip the dialog once


if __name__ == "__main__":
    code = main()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(code)              # skip interpreter finalisation: Qt/PySide teardown order is not worth a crash dialog
