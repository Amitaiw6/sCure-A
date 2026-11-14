"""Two-page DVT overview (A4, English) — the campaign on two sheets for
management and reviewers: scope, phases and gates, method, instrumentation,
tooling, status, open decisions.

    python -m dvt_tool.overview [--out DVT/docs/DVT_Overview.pdf] [--data ~/.scure-dvt]

Figures come from the catalog and the campaign store; the PDF is printed with
the installed Chrome / Edge (headless), the HTML is kept next to it.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dvt_tool.catalog import Catalog  # noqa: E402
from dvt_tool.store import Store  # noqa: E402
from dvt_tool.engine import Engine  # noqa: E402
from dvt_tool import figures  # noqa: E402
from dvt_tool.docgen import find_browser  # noqa: E402


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def gather(cat: Catalog, store: Store | None) -> dict:
    runs = cat.runs()
    per_phase = []
    for ph in sorted(cat.phases, key=lambda p: p["id"]):
        tids = ph.get("tests") or []
        n_runs = sum(len(cat.runs(t)) for t in tids)
        hours = sum((cat.tests[t].get("duration_est_min") or 0) * len(cat.runs(t)) for t in tids) / 60
        per_phase.append({"id": ph["id"], "name": ph["name"], "tests": len(tids), "runs": n_runs, "hours": round(hours), "gate": ph.get("gate") or "—", "ids": tids})
    by_sub = Counter(t["subsystem"] for t in cat.tests.values())
    hours = sum((cat.tests[r.test_id].get("duration_est_min") or 0) for r in runs) / 60
    raw = (cat.path.read_text(encoding="utf-8") if cat.path else "")
    confirms = len(re.findall(r"CONFIRM", raw))
    nulls = [(k, kk) for k, v in cat.thresholds.items() for kk, vv in v.items() if vv is None]
    progress = None
    if store is not None:
        progress = Engine(cat, store).progress()
    return {"version": cat.version, "n_tests": len(cat.tests), "n_runs": len(runs), "units": cat.units, "per_phase": per_phase,
            "by_sub": dict(by_sub), "hours": round(hours), "confirms": confirms, "null_thresholds": nulls, "progress": progress}


CSS = """
@page { size: A4; margin: 12mm 13mm 12mm 13mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; color: #1b2430; font-size: 9.2pt; line-height: 1.32; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2px; letter-spacing: .2px; }
h2 { font-size: 10.5pt; margin: 9px 0 4px; padding-bottom: 2px; border-bottom: 1.5px solid #1b2430; text-transform: uppercase; letter-spacing: .6px; }
p { margin: 3px 0 5px; }
.sub { color: #6b7a8c; font-size: 8.6pt; margin: 0 0 6px; }
.hdr { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #e8461f; padding-bottom: 5px; margin-bottom: 6px; }
.hdr .brand { font-weight: 700; color: #6b7a8c; font-size: 8.5pt; letter-spacing: .8px; text-align: right; white-space: nowrap; }
.kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin: 6px 0 8px; }
.kpi { border: 1px solid #d9dee6; border-radius: 6px; padding: 5px 7px; background: #f7f8fa; }
.kpi b { display: block; font-size: 15pt; line-height: 1.1; }
.kpi span { color: #6b7a8c; font-size: 7.6pt; text-transform: uppercase; letter-spacing: .4px; }
table { border-collapse: collapse; width: 100%; font-size: 8.4pt; margin: 3px 0 6px; }
th { text-align: left; background: #eef1f5; color: #3d4a5c; font-size: 7.6pt; text-transform: uppercase; letter-spacing: .4px; padding: 3px 5px; border-bottom: 1px solid #c9d1dc; }
td { padding: 3px 5px; border-bottom: 1px solid #e6e9ee; vertical-align: top; }
td.n, th.n { text-align: right; white-space: nowrap; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
ul { margin: 2px 0 5px 16px; padding: 0; } li { margin: 1.5px 0; }
.tag { display: inline-block; font-family: Consolas, monospace; font-size: 7.8pt; background: #eef1f5; border-radius: 3px; padding: 0 4px; }
.warn { border-left: 3px solid #d68a0c; background: #fff7e8; padding: 4px 8px; margin: 4px 0; }
.fig { border: 1px solid #d9dee6; border-radius: 4px; padding: 3px; background: #fff; }
.fig svg { width: 100%; height: auto; display: block; }
.figcap { color: #6b7a8c; font-size: 7.6pt; margin: 2px 0 0; }
.foot { position: fixed; bottom: 4mm; left: 13mm; right: 13mm; color: #6b7a8c; font-size: 7.4pt; display: flex; justify-content: space-between; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
@media screen { body { background: #eef1f5; } .page { background: #fff; width: 210mm; min-height: 297mm; margin: 10px auto; padding: 12mm 13mm; box-shadow: 0 2px 12px rgba(0,0,0,.15); } .foot { position: static; margin-top: 10px; } }
"""


def build_html(d: dict, campaign: str = "sCure-DVT") -> str:
    today = date.today().isoformat()
    pr = d["progress"] or {}
    done, total = pr.get("done", 0), pr.get("total", d["n_runs"])
    subs = " · ".join(f"{k} {v}" for k, v in sorted(d["by_sub"].items(), key=lambda kv: -kv[1]))
    phase_rows = "".join(f"<tr><td><b>{p['id']}</b> — {_e(p['name'])}</td><td class='n'>{p['tests']}</td><td class='n'>{p['runs']}</td><td class='n'>{p['hours']}</td><td>{_e(p['gate'])}</td></tr>" for p in d["per_phase"])
    unit_rows = "".join(f"<tr><td><b>{_e(u['id'])}</b></td><td>{_e(u.get('role_label') or u.get('role') or '')}</td><td>{_e(u.get('notes') or '')}</td>"
                        f"<td class='n'>{(pr.get('perUnit') or {}).get(u['id'], {}).get('done', 0)}/{(pr.get('perUnit') or {}).get(u['id'], {}).get('total', 0)}</td></tr>" for u in d["units"])
    nulls = ", ".join(f"<span class='tag'>{_e(k.replace('_thresholds', ''))}.{_e(kk)}</span>" for k, kk in d["null_thresholds"])
    fig = figures.figure_svg("DVT-SAF-008", None, "Door interlock — UV inhibited with the door open", rev=d["version"], date=today)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>sCure DVT — overview</title><style>{CSS}</style></head><body>
<div class="page">
<div class="hdr"><div><h1>sCure / CureBox — Design Verification Test (DVT)</h1><div class="sub">Campaign overview · catalog v{_e(d['version'])} · SRS-DVT-SW Rev B · {today}</div></div><div class="brand">STRATASYS · sCure<br>DVT OVERVIEW · 2 pages</div></div>

<div class="kpis">
<div class="kpi"><b>{d['n_tests']}</b><span>tests</span></div><div class="kpi"><b>{len(d['units'])}</b><span>units under test</span></div>
<div class="kpi"><b>{d['n_runs']}</b><span>applicable runs</span></div><div class="kpi"><b>≈{d['hours']} h</b><span>bench time</span></div>
<div class="kpi"><b>{done}</b><span>runs committed</span></div><div class="kpi"><b>{d['confirms']}</b><span>CONFIRM items open</span></div>
</div>

<h2>1 · What the DVT proves</h2>
<p>The DVT qualifies the sCure resin-curing chamber design on five production-representative units before release: <b>electrical safety</b> (bonding, insulation, hipot, touch current, inrush), <b>every protective function</b> under injected faults (door interlock, thermal cutout, watchdog, sensor and fan failures, mains faults, LED and nitrogen faults), <b>performance</b> (chamber thermal characterisation, LED temperature, cool-down, nitrogen purge), <b>transport</b> and, last, two <b>destructive</b> mains-fault tests on the designated unit. Tests by subsystem: {_e(subs)}.</p>
<p>Every test is defined once, in a machine-readable catalog (YAML) that the DVT console executes: applicability per unit, sweep or case matrix, equipment with calibration status, preconditions, step-by-step procedure with the fields each step records, data fields with plausible ranges, and a pass criterion evaluated automatically (PASS / FAIL / BLOCKED — a criterion whose limit is still undecided is reported BLOCKED, never PASS).</p>

<h2>2 · Phases and gates</h2>
<table><tr><th>Phase</th><th class="n">Tests</th><th class="n">Runs</th><th class="n">Hours</th><th>Gate to the next phase</th></tr>{phase_rows}</table>
<p class="sub">A phase opens for a unit only when the previous one is closed for that unit; protective earth (DVT-ELE-001) must PASS before anything is energised. Phase 0 is the configuration freeze (serial, firmware, catalog revision) and the readiness review (TRR) signed per unit.</p>

<h2>3 · Units</h2>
<table><tr><th>Unit</th><th>Role</th><th>Notes</th><th class="n">Runs done</th></tr>{unit_rows}</table>

<h2>4 · Method — the rules every test follows</h2>
<ul>
<li><b>Shutdowns are proven on the output, not the controller.</b> A heater cut-off is read from the type-K thermocouple bonded to the heater body (PicoLog TC-08): the instant the trace turns from rising to falling is when power was removed; faults are injected during heat-up at full output so the turn is unmistakable. LED cut-off is read from the Ophir StarBright irradiance trace (below 10 % of plateau). The controller's own report is recorded, never trusted alone.</li>
<li><b>Alarms must name the component.</b> Every fault test records the alarm text and code and judges whether it names the right fan, sensor, panel or line — and, where the machine cannot know (a blocked air path vs a weak fan), whether it says so instead of guessing.</li>
<li><b>Every unit for workmanship, one unit for design.</b> Bonding, seals, harnesses and fittings vary unit to unit and are tested on all five; software behaviour and destructive faults run once on the designated unit.</li>
<li><b>Nothing is guessed.</b> Limits still to be decided are <span class="tag">CONFIRM</span> items in the catalog; the affected tests stay BLOCKED until the number is set and the decision is logged.</li>
</ul>
<div class="foot"><span>sCure DVT overview · catalog v{_e(d['version'])} · generated by the DVT console</span><span>page 1 / 2</span></div>
</div>

<div class="page">
<div class="cols">
<div>
<h2>5 · Instrumentation</h2>
<ul>
<li><b>PicoLog TC-08 ×2</b> — 16 type-K thermocouples on a fixed 3-D grid (DVT-THM-001), heater-body and LED MCPCB bonds; the TC-08 clock is the time base of every shutdown test.</li>
<li><b>Ophir StarBright</b> UV power meter (PD300-UV head) read directly by the console: LEDs at maximum → trigger → irradiance vs time, graph and CSV attached to the run (DVT-SAF-008 door, DVT-SAF-004 thermistor, DVT-SAF-010 watchdog).</li>
<li><b>Oxygen analyser</b> (centre + worst corner), inline N₂ flow meter, chamber manometer — purge to 95 % N₂, hold through the cure, inlet over-pressure, venting, room O₂ at the operator.</li>
<li><b>Programmable AC source</b> 100 / 110 / 230 / 240 V, true-RMS meter, clamp on the heater branch, current probe with single-shot scope for the fuse tests.</li>
<li><b>Safety bench</b> — earth-bond tester, insulation tester, hipot, touch-current meter; thermal camera and fire-rated enclosure for the destructive tests.</li>
</ul>

<h2>6 · The DVT console</h2>
<ul>
<li><b>Guided execution</b> — one wizard per run: safety plan, equipment and calibration check, preconditions, each step with only its fields, live values from the machine, redlines, attachments, verdict; a restart resumes where it stopped.</li>
<li><b>Machine in the loop</b> — the console talks to the unit's hardware service (state, heat / cool / UV / door / diagnostics) and its SSH host; a built-in simulator with fault injection rehearses every protective test without hardware.</li>
<li><b>Team work through Microsoft SharePoint</b> — the campaign folder is a SharePoint document library (Microsoft 365) synced to each bench with OneDrive; each console keeps its own journal there and replays the others' every 15 s: one campaign, several benches, first claim on a run wins; attachments in the shared folder.</li>
<li><b>Controlled history in Git</b> — a checkpoint (campaign JSON, workbook, report, summary) is committed at every phase gate and on demand.</li>
<li><b>Outputs</b> — dashboard with progress per subsystem and per machine, verdict matrix across units, temperature statistics per component, XLSX / CSV / Markdown exports, the full campaign document (every test with its engineering process figure), NCRs and waivers with approver and rationale.</li>
</ul>
</div>
<div>
<div class="fig">{fig}</div>
<p class="figcap">Process figure — one generated engineering sheet per test and per step: the machine, the mains chain, the instruments, the injected fault, with component tags and a title block (here: DVT-SAF-008, door interlock).</p>

<h2>7 · Status</h2>
<p>Catalog v{_e(d['version'])} baselined for review: {d['n_tests']} tests, {d['n_runs']} applicable runs, ≈{d['hours']} bench hours. Runs committed so far: <b>{done} / {total}</b>{(' · ' + str(pr.get('PASS', 0)) + ' PASS · ' + str(pr.get('FAIL', 0)) + ' FAIL · ' + str(pr.get('BLOCKED', 0)) + ' BLOCKED · ' + str(pr.get('openNcrs', 0)) + ' open NCRs') if pr else ''}.</p>

<h2>8 · Decisions needed before Phase 2</h2>
<div class="warn"><b>Limits still null in the catalog:</b> {nulls}. The tests that reference them evaluate as BLOCKED until set.</div>
<ul>
<li><b>Fan and LED feedback.</b> No tach on the second fan of each pair and no per-panel LED output feedback: DVT-SAF-005 / 015 / 016 need a hardware or firmware decision (tach lead, per-panel current sense on the spare ADS1115 inputs, or a thermistor rise-rate rule).</li>
<li><b>Nitrogen sensing.</b> No line-pressure sensor on the board (<span class="tag">n2LinePressure = null</span>); the 6 bar enable guard and the pre-cure N₂ check cannot work, and the Settings guard blocks nitrogen mode on real hardware. Fit an inlet pressure switch or drop the guard.</li>
<li><b>Voltage selector.</b> A mid position is an open circuit; only the 25-minute stall rule can catch it and its text does not mention the selector. A "no rise at all" rule with customer guidance is recommended.</li>
<li><b>REQ-48 heat-up ≤ 20 min</b> already fails at EVT (27–33 min); decide the number or a documented waiver before Phase 3. Low line at 100 V is now in DVT-THM-001; 207 V still open.</li>
<li><b>Campaign logistics</b> — the destructive unit (UUT-05), the shipped unit for DVT-ENV-001, witnessing of Phases 1 and 5, a climate-controlled room for DVT-THM-003.</li>
</ul>
<div class="foot"><span>sCure DVT overview · catalog v{_e(d['version'])} · generated by the DVT console</span><span>page 2 / 2</span></div>
</div>
</div>
</div>
</body></html>"""


def render_pdf(html_path: Path, pdf_path: Path) -> bool:
    b = find_browser()
    if not b:
        return False
    r = subprocess.run([b, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                       capture_output=True, text=True, timeout=120)
    return pdf_path.exists()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Two-page DVT overview (A4)")
    ap.add_argument("--catalog", default=str(HERE.parent / "catalog" / "DVT_test_catalog.yaml"))
    ap.add_argument("--data", default=os.path.expanduser("~/.scure-dvt"))
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "DVT_Overview.pdf"))
    a = ap.parse_args(argv)
    cat = Catalog.load(a.catalog)
    db = Path(a.data) / "campaign.db"
    store = Store(db) if db.exists() else None
    d = gather(cat, store)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    html_path = out.with_suffix(".html"); html_path.write_text(build_html(d), encoding="utf-8")
    ok = render_pdf(html_path, out)
    print(html_path); print(out if ok else "PDF not rendered (no Chrome / Edge found)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
