"""Confirmation for 'Restart DVT and erase all data' — irreversible, reason required."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QCheckBox, QDialogButtonBox

from .widgets import label
from .i18n import tr, trf
from . import theme as T


class ResetDialog(QDialog):
    """Are you sure? It is irreversible. Why? — Erase is enabled only with a reason and the acknowledgement ticked."""

    def __init__(self, parent, data_dir: Path, shared: Path | None, unit_id: str | None = None):
        super().__init__(parent)
        self.reason = ""; self.unit_id = unit_id
        self.setWindowTitle(trf("Restart {unit} and erase its data", unit=unit_id) if unit_id else tr("Restart DVT and erase all data")); self.setMinimumWidth(560)
        l = QVBoxLayout(self); l.setSpacing(12)
        l.addWidget(label("⚠  " + tr("Are you sure? This cannot be undone."), "h1", color=T.BAD))
        if unit_id:
            l.addWidget(label(trf("{unit} starts over: every run of this unit goes back to NOT_STARTED; its recorded values, verdicts, redlines, NCRs, waivers, attachments and phase sign-offs are erased and its configuration is un-frozen — on this console and, through the shared journal, on every other console. Other units, the catalog, calibration records and the console settings are untouched.", unit=unit_id), "instruction", wrap=True))
        else:
            l.addWidget(label(tr("Everything in this campaign is erased: runs, recorded values, verdicts, redlines, NCRs, waivers, calibration records, attachments, exports and the events log — on this console and in the shared folder, so every other console loses it too. The catalog and the console settings stay. The console restarts empty."), "instruction", wrap=True))
        l.addWidget(label(trf("Local data: {local}\nShared campaign: {shared}", local=data_dir, shared=shared or tr("not shared")), "mono", wrap=True))
        l.addWidget(label(tr("Reason (required — the only thing that is kept, in the reset log):"), "muted"))
        self.ed_reason = QLineEdit(); self.ed_reason.setPlaceholderText(tr("e.g. dry-run data before the real campaign; wrong catalog version; unit re-labelled…"))
        self.ed_reason.textChanged.connect(self._update); l.addWidget(self.ed_reason)
        self.cb_ack = QCheckBox(trf("I understand this is irreversible and every console loses {what}", what=trf("the data of {unit}", unit=unit_id) if unit_id else tr("the campaign data"))); self.cb_ack.toggled.connect(self._update); l.addWidget(self.cb_ack)
        row = QHBoxLayout(); row.addStretch(); l.addLayout(row)
        self.btn_erase = QPushButton(trf("Erase {unit} and restart it", unit=unit_id) if unit_id else tr("Erase everything and restart")); self.btn_erase.setProperty("kind", "danger"); self.btn_erase.setEnabled(False); self.btn_erase.clicked.connect(self._accept); row.addWidget(self.btn_erase)
        b = QPushButton(tr("Cancel")); b.setProperty("kind", "ghost"); b.clicked.connect(self.reject); row.addWidget(b)

    def _update(self, *_):
        self.btn_erase.setEnabled(bool(self.ed_reason.text().strip()) and self.cb_ack.isChecked())

    def _accept(self):
        self.reason = self.ed_reason.text().strip()
        if self.reason and self.cb_ack.isChecked():
            self.accept()
