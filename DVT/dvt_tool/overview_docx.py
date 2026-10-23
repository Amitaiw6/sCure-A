"""DVT overview as a Word document — every test is a heading.

    python -m dvt_tool.overview_docx [--out DVT/docs/DVT_Overview.docx] [--data ~/.scure-dvt]

Structure (Word navigation pane = the test list):
    Title, key figures, what the DVT proves, method
    1 … 5  one Heading 1 per phase, one Heading 2 per test
           ("DVT-SAF-012 — Door interlock — UV inhibited with the door open")
           with one line: applicability · repetitions · what it verifies
    Units, instrumentation, the console, status, decisions needed
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dvt_tool.catalog import Catalog  # noqa: E402
from dvt_tool.store import Store  # noqa: E402
from dvt_tool.overview import gather  # noqa: E402

INK, MUTED, ACCENT = RGBColor(0x1B, 0x24, 0x30), RGBColor(0x6B, 0x7A, 0x8C), RGBColor(0xE8, 0x46, 0x1F)


def first_sentence(text: str, limit: int = 260) -> str:
    t = " ".join((text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else t
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def applicability(cat: Catalog, tid: str) -> str:
    t = cat.tests[tid]; app = t["applicability"]; rule = app["rule"]
    if rule == "ALL": a = "all 5 units"
    elif rule == "SINGLE": a = f"{app.get('unit') or 'unit TBD'} only"
    else: a = f"{len(app.get('units') or [])} units"
    n = len(cat.runs(tid)); reps = t.get("repetitions") or 1
    var = ""
    if t.get("sweep"): var = f"{len(t['sweep']['matrix'])} matrix rows · "
    elif t.get("case_matrix"): var = f"{len(t['case_matrix'])} cases · "
    return f"{a} · {var}{reps} rep · {n} runs"


def _shade(cell, hex_fill: str):
    tcPr = cell._tc.get_or_add_tcPr(); shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill); tcPr.append(shd)


def _table(doc, header: list[str], rows: list[list[str]], widths: list[float] | None = None, font_pt: float = 9):
    t = doc.add_table(rows=1, cols=len(header)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]; c.text = ""; r = c.paragraphs[0].add_run(h); r.bold = True; r.font.size = Pt(font_pt); r.font.color.rgb = INK; _shade(c, "EEF1F5")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""; r = cells[i].paragraphs[0].add_run(str(v)); r.font.size = Pt(font_pt)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths): row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def _p(doc, text: str, size: float = 10, color=None, bold=False, italic=False, space_after=4, style=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    r = p.add_run(text); r.font.size = Pt(size); r.bold = bold; r.italic = italic
    if color is not None: r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(space_after); return p


def _bullets(doc, items: list[tuple[str, str]]):
    for head, body in items:
        p = doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after = Pt(2)
        r = p.add_run(head + " "); r.bold = True; r.font.size = Pt(9.5)
        r = p.add_run(body); r.font.size = Pt(9.5)


def load_revisions(path: Path, today: str, catalog_version: str) -> list[dict]:
    """Revision rows from <doc>.revisions.json; a first issue is created when the file does not exist."""
    import json
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = [{"rev": "A", "date": today, "author": "Amitai Wecker", "description": f"Initial issue — DVT plan and test list, catalog v{catalog_version}"}]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def build(cat: Catalog, d: dict, out: Path) -> Path:
    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10); st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    for name, size, color in (("Title", 22, INK), ("Heading 1", 14, INK), ("Heading 2", 11.5, INK), ("Heading 3", 10.5, MUTED)):
        s = doc.styles[name]; s.font.name = "Arial"; s.font.size = Pt(size); s.font.bold = True; s.font.color.rgb = color
        s.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Cm(1.8); sec.left_margin = sec.right_margin = Cm(2.0)
    today = date.today().isoformat(); pr = d["progress"] or {}

    doc.add_paragraph("sCure / CureBox — Design Verification Test (DVT)", style="Title")
    _p(doc, f"Campaign overview and test list · catalog v{d['version']} · SRS-DVT-SW Rev B · {today}", 10, MUTED, space_after=8)

    # ---- revision history (DVT/docs/DVT_Overview.revisions.json — add a row per issue)
    revs = load_revisions(out.with_suffix(".revisions.json"), today, d["version"])
    doc.add_heading("Revision history", level=1)
    _table(doc, ["Rev", "Date", "Author", "Description"], [[r["rev"], r["date"], r["author"], r["description"]] for r in revs], widths=[1.4, 2.6, 3.6, 8.6])

    doc.add_heading("What the DVT proves", level=1)
    subs = ", ".join(f"{k} {v}" for k, v in sorted(d["by_sub"].items(), key=lambda kv: -kv[1]))
    _p(doc, "The DVT qualifies the sCure resin-curing chamber design on five production-representative units before release: "
            "electrical safety (bonding, insulation, hipot, touch current, inrush), every protective function under injected faults "
            "(door interlock, thermal cutout, watchdog, sensor and fan failures, mains faults, LED and nitrogen faults), performance "
            "(chamber thermal characterisation, LED temperature, cool-down, nitrogen purge), transport and, last, destructive mains-fault "
            f"tests on the designated unit. Tests by subsystem: {subs}.")
    _p(doc, "Every test is defined once, in a machine-readable catalog the DVT console executes: applicability per unit, sweep or case "
            "matrix, equipment with calibration status, preconditions, a step-by-step procedure with the fields each step records, data "
            "fields with plausible ranges, and a pass criterion evaluated automatically (PASS / FAIL / BLOCKED — a criterion whose limit is "
            "still undecided is reported BLOCKED, never PASS).")

    doc.add_heading("Method — the rules every test follows", level=1)
    _bullets(doc, [
        ("Shutdowns are proven on the output, not the controller.", "A heater cut-off is read from the type-K thermocouple bonded to the heater body (PicoLog TC-08): the instant the trace turns from rising to falling is when power was removed; faults are injected during heat-up at full output so the turn is unmistakable. LED cut-off is read from the Ophir StarBright irradiance trace (below 10 % of plateau)."),
        ("Alarms must name the component.", "Every fault test records the alarm text and code and judges whether it names the right fan, sensor, panel or line — and, where the machine cannot know, whether it says so instead of guessing."),
        ("Every unit for workmanship, one unit for design.", "Bonding, seals, harnesses and fittings vary unit to unit and are tested on all five; software behaviour and destructive faults run once on the designated unit."),
        ("Nothing is guessed.", "Limits still to be decided are CONFIRM items in the catalog; the affected tests stay BLOCKED until the number is set and the decision is logged."),
    ])

    # ---- the tests, one heading each, grouped by phase
    doc.add_heading("The tests", level=1)
    _p(doc, "One heading per test, in the order they are run, each with one line on what it verifies.", 9.5, MUTED)
    phases = sorted(cat.phases, key=lambda p: p["id"])
    for ph in phases:
        tids = ph.get("tests") or []
        if not tids and ph["id"] != 0:
            continue
        hrs = next((p["hours"] for p in d["per_phase"] if p["id"] == ph["id"]), 0); runs = next((p["runs"] for p in d["per_phase"] if p["id"] == ph["id"]), 0)
        doc.add_heading(f"Phase {ph['id']} — {ph['name']}", level=1)
        if ph["id"] == 0:
            _p(doc, "Incoming inspection, configuration record (serial, firmware, catalog revision) frozen and signed per unit; equipment calibrations checked; test-readiness review (TRR) signed before Phase 1.", 9.5)
        for tid in tids:
            t = cat.tests[tid]
            doc.add_heading(f"{tid} — {t['title']}", level=2)
            _p(doc, first_sentence(t.get("purpose", "")), 9.5, space_after=6)

    # ---- units
    doc.add_heading("Units under test", level=1)
    _table(doc, ["Unit", "Role", "Notes"],
           [[u["id"], u.get("role_label") or u.get("role") or "", u.get("notes") or ""] for u in d["units"]], widths=[2.4, 3.0, 10.8])

    doc.add_heading("Instrumentation", level=1)
    _bullets(doc, [
        ("PicoLog TC-08 ×2", "— 16 type-K thermocouples on a fixed 3-D grid (THM-001), heater-body and LED MCPCB bonds; the TC-08 clock is the time base of every shutdown test."),
        ("Ophir StarBright", "UV power meter (PD300-UV head) read directly by the console: LEDs at maximum → trigger → irradiance vs time, graph and CSV attached to the run."),
        ("Oxygen analyser", "(centre + worst corner), inline N₂ flow meter, chamber manometer — purge to 95 % N₂, hold through the cure, inlet over-pressure, venting, room O₂ at the operator."),
        ("Programmable AC source", "100 / 110 / 230 / 240 V, true-RMS meter, clamp on the heater branch, current probe with single-shot scope for the fuse tests."),
        ("Safety bench", "— earth-bond tester, insulation tester, hipot, touch-current meter; thermal camera and fire-rated enclosure for the destructive tests."),
    ])

    doc.add_heading("The DVT console", level=1)
    _bullets(doc, [
        ("Guided execution", "— one wizard per run: safety plan, equipment and calibration check, preconditions, each step with only its fields, live values from the machine, redlines, attachments, verdict; a restart resumes where it stopped."),
        ("Machine in the loop", "— the console talks to the unit's hardware service and its SSH host; a built-in simulator with fault injection rehearses every protective test without hardware."),
        ("Team work through Microsoft SharePoint", "— the campaign folder is a SharePoint document library (Microsoft 365) synced to each bench with OneDrive; each console keeps its own journal in that folder and replays the others' every 15 s: one campaign, several benches; a run belongs to whoever started it first."),
        ("Controlled history in Git", "— a checkpoint (campaign JSON, workbook, report, summary) is committed at every phase gate and on demand."),
        ("Outputs", "— dashboard with progress per subsystem and per machine, verdict matrix across units, temperature statistics per component, XLSX / CSV / Markdown exports, the full campaign document with an engineering process figure per test, NCRs and waivers."),
    ])

    doc.add_heading("Decisions needed before Phase 2", level=1)
    nulls = ", ".join(f"{k.replace('_thresholds', '')}.{kk}" for k, kk in d["null_thresholds"])
    _p(doc, f"Limits still null in the catalog: {nulls}. The tests that reference them evaluate as BLOCKED until set.", 9.5, bold=True)
    _bullets(doc, [
        ("Fan and LED feedback.", "No tach on the second fan of each pair and no per-panel LED output feedback: SAF-008 / 019 / 020 need a hardware or firmware decision (tach lead, per-panel current sense on the spare ADS1115 inputs, or a thermistor rise-rate rule)."),
        ("Nitrogen sensing.", "No line-pressure sensor on the board; the 6 bar enable guard and the pre-cure N₂ check cannot work, and the Settings guard blocks nitrogen mode on real hardware. Fit an inlet pressure switch or drop the guard."),
        ("Voltage selector.", "A mid position is an open circuit; only the 25-minute stall rule can catch it and its text does not mention the selector. A \"no rise at all\" rule with customer guidance is recommended."),
        ("REQ-48 heat-up ≤ 20 min", "already fails at EVT (27–33 min); decide the number or a documented waiver before Phase 3. Low line at 100 V is now in THM-001; 207 V still open."),
        ("Campaign logistics", "— the destructive unit (UUT-05), the shipped unit for ENV-001, witnessing of Phases 1 and 5, a climate-controlled room for THM-003."),
    ])

    # footer
    for sec in doc.sections:
        fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run(f"sCure DVT overview · catalog v{d['version']} · generated by the DVT console · {today}"); r.font.size = Pt(8); r.font.color.rgb = MUTED
    out.parent.mkdir(parents=True, exist_ok=True); doc.save(str(out))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DVT overview as a Word document (one heading per test)")
    ap.add_argument("--catalog", default=str(HERE.parent / "catalog" / "DVT_test_catalog.yaml"))
    ap.add_argument("--data", default=os.path.expanduser("~/.scure-dvt"))
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "DVT_Overview.docx"))
    a = ap.parse_args(argv)
    cat = Catalog.load(a.catalog)
    db = Path(a.data) / "campaign.db"
    d = gather(cat, Store(db) if db.exists() else None)
    print(build(cat, d, Path(a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
