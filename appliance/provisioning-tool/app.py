#!/usr/bin/env python3
"""Stratasys Factory Provisioning Tool — desktop application (Qt / PySide6).

    python app.py --station ST-01 --server http://mfg:8440 --trust trust/ [--fake] [--signed-eeprom DIR]

A native window for the manufacturing station: step list with progress,
approved-image panel (Latest Production / Local / Signature / Status,
OFFLINE MODE banner), module detection, unit panel (serial, previous
serial, device ID, versions, secure boot, encryption, license, final test),
Start Provisioning, the authorised Generate New Serial Number action, the
Provisioning Successful summary and the event log.

The window only observes: a ProvisioningRun executes in a QThread and
reports through Qt signals; all rules live in provision.py / common/.
Package as a single .exe with:  pyinstaller stratasys-provisioning.spec
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit,
                               QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QListWidget, QListWidgetItem,
                               QProgressBar, QPlainTextEdit, QMessageBox, QFrame, QSizePolicy)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stratasys_appliance import crypto, serials  # noqa: E402
import provision  # noqa: E402
from image_catalog import ImageCatalog, CatalogError  # noqa: E402
from rpiboot import Rpiboot, FakeRpiboot, detect_usb_module  # noqa: E402

STEP_LABELS = {
    "FETCH_APPROVED_IMAGE": "Fetch approved image", "DETECT_HARDWARE": "Detect module (rpiboot)",
    "VERIFY_COMPAT": "Verify hardware compatibility", "FLASH_IMAGE": "Flash image",
    "CONFIGURE_BOOT": "Configure secure boot (OTP)", "CREATE_IDENTITY": "Create device identity",
    "ALLOCATE_SERIAL": "Assign serial number", "REQUEST_LICENSE": "Request license",
    "BIND_LICENSE": "Bind license to device", "ENCRYPT_DATA": "Encrypt data partition",
    "APPLY_POLICY": "Apply kiosk / USB / user policy", "VERIFY_MACHINE": "Machine self-test",
    "VERIFY_SOFTWARE": "Software verification", "RECORD": "Manufacturing record",
}
C_OK, C_WARN, C_BAD, C_MUTE, C_ACC = "#5cbf86", "#d9a93a", "#e06a60", "#93a4b3", "#3fb8ba"

STYLE = """
QMainWindow, QWidget { background: #0f1418; color: #e6ebf0; font-family: 'Segoe UI'; font-size: 14px; }
QGroupBox { border: 1px solid #2a353f; border-radius: 8px; margin-top: 14px; padding: 10px 12px 8px; background: #171f26; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #93a4b3; font-size: 11px; letter-spacing: 1px; }
QLineEdit { background: #0f1418; border: 1px solid #2a353f; border-radius: 6px; padding: 8px 10px; }
QPushButton { background: #3fb8ba; color: #04191a; border: 0; border-radius: 7px; padding: 10px 16px; font-weight: 700; }
QPushButton:disabled { background: #26313a; color: #6c7a86; }
QPushButton[secondary="true"] { background: #26313a; color: #e6ebf0; }
QListWidget { background: #0f1418; border: 1px solid #2a353f; border-radius: 6px; font-family: Consolas; font-size: 13px; }
QPlainTextEdit { background: #0f1418; border: 1px solid #2a353f; border-radius: 6px; font-family: Consolas; font-size: 12px; }
QProgressBar { background: #26313a; border: 0; border-radius: 4px; height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #3fb8ba; border-radius: 4px; }
QLabel[role="value"] { font-family: Consolas; }
QLabel[role="pill"] { border-radius: 9px; padding: 2px 9px; font-weight: 700; font-size: 12px; }
QLabel[role="banner"] { background: #5a3d05; color: #ffd98a; padding: 8px 14px; font-weight: 600; border-radius: 6px; }
QLabel[role="error"] { background: #4a1f1b; color: #ffb4ad; padding: 8px 12px; font-weight: 600; border-radius: 6px; }
QFrame[role="success"] { background: #0f2a1f; border: 1px solid #1f5a3d; border-radius: 8px; }
QFrame[role="failed"] { background: #2e1512; border: 1px solid #6b2a24; border-radius: 8px; }
"""


# --------------------------------------------------------------------------
#  worker thread: runs one ProvisioningRun, emits events
# --------------------------------------------------------------------------
class RunWorker(QThread):
    event = Signal(str, dict)          # (event name, detail)
    progress = Signal(str, int, int)   # (kind, done, total)
    finished_run = Signal(object)      # RunState

    def __init__(self, cfg: provision.Config, fake: bool, previous_serial: str | None):
        super().__init__()
        self.cfg, self.fake, self.previous_serial = cfg, fake, previous_serial
        self.run_obj: provision.ProvisioningRun | None = None

    def run(self):
        def on_event(ev, detail):
            if ev in ("download", "flash"):
                self.progress.emit(ev, int(detail.get("done", 0)), int(detail.get("total", 1)))
            else:
                self.event.emit(ev, detail)
        if self.fake:
            from tests_support import FakeDeviceAgent
            r = provision.ProvisioningRun(self.cfg, FakeRpiboot(),
                                          FakeDeviceAgent(crypto.TrustStore.from_dir(self.cfg.trust_dir)), on_event=on_event)
        else:
            r = provision.ProvisioningRun(self.cfg, Rpiboot(), provision.DeviceAgent(), on_event=on_event)
        r.state.previous_serial = self.previous_serial
        self.run_obj = r
        self.finished_run.emit(r.run())


class UsbWatcher(QThread):
    """Polls the USB bus for a Raspberry Pi module (boot ROM / gadget)."""
    changed = Signal(object)          # UsbModule | None

    def __init__(self, fake: bool, interval_s: float = 2.0):
        super().__init__()
        self.fake, self.interval_s, self._stop = fake, interval_s, False

    def run(self):
        last = "?"
        while not self._stop:
            if self.fake:
                from rpiboot import UsbModule
                cur = UsbModule("0a5c", "2712", "BCM2712 (CM5 / Pi 5) — simulated", "rpiboot")
            else:
                cur = detect_usb_module()
            key = (cur.vid, cur.pid, cur.mode) if cur else None
            if key != last:
                self.changed.emit(cur)
                last = key
            self.msleep(int(self.interval_s * 1000))

    def stop(self):
        self._stop = True


class CatalogWorker(QThread):
    done = Signal(dict)

    def __init__(self, cfg: provision.Config):
        super().__init__()
        self.cfg = cfg

    def run(self):
        try:
            cat = ImageCatalog(self.cfg.server_url, crypto.TrustStore.from_dir(self.cfg.trust_dir),
                               self.cfg.workdir / "image-cache", self.cfg.product, self.cfg.channel)
            res = cat.resolve(None)
            local = cat.newest_cached()
            self.done.emit({"ok": True, "online": res.online, "latestProduction": res.version, "buildId": res.build_id,
                            "localVersion": local["payload"]["imageVersion"] if local else None,
                            "versions": res.server_versions, "appVersion": res.payload.get("appVersion")})
        except (CatalogError, Exception) as e:  # noqa: BLE001 - shown to the operator
            self.done.emit({"ok": False, "online": False, "error": str(e)})


# --------------------------------------------------------------------------
#  widgets
# --------------------------------------------------------------------------
def _tint(color: str, alpha: float = 0.16) -> str:
    """Qt stylesheets read #RRGGBBAA as #AARRGGBB — use rgba() for tints."""
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


def pill(text: str, color: str) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "pill")
    lb.setStyleSheet(f"background: {_tint(color)}; color: {color};")
    lb.setAlignment(Qt.AlignCenter)
    lb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return lb


def set_pill(lb: QLabel, text: str, color: str):
    lb.setText(text)
    lb.setStyleSheet(f"background: {_tint(color)}; color: {color};")


def value_label(text="—", size=14) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "value")
    f = QFont("Consolas"); f.setPointSize(size); lb.setFont(f)
    lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


class KeyValue(QGridLayout):
    def __init__(self):
        super().__init__()
        self.setHorizontalSpacing(14); self.setVerticalSpacing(6)
        self.setColumnStretch(1, 1)

    def add(self, key: str, widget: QWidget):
        r = self.rowCount()
        k = QLabel(key); k.setStyleSheet(f"color: {C_MUTE};")
        self.addWidget(k, r, 0, alignment=Qt.AlignTop)
        self.addWidget(widget, r, 1)
        return widget


class MainWindow(QMainWindow):
    def __init__(self, cfg: provision.Config, fake: bool, real_usb: bool = False):
        super().__init__()
        self.cfg, self.fake, self.real_usb = cfg, fake, real_usb
        self.worker: RunWorker | None = None
        self.catalog: dict = {}
        self.usb_module = None
        self.last_serial: str | None = None
        self.completed: set[str] = set()
        self.setWindowTitle("Stratasys Factory Provisioning Tool")
        self.resize(1280, 820)
        self._build()
        self.refresh_catalog()
        self.usb = UsbWatcher(self.fake and not self.real_usb)
        self.usb.changed.connect(self.on_usb)
        self.usb.start()

    # ---------------- layout ----------------
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(18, 14, 18, 14); v.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel("Stratasys Factory Provisioning Tool"); f = QFont("Segoe UI", 15, QFont.DemiBold); t.setFont(f)
        head.addWidget(t); head.addStretch()
        self.p_usb = pill("CM5: checking USB…", C_MUTE)
        head.addWidget(self.p_usb); head.addSpacing(16)
        self.lbl_station = QLabel(f"Station {self.cfg.station_id} · {'SIMULATED MODULE' if self.fake else 'CM5 over USB'}")
        self.lbl_station.setStyleSheet(f"color: {C_MUTE}; font-family: Consolas;")
        head.addWidget(self.lbl_station)
        v.addLayout(head)

        self.banner = QLabel(); self.banner.setProperty("role", "banner"); self.banner.hide()
        v.addWidget(self.banner)

        cols = QHBoxLayout(); cols.setSpacing(12); v.addLayout(cols, 1)

        # --- provisioning column
        g1 = QGroupBox("PROVISIONING"); l1 = QVBoxLayout(g1)
        self.steps = QListWidget(); self.steps.setSelectionMode(QListWidget.NoSelection); self.steps.setFocusPolicy(Qt.NoFocus)
        for s in provision.ORDER:
            it = QListWidgetItem(f"○  {STEP_LABELS[s.value]}"); it.setData(Qt.UserRole, s.value); self.steps.addItem(it)
        l1.addWidget(self.steps, 1)
        self.prog_label = QLabel(""); self.prog_label.setStyleSheet(f"color: {C_MUTE}; font-size: 12px;")
        self.prog = QProgressBar(); self.prog.setRange(0, 100); self.prog.setTextVisible(False)
        self.prog_label.hide(); self.prog.hide()
        l1.addWidget(self.prog_label); l1.addWidget(self.prog)
        self.operator = QLineEdit(getpass.getuser()); self.operator.setPlaceholderText("Operator name (required)")
        self.operator.textChanged.connect(self._update_buttons)
        l1.addWidget(self.operator)
        row = QHBoxLayout()
        self.btn_start = QPushButton("Start Provisioning"); self.btn_start.clicked.connect(self.start_run)
        self.btn_refresh = QPushButton("Check for newer image"); self.btn_refresh.setProperty("secondary", True)
        self.btn_refresh.clicked.connect(self.refresh_catalog)
        row.addWidget(self.btn_start); row.addWidget(self.btn_refresh); l1.addLayout(row)
        self.err = QLabel(); self.err.setProperty("role", "error"); self.err.setWordWrap(True); self.err.hide()
        l1.addWidget(self.err)
        cols.addWidget(g1, 5)

        # --- image + module column
        mid = QVBoxLayout(); mid.setSpacing(10)
        g2 = QGroupBox("APPROVED IMAGE"); kv2 = KeyValue(); g2.setLayout(kv2)
        self.v_latest = kv2.add("Latest Production Version", value_label())
        self.v_local = kv2.add("Local Image Version", value_label())
        self.v_other = kv2.add("Development / QA", value_label(size=11))
        self.p_sig = kv2.add("Image Signature", pill("—", C_MUTE))
        self.p_img = kv2.add("Image Status", pill("—", C_MUTE))
        self.v_build = kv2.add("Build ID", value_label(size=11))
        mid.addWidget(g2)
        g3 = QGroupBox("MODULE"); kv3 = KeyValue(); g3.setLayout(kv3)
        self.v_hw = kv3.add("Hardware", value_label(size=12))
        self.v_board = kv3.add("Board serial", value_label(size=12))
        self.v_eeprom = kv3.add("EEPROM", value_label(size=12))
        self.v_storage = kv3.add("Storage", value_label(size=12))
        mid.addWidget(g3); mid.addStretch()
        cols.addLayout(mid, 4)

        # --- unit column
        right = QVBoxLayout(); right.setSpacing(10)
        g4 = QGroupBox("UNIT"); kv4 = KeyValue(); g4.setLayout(kv4)
        self.v_serial = kv4.add("Serial Number", value_label(size=20))
        self.v_prev = kv4.add("Previous Serial", value_label())
        self.v_devid = kv4.add("Device ID", value_label(size=10))
        self.v_imgver = kv4.add("Image Version", value_label())
        self.v_appver = kv4.add("Software Version", value_label())
        self.p_sb = kv4.add("Secure Boot", pill("—", C_MUTE))
        self.p_enc = kv4.add("Disk Encryption", pill("—", C_MUTE))
        self.p_lic = kv4.add("License", pill("—", C_MUTE))
        self.p_test = kv4.add("Final Test", pill("—", C_MUTE))
        right.addWidget(g4)
        g5 = QGroupBox("GENERATE NEW SERIAL NUMBER"); l5 = QVBoxLayout(g5)
        hint = QLabel("Assigns the next serial from the central counter to the connected unit. "
                      "The previous serial is kept for traceability. Factory / Service only.")
        hint.setWordWrap(True); hint.setStyleSheet(f"color: {C_MUTE}; font-size: 12px;"); l5.addWidget(hint)
        self.prev_serial = QLineEdit(); self.prev_serial.setPlaceholderText("Current serial of the unit (SC000000)")
        self.prev_serial.textChanged.connect(self._update_buttons); l5.addWidget(self.prev_serial)
        self.btn_new = QPushButton("Generate New Serial Number"); self.btn_new.setProperty("secondary", True)
        self.btn_new.clicked.connect(self.new_serial); l5.addWidget(self.btn_new)
        right.addWidget(g5); right.addStretch()
        cols.addLayout(right, 4)

        # --- result banners + log
        self.success = QFrame(); self.success.setProperty("role", "success"); sl = QGridLayout(self.success)
        st = QLabel("Provisioning Successful"); st.setStyleSheet(f"color: {C_OK}; font-size: 20px; font-weight: 700;")
        sl.addWidget(st, 0, 0, 1, 4)
        sl.addWidget(QLabel("Machine Serial"), 1, 0); self.s_serial = value_label(size=22); sl.addWidget(self.s_serial, 1, 1)
        sl.addWidget(QLabel("Device Status"), 1, 2); ds = value_label("READY FOR PRODUCTION", size=22); ds.setStyleSheet(f"color: {C_OK};"); sl.addWidget(ds, 1, 3)
        sl.addWidget(QLabel("Image"), 2, 0); self.s_image = value_label(size=12); sl.addWidget(self.s_image, 2, 1)
        sl.addWidget(QLabel("Provisioning"), 2, 2); self.s_online = value_label(size=12); sl.addWidget(self.s_online, 2, 3)
        self.success.hide(); v.addWidget(self.success)
        self.failed = QFrame(); self.failed.setProperty("role", "failed"); fl = QVBoxLayout(self.failed)
        self.f_text = QLabel(); self.f_text.setWordWrap(True); self.f_text.setStyleSheet(f"color: {C_BAD}; font-weight: 700;")
        fl.addWidget(self.f_text)
        fh = QLabel("The reserved serial (if any) was voided; it will never be reused. Fix the cause and press Start again.")
        fh.setStyleSheet(f"color: {C_MUTE}; font-size: 12px;"); fl.addWidget(fh)
        self.failed.hide(); v.addWidget(self.failed)
        g6 = QGroupBox("LOG"); l6 = QVBoxLayout(g6)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(500); self.log.setFixedHeight(150)
        l6.addWidget(self.log); v.addWidget(g6)
        self._update_buttons()

    # ---------------- state ----------------
    def _running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _update_buttons(self):
        has_op = bool(self.operator.text().strip())
        cat_ok = bool(self.catalog.get("ok"))
        usb_ok = (self.fake and not self.real_usb) or self.usb_module is not None
        ready = not self._running() and has_op and cat_ok and usb_ok
        self.btn_start.setEnabled(ready)
        self.btn_start.setToolTip("" if ready else ("Enter the operator name first" if not has_op else
                                  "No approved image available" if not cat_ok else
                                  "Connect the CM5 over USB (nRPIBOOT mode) first"))
        self.btn_new.setEnabled(not self._running() and has_op and usb_ok and serials.is_valid(self.prev_serial.text().strip().upper()))
        self.btn_refresh.setEnabled(not self._running())

    def on_usb(self, mod):
        self.usb_module = mod
        if mod is None:
            set_pill(self.p_usb, "CM5: NOT CONNECTED — connect over USB in nRPIBOOT mode", C_BAD)
            self.v_hw.setText("—")
        elif mod.mode == "rpiboot":
            set_pill(self.p_usb, f"CM5: CONNECTED · {mod.description} ({mod.vid}:{mod.pid}) · ready for rpiboot", C_OK)
            if not self._running():
                self.v_hw.setText(mod.description)
        else:
            set_pill(self.p_usb, f"CM5: CONNECTED · {mod.description} (gadget loaded)", C_OK)
        self.log.appendPlainText("         USB                    " + ("module connected" if mod else "module disconnected"))
        self._update_buttons()

    def closeEvent(self, ev):
        if hasattr(self, "usb"):
            self.usb.stop(); self.usb.wait(3000)
        super().closeEvent(ev)

    def show_error(self, text: str | None):
        self.err.setText(text or ""); self.err.setVisible(bool(text))

    def refresh_catalog(self):
        self.btn_refresh.setEnabled(False)
        self._cat = CatalogWorker(self.cfg)
        self._cat.done.connect(self._catalog_done); self._cat.start()

    def _catalog_done(self, c: dict):
        self.catalog = c
        self.v_latest.setText(c.get("latestProduction") or "—")
        self.v_local.setText(c.get("localVersion") or "none")
        self.v_build.setText(c.get("buildId") or "—")
        vs = c.get("versions") or {}
        self.v_other.setText(f"dev {vs.get('development') or '—'} · qa {vs.get('qa') or '—'}" if vs else "—")
        self.v_appver.setText(c.get("appVersion") or "—")
        if c.get("ok"):
            set_pill(self.p_sig, "cached · re-verified before flash", C_MUTE); set_pill(self.p_img, "READY TO VERIFY", C_MUTE)
        else:
            set_pill(self.p_sig, c.get("error") or "NO IMAGE", C_BAD); set_pill(self.p_img, "NOT AVAILABLE", C_BAD)
        if c.get("ok") and not c.get("online"):
            self.banner.setText("OFFLINE MODE — Unable to verify whether a newer Production Image is available. "
                                f"Using cached approved image: {c.get('latestProduction')}"); self.banner.show()
        else:
            self.banner.hide()
        self._update_buttons()

    # ---------------- actions ----------------
    def start_run(self):
        self._launch(None)

    def new_serial(self):
        prev = self.prev_serial.text().strip().upper()
        if not serials.is_valid(prev):
            self.show_error("previous serial must be the unit's current serial (SC000000)"); return
        if self.cfg.role not in ("factory", "service"):
            self.show_error("only Factory or Service users may reassign a serial"); return
        if QMessageBox.question(self, "Generate New Serial Number",
                                f"Assign the NEXT serial number to the unit currently {prev}?\n"
                                "The previous serial stays in the manufacturing database and the audit log.") != QMessageBox.Yes:
            return
        self._launch(prev)

    def _launch(self, previous_serial: str | None):
        op = self.operator.text().strip()
        if not op:
            self.show_error("operator name required"); return
        self.show_error(None); self.success.hide(); self.failed.hide(); self.log.clear()
        self.completed = set()
        for i in range(self.steps.count()):
            self.steps.item(i).setText(f"○  {STEP_LABELS[self.steps.item(i).data(Qt.UserRole)]}")
            self.steps.item(i).setForeground(QColor("#e6ebf0"))
        for w in (self.v_serial, self.v_prev, self.v_devid, self.v_imgver, self.v_hw, self.v_board, self.v_eeprom, self.v_storage):
            w.setText("—")
        for p in (self.p_sb, self.p_enc, self.p_lic, self.p_test):
            set_pill(p, "—", C_MUTE)
        cfg = provision.Config(**{**self.cfg.__dict__, "operator": op})
        self.worker = RunWorker(cfg, self.fake, previous_serial)
        self.worker.event.connect(self.on_event)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_run.connect(self.on_finished)
        self.worker.start()
        self._update_buttons()

    # ---------------- run feedback ----------------
    def _step_item(self, step: str) -> QListWidgetItem | None:
        for i in range(self.steps.count()):
            if self.steps.item(i).data(Qt.UserRole) == step:
                return self.steps.item(i)
        return None

    def on_event(self, ev: str, d: dict):
        step = d.get("step") or ""
        self.log.appendPlainText(f"{(d.get('ts') or '')[11:19]} {step:22} {ev}"
                                 + (f" — {d['status']}" if d.get("status") else "") + (f" {d['serial']}" if d.get("serial") else ""))
        it = self._step_item(step)
        if ev == "step started" and it:
            it.setText(f"●  {STEP_LABELS[step]}"); it.setForeground(QColor("#f5b942"))
        elif ev == "step completed" and it:
            it.setText(f"✓  {STEP_LABELS[step]}"); it.setForeground(QColor(C_OK)); self.completed.add(step)
            self.prog.hide(); self.prog_label.hide()
        st = self.worker.run_obj.state if self.worker and self.worker.run_obj else None
        if not st:
            return
        if ev == "image resolved":
            self.v_latest.setText(d.get("latestProduction") or "—"); self.v_local.setText(d.get("localVersion") or "none")
            if not d.get("online"):
                self.banner.setText(d.get("status", "OFFLINE MODE")); self.banner.show()
        if ev.startswith("Image Signature: VALID"):
            set_pill(self.p_sig, "VALID", C_OK); set_pill(self.p_img, "READY FOR INSTALLATION", C_OK)
            self.v_imgver.setText(st.image.get("version", "—")); self.v_build.setText(st.image.get("buildId", "—"))
        if ev == "image flashed":
            set_pill(self.p_img, "INSTALLED", C_OK)
        if ev == "module detected":
            m = st.module
            self.v_hw.setText(m.get("model") or "—"); self.v_board.setText(m.get("board_serial") or "—")
            self.v_eeprom.setText(m.get("eeprom_version") or "—")
            self.v_storage.setText(f"{m.get('storage_size_bytes', 0) / 1e9:.0f} GB · {m.get('storage_device', '')}")
        if step == "CONFIGURE_BOOT" and ev == "step completed":
            set_pill(self.p_sb, "PROGRAMMED" if st.module.get("secure_boot") else "NOT PROGRAMMED (lab)",
                     C_OK if st.module.get("secure_boot") else C_WARN)
        if ev == "device identity created":
            self.v_devid.setText(st.device_id or "—")
        if ev == "serial assigned":
            self.v_serial.setText(st.serial or "—"); self.v_prev.setText(st.previous_serial or "—")
        if ev == "license bound and verified on device":
            feats = ",".join((st.license or {}).get("payload", {}).get("features", []))
            set_pill(self.p_lic, ("PROVISIONAL · " if st.provisional else "VALID · ") + feats, C_WARN if st.provisional else C_OK)
        if ev == "data partition encrypted":
            set_pill(self.p_enc, f"LUKS2 · {d.get('keySource', 'otp-hkdf')}", C_OK)
        if ev == "machine self-test passed":
            set_pill(self.p_test, "MACHINE OK", C_OK)
        if ev == "software verified":
            set_pill(self.p_test, "PASS", C_OK)
            if d.get("appVersion"):
                self.v_appver.setText(str(d["appVersion"]))

    def on_progress(self, kind: str, done: int, total: int):
        self.prog_label.setText(("Flashing" if kind == "flash" else "Downloading latest approved image...") + f" {100 * done // max(total, 1)}%")
        self.prog.setValue(100 * done // max(total, 1)); self.prog_label.show(); self.prog.show()

    def on_finished(self, st):
        self.prog.hide(); self.prog_label.hide()
        if st.result == "READY_FOR_PRODUCTION":
            self.last_serial = st.serial
            self.s_serial.setText(st.serial or "—")
            self.s_image.setText(f"{st.image.get('version')} (build {st.image.get('buildId')})")
            self.s_online.setText("Online" if st.online else "OFFLINE — record queued for upload")
            self.success.show()
            self.prev_serial.setPlaceholderText(f"Current serial of the unit (last: {st.serial})")
        else:
            it = self._step_item(st.log[-1]["step"] if st.log else "")
            if it:
                it.setText(f"✗  {it.text()[3:]}"); it.setForeground(QColor(C_BAD))
            self.f_text.setText(f"Provisioning FAILED — {st.error}")
            self.failed.show()
        self.refresh_catalog()
        self._update_buttons()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stratasys Factory Provisioning Tool (desktop)")
    ap.add_argument("--station", required=True)
    ap.add_argument("--server")
    ap.add_argument("--workdir", default=os.path.expanduser("~/.stratasys-provisioning"))
    ap.add_argument("--trust", default=str(Path(__file__).with_name("trust")))
    ap.add_argument("--channel", default="production")
    ap.add_argument("--role", default="factory")
    ap.add_argument("--signed-eeprom")
    ap.add_argument("--offline-token")
    ap.add_argument("--station-key")
    ap.add_argument("--fake", action="store_true", help="simulated module (no rpiboot)")
    ap.add_argument("--real-usb", action="store_true", help="with --fake: still detect a real CM5 on the USB bus")
    a = ap.parse_args(argv)
    cfg = provision.Config(a.station, "", a.server, Path(a.workdir), Path(a.trust), channel=a.channel, role=a.role,
                           signed_eeprom_dir=Path(a.signed_eeprom) if a.signed_eeprom else None,
                           offline_token=Path(a.offline_token) if a.offline_token else None,
                           station_key=Path(a.station_key) if a.station_key else None)
    qapp = QApplication(sys.argv[:1])
    qapp.setStyleSheet(STYLE)
    pal = qapp.palette(); pal.setColor(QPalette.Window, QColor("#0f1418")); qapp.setPalette(pal)
    win = MainWindow(cfg, a.fake, real_usb=a.real_usb)
    win.show()
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
