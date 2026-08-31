"""Start dialog: language, work mode (normal machine / simulation), machine
address, unit under test, operator. Shown at launch unless the command
line already decided (--machine / --no-dialog)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QLineEdit, QRadioButton,
                               QPushButton, QButtonGroup, QFrame)

from . import theme as T
from .i18n import tr, LANGUAGES, set_language
from .widgets import label


class StartDialog(QDialog):
    def __init__(self, machines: list[str], units: list[dict], operator: str, lang: str, mode: str, machine: str, unit: str | None):
        super().__init__(); self.setWindowTitle("sCure DVT"); self.setMinimumWidth(560); self.setModal(True)
        self._machines, self._units = machines, units
        self.result_ = None
        self._build(operator, lang, mode, machine, unit)

    def _build(self, operator, lang, mode, machine, unit):
        root = QVBoxLayout(self); root.setContentsMargins(24, 22, 24, 20); root.setSpacing(14)
        head = QHBoxLayout(); head.addWidget(label("sCure DVT", "h1")); head.addStretch()
        self.cb_lang = QComboBox()
        for code, name in LANGUAGES.items(): self.cb_lang.addItem(name, code)
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(lang))); self.cb_lang.currentIndexChanged.connect(self._relabel)
        head.addWidget(QLabel("🌐")); head.addWidget(self.cb_lang); root.addLayout(head)
        self.lbl_title = label(tr("Welcome — choose how to work"), "h2"); root.addWidget(self.lbl_title)

        box = QFrame(); box.setProperty("card", "true"); g = QGridLayout(box); g.setContentsMargins(16, 14, 16, 14); g.setVerticalSpacing(12); g.setHorizontalSpacing(14)
        self.l_mode = label(tr("Work mode:"), bold=True); g.addWidget(self.l_mode, 0, 0, Qt.AlignTop)
        mrow = QVBoxLayout(); self.rb_normal = QRadioButton(tr("Normal — real machine")); self.rb_sim = QRadioButton(tr("Simulation — built-in simulated machine"))
        grp = QButtonGroup(self); grp.addButton(self.rb_normal); grp.addButton(self.rb_sim)
        (self.rb_sim if mode == "sim" else self.rb_normal).setChecked(True)
        self.rb_normal.toggled.connect(lambda on: self.cb_machine.setEnabled(on)); mrow.addWidget(self.rb_normal); mrow.addWidget(self.rb_sim); g.addLayout(mrow, 0, 1)
        self.l_machine = label(tr("Machine address:"), bold=True); g.addWidget(self.l_machine, 1, 0)
        self.cb_machine = QComboBox(); self.cb_machine.setEditable(True)
        for m in self._machines:
            if not m.startswith("sim://"): self.cb_machine.addItem(m)
        self.cb_machine.setCurrentText(machine if not machine.startswith("sim://") else (self.cb_machine.itemText(0) if self.cb_machine.count() else "")); self.cb_machine.setEnabled(mode != "sim")
        g.addWidget(self.cb_machine, 1, 1)
        self.l_unit = label(tr("Unit under test:"), bold=True); g.addWidget(self.l_unit, 2, 0)
        self.cb_unit = QComboBox()
        for u in self._units: self.cb_unit.addItem(f"{u['id']}" + (f"  ·  {u.get('role')}" if u.get("role") else ""), u["id"])
        if unit: self.cb_unit.setCurrentIndex(max(0, self.cb_unit.findData(unit)))
        g.addWidget(self.cb_unit, 2, 1)
        self.l_op = label(tr("Operator:"), bold=True); g.addWidget(self.l_op, 3, 0); self.ed_op = QLineEdit(operator); g.addWidget(self.ed_op, 3, 1)
        root.addWidget(box)
        self.lbl_hint = label(tr("You can change all of this later in Settings and in the header."), "muted", wrap=True); root.addWidget(self.lbl_hint)
        row = QHBoxLayout(); row.addStretch(); self.btn = QPushButton(tr("Start")); self.btn.setProperty("kind", "big"); self.btn.clicked.connect(self._accept); row.addWidget(self.btn); root.addLayout(row)

    def _relabel(self):
        set_language(self.cb_lang.currentData()); self.setLayoutDirection(Qt.RightToLeft if self.cb_lang.currentData() == "he" else Qt.LeftToRight)
        self.lbl_title.setText(tr("Welcome — choose how to work")); self.l_mode.setText(tr("Work mode:")); self.rb_normal.setText(tr("Normal — real machine"))
        self.rb_sim.setText(tr("Simulation — built-in simulated machine")); self.l_machine.setText(tr("Machine address:")); self.l_unit.setText(tr("Unit under test:"))
        self.l_op.setText(tr("Operator:")); self.lbl_hint.setText(tr("You can change all of this later in Settings and in the header.")); self.btn.setText(tr("Start"))

    def _accept(self):
        self.result_ = {"lang": self.cb_lang.currentData(), "mode": "sim" if self.rb_sim.isChecked() else "normal",
                        "machine": self.cb_machine.currentText().strip(), "unit": self.cb_unit.currentData(), "operator": self.ed_op.text().strip()}
        self.accept()
