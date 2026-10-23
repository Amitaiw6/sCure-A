# sCure DVT — verification campaign folder + application

Everything for the Design Verification Test campaign lives here: the test
catalog (the single source of truth), the verification plan / SRS, and the
desktop application that runs the campaign and keeps your Google Drive
up to date.

```
DVT/
├── catalog/DVT_test_catalog.yaml     40 tests, 5 UUTs, phases + gates — ADD NEW SYSTEM TESTS HERE
├── docs/DVT_Verification_Plan_SRS_RevB.md
├── dvt_tool/                          the application
│   ├── app.py        desktop UI (PySide6)      python -m dvt_tool.app
│   ├── catalog.py    load/validate the YAML, expand tests × units × sweep/case × reps into runs
│   ├── criteria.py   safe evaluator of pass_criteria (PASS / FAIL / BLOCKED)
│   ├── store.py      SQLite campaign store: runs, values, redlines, NCRs, waivers, attachments, calibration, TRR sign-off
│   ├── engine.py     wizard: phase gates, "earth before power", dependencies, next action, rolled-up verdicts
│   ├── export.py     JSON snapshot + per-test CSV + XLSX workbook + Markdown report
│   ├── drive.py      Google Drive sync (Drive API with your account, or a Drive-for-Desktop / OneDrive folder)
│   ├── figures.py    process figures: one generated machine schematic, per-test / per-step highlights   python -m dvt_tool.figures --out docs/figures
│   └── instruments/  bench instruments: ophir.py (StarBright via StarLab USB / serial / simulated), uvoff.py (SAF-012 door / SAF-007 thermistor UV-off sequence + graph)
└── tests/            pytest
```

## Run the application

```powershell
cd C:\Users\User\Documents\GitHub\sCure-A\DVT
..\.venv\Scripts\python -m dvt_tool.app
```

Data lives in `%USERPROFILE%\.scure-dvt\` (`campaign.db`, `export\`, `sync.json`).

### Start dialog — work mode and language

Every launch opens a small dialog: **language** (English / עברית — the whole
UI flips to right-to-left in Hebrew), **work mode** (Normal — real machine
by address, or Simulation — the built-in simulated machine), the machine
address, the unit under test and the operator. All of it can be changed
later: mode in Settings → *Work mode* (or the rail toggle), language in
Settings → *Language* → *Restart console now*. `run.bat --machine sim
--no-dialog` skips the dialog.

In Hebrew **everything** is Hebrew, in English everything is English
(SRS-DVT-194): the console's own text comes from `dvt_tool/ui/i18n.py`, and
the catalog prose (test titles, purposes, safety plans, equipment,
preconditions, procedure steps, phase names…) from the overlay
`catalog/DVT_test_catalog.he.yaml`, applied by `Catalog.load(path, lang)`.
When you add or change a test in the English catalog, add / update its
block in the overlay too — the lists are positional and the console refuses
to start in Hebrew if a step count differs. Identifiers never change
language: test ids, data field names, enum values, PASS / FAIL / BLOCKED /
WAIVED, pass criteria and run ids are the same in both, so results recorded
in either language are the same runs.

### Simulation mode (test the console without a machine)

Click **◉ Simulation mode** at the bottom of the rail (or type `sim` as the
DUT address, or start with `run.bat --machine sim`). A simulated sCure with
coarse physics answers instead of a real unit: heat/cool/UV/door/fan
controls work, and **DUT Control → Simulator — fault injection** lets you
open the door, open/short the heater sensor, open an LED thermistor,
disconnect or block an LED fan, lose the circulation or chamber fan, drop
mains, trip the thermal cutout and switch mains to 110/230/240 V — each
producing the alarm code and protective action the SAF tests look for. A
purple banner and the `SIM ·` prefix make it unmistakable, and every run
made in simulation is flagged in the campaign events.

### The screens

- **Header** — DUT address (the machine you test against; type an IP or pick
  a known one, Enter = connect), operator, campaign, test plan, live
  SYSTEM STATUS (OFFLINE / IDLE / HEATING / CURING / FAULT), UTC clock,
  Drive sync pill.
- **Dashboard** — KPIs, test distribution by subsystem (click to filter),
  test matrix grouped by subsystem with status / result / runs per test,
  live telemetry + interlocks of the connected machine.
- **Test Plans** — the catalog by phase; click a test to read its full
  definition.
- **Test Console** — pick a unit; the *Next action* card says what to run
  and why anything is blocked; **Start guided run →** opens the wizard.
- **DUT Control** — connect / discover the machine, live gauges, safe
  controls (heat, cool, UV on/off, door, STOP, LED/fan tests). Every
  action is confirmed and logged.
- **Instruments** — calibration records per instrument (SRS-DVT-085).
- **Reports** — export + sync now, open the Drive folder, campaign events.
- **Settings** — Drive mode (folder / api / off), reduced motion.

### The wizard (SRS §4.2) — one screen per stage

Overview → Safety plan (if any) → Equipment & calibration → Preconditions
(data stays locked until every box is ticked) → **Step 1 … N** (the
instruction in large type + only that step's fields, with **⇩ from DUT**
next to any field the connected machine can supply, a per-step timer,
*Redline this step*, *Attach file…*) → **Verdict** (all values, the pass
criteria, Evaluate / Finish / Waive / Reject, optional witness) → Done
(result + what to do next). Back/Next with animated transitions; every
Next saves, so closing the app and reopening resumes at the same stage.
FAIL opens an NCR automatically; BLOCKED (missing value or a threshold that
is still `null` in the catalog) is never reported as PASS.

Every commit is exported and pushed to Drive in the background; the pill
in the header shows the last sync and how many items are queued if Drive is
unreachable. Nothing is ever lost — it is committed locally first.

Compliance against the SRS: [docs/SRS-compliance.md](docs/SRS-compliance.md).
Requirements of this tool itself (progress, 5-machine comparison, applicability rules ALL / SINGLE / SUBSET, NASA discipline, simulation): [docs/SRS-DVT-Tool.md](docs/SRS-DVT-Tool.md).

### Applicability of a test (which machines)

```yaml
applicability: {rule: ALL}                              # every UUT
applicability: {rule: SINGLE, unit: UUT-05}             # one named UUT (+ sample_rationale)
applicability: {rule: SUBSET, units: [UUT-01, UUT-03, UUT-05]}   # a defined subset (+ sample_rationale = the criterion)
```

The **Statistics** page shows the tests × 5 machines verdict matrix (N/A
where a test does not apply) and, per test and numeric field, one curve per
unit; the **Dashboard** shows the campaign %, a progress bar per subsystem
and the list of what is still owed with estimated bench time.

### Campaign document — everything in one PDF (SRS-DVT-197)

Reports → **Campaign document (PDF)** writes `sCure-DVT.document.pdf` (and the
`.html` it was printed from) into the export folder — so the next sync puts it
on Drive — and opens it. In the console's language (Hebrew is RTL; test ids,
field names and criteria stay LTR): cover and counts, contents, units, phases
with gates and bench order, thresholds (CONFIRM where still null), campaign
status (progress, verdict matrix, NCRs, waivers, temperature by component),
then every test in bench order with its process figure, purpose, safety plan,
sweep / cases, equipment, preconditions, procedure and the fields each step
records, data fields, pass criteria, the CONFIRM lines from the catalog and the
runs recorded so far, and finally every open CONFIRM decision. From the shell:
`python -m dvt_tool.docgen --lang he`. The PDF needs Chrome or Edge on the
PC (headless print); without one the HTML is written and opened instead.

### Bench order — same instrument, one test after the other (SRS-DVT-196)

Each `equipment` entry is reduced to an instrument (PicoLog TC-08, Ophir
StarBright, O2 analyser, AC source, thermal camera, …; spare fuses, shorting
links and break-out leads are not instruments). Inside a phase the tests are
ordered so the ones sharing an instrument set run consecutively: from the
first test of the phase, the next is always the runnable test that keeps the
most of what is already on the bench (ties by catalog order); dependencies
and the §4 rules always win. Test Plans shows each phase as **🔧 instrument
groups**; the Test Console's *Next action* follows the same order, prefers
the test that keeps the instruments of the unit's last finished test, and
says what stays, what to add and what to remove. Logic in
`dvt_tool/bench.py` (`INSTRUMENT_RULES` maps equipment names to instruments).

### Temperature by component — which machine, which component (SRS-DVT-195)

Every temperature recorded in any test (°C fields, sweep values included) is
grouped by the component it measures — LED panel right / left / back / door,
heater body, chamber, ambient — and summarised **per machine** (n, mean, std,
min, max) and **across machines** (spread of the means, between-machine std).
A machine whose mean sits further from the median of the machines than 3× the
scaled MAD, 2× the pooled within-machine std and 2 °C (whichever is largest)
is flagged as an **outlier** in red.
Statistics → *Temperature by component*: pick a component, click a row, read
the mean ± std chart. The same numbers go to Drive with every sync:
`temperature_by_component.csv`, the `TempStats` sheet of the workbook, a
section in the report, and `charts/temp_<component>.png` (mean ± std per
machine). Reports → *Temperature graphs →* jumps there. Logic in
`dvt_tool/tempstats.py`; a field can force its component with `component:`
in the catalog.

### Adding a system test

Append an entry to `catalog/DVT_test_catalog.yaml` (copy the closest
existing test), assign it to a phase in the `phases:` list, and restart the
app — the run set, the wizard order and the exports follow automatically.
`Catalog.load()` refuses a catalog with an unknown dependency, a step that
captures an undeclared field, an enum without values, an enum value YAML
reads as a boolean (quote `'on'` / `'off'`), or a test not in any phase.
`pytest` in this folder runs the same validation. After a catalog change run
`python web/build_dvt_web.py` so the web page below follows.

## Web page - `web/dvt-tool.html`

A single page in the style of the QA tool, for running the campaign from any
browser without installing the console: double-click `web/dvt-tool.html`.
Pick the unit and type the operator; the phases list the tests that unit
owes, each test shows its purpose, safety plan, equipment, preconditions and
steps, and every run (sweep row / case x repetition) takes the step values.
The pass criteria are judged live with the console's rules (PASS / FAIL /
BLOCKED, `web/dvt-criteria.js`, checked against `dvt_tool/criteria.py` by
`tests/test_dvt_web.py`); *Record verdict* stores it with the operator and the
time. Tests whose step is automatic on the machine get a *Run on the machine*
button instead of value entry: for DVT-OPT-001 / 002 the page checks the
StarBright on the machine's USB, sets it to the test wavelength, runs the sweep
on the machine (`/api/dvt/uv-sweep`, sCureBox 1.0.34 or the Python machine
software), fills every value, locks them and draws the graph - the operator
only records the verdict.

The page finds the machine by itself: for the selected unit it tries the address that worked last
(name and IP), `scurebox.local`, then scans the known networks for the machine's serial (eMMC). Each
unit is paired with its machine's serial, so with five units on one network the page connects only to
the right one and warns when the machine it reached belongs to another unit; pressing *Connect* (or
choosing from the list shown when several machines answer) re-pairs it.

Every result is written to a **results folder** on the PC (*Choose results folder*, Chrome / Edge;
recording is refused until one is chosen, and the page asks again after a browser restart):

    runs.csv        one row per run - unit, test, variant, repetition, verdict, operator, times, note
    values.csv      one row per value (long format) - field, value, unit, type, source machine | manual
    journal.jsonl   every record / reopen / automatic measurement, append-only
    runs/<unit>/<test>/<variant>_r<n>.json          the full run
    sweeps/<unit>/<test>/<variant>_r<n>_<time>.csv  raw samples of an automatic measurement
    reports/        reports saved from *Export report*

The folder is the record, not the browser: choosing it on another PC reads `runs/` back, and a
newer run wins. `runs.csv` / `values.csv` open in Excel (UTF-8 with BOM) or pandas as they are.
*Export report* gives a text report per unit. English /
Hebrew from the catalog and its overlay. `web/dvt-catalog.js` is generated -
never edit it by hand.

## Google Drive

**Current setup (this PC):** Google Drive for Desktop is installed and the
app is configured in `folder` mode — every export is written to
`G:\My Drive\sCure DVT\` and Drive uploads it within seconds
(`sCure-DVT.xlsx`, `sCure-DVT.report.md`, `sCure-DVT.campaign.json`,
`csv\<test>.csv`, `attachments\…`). Start the app with `run.bat`.

Alternative — a station **without** Drive for Desktop — use the **Drive API
with your own Google account** (Drive settings → `api`):

1. Google Cloud Console → create a project → enable **Google Drive API** →
   *Credentials* → *OAuth client ID* → application type **Desktop app** →
   download the JSON.
2. In the app: **Drive settings** → `api` → select that `credentials.json`.
3. The first sync opens the browser once for consent (scope `drive.file`:
   the app sees only the files it created). A `token.json` is cached in
   `~/.scure-dvt`.
4. A folder named after the campaign (`sCure-DVT`) is created in *My Drive*
   and mirrored: `sCure-DVT.xlsx` (Summary + one sheet per test + NCR),
   `sCure-DVT.report.md`, `sCure-DVT.campaign.json`, `csv/<test>.csv`,
   `attachments/<run>/…`. Each sync overwrites the previous version of a
   file, so Drive always shows the current state (Drive keeps file history).

If you later install Google Drive for Desktop, switch to `folder` mode and
point it at `G:\My Drive\sCure DVT` — no API setup needed.

## Tests

```powershell
..\.venv\Scripts\python -m pytest DVT\tests -q
```

### Process figures

Every test has a schematic on the wizard's overview page and on each of
its steps: a top view of the chamber (four LED panels with thermistors and
fans, the heater with its control NTC and the TC-08 thermocouple bond, the
thermal cutout, circulation and intake fans, door with sensor and lock), the
mains chain (inlet, 15 A inlet fuse, voltage selector, 5 A heater fuse,
SSRs, LED drivers, PSU, CM5 with its heartbeat) and the bench instruments
the test uses. Colours: orange = what this step is about, warm = energised,
grey = de-energised, red = the injected fault, blue = instrument, green =
restored. The figures are generated from `dvt_tool/figures.py` — a test is
a list of elements and states plus per-step overrides — so all of them share
one machine and one legend, and the pytest suite refuses a catalog test
without a figure. `python -m dvt_tool.figures --out docs/figures [--steps]
[--lang he]` exports them as SVG (`docs/figures/` holds the per-test set).

### Instruments page — every external device once

The Instruments page lists the external devices the campaign needs, one
row each: the catalog's different wordings of the same device ("PicoLog
TC-08 thermocouple logger", "PicoLog TC-08 x2 …") are grouped by
`bench.instrument_key`, the row shows which tests use it and all its catalog
wordings, and one calibration record covers all of them (it is written
under the device name and under every wording, which is what the wizard and
the blockers look up). Fixtures, consumables, accessories and access notes
(spare fuses, sensor fixtures, break-out leads, indicators, stopwatch, the
machine's own tachometer readback…) are listed apart and never need a
calibration record, so they never block a run.

### Test Console — pick a test

The console follows the guided order (next action per unit), and next to
it a **Pick a test** card lists every catalog test: choose one, and *Run
this test on the selected unit* opens its IN_PROGRESS run (resume) or its
first NOT_STARTED run. Blockers (phase gates, earth first, dependencies,
calibration) are shown, not hidden — the button turns into *Run anyway
(supervisor)* and asks for a recorded reason. *Open the selected run* does
the same for the run highlighted in the table (a specific variant or
repetition). `--open TEST_ID` preselects a test at start-up.

### Test Console — restart a unit / erase (danger zone)

**Restart this unit and erase its data…** acts on the selected UUT: after
*Are you sure? This cannot be undone* and a required reason, every run of
that unit goes back to NOT_STARTED and its values, verdicts, redlines,
NCRs, waivers, attachments and phase sign-offs are erased, its
configuration un-frozen. The operation is journaled, so every other
console applies the same erase; other units are untouched. The reason is
kept in the events log and in `reset_log.jsonl`.

**Restart DVT and erase all data…** asks *Are you sure? This cannot be
undone*, requires a reason and an acknowledgement, then erases the campaign
on this console (campaign.db, exports, journal) and in the shared folder
(every console's journal, attachments, csv/charts, the campaign exports),
writes `reset.json` + a line in `reset_log.jsonl` (shared and local — the
reason is the only thing kept) and restarts the console empty. Console
settings (language, machine, operator) survive. Events written before the
reset are never replayed again, so a stale console pushing its old journal
changes nothing; such a console is told about the reset at start-up and
offered to erase its local data too.

### UV irradiance vs commanded power — StarBright on the machine (DVT-OPT-001 / 002)

For these two tests the StarBright is plugged into the **machine's** USB
port, not the console PC: the Flask server on the Pi talks to it over
pyusb (`server/starbright_usb.py`) and runs the sweep itself
(`server/uv_sweep.py`: `GET /api/dvt/meter`, `POST /api/dvt/uv-sweep`,
`GET /api/dvt/uv-sweep`, `POST /api/dvt/uv-sweep/abort`). The wizard step
The test is three things: the connection checklist (the Preconditions
stage), the schematic of the set-up (the process figure) and one automatic
step — **Run the UV sweep** runs inline on it (progress, abort button and
result on the step page; when it finishes every value, the CSV log and the
graph are recorded by themselves and the wizard moves on — nothing is typed
in, nothing attached by hand). It first checks the meter through the
machine and shows the wavelength it is *set* to; the sweep refuses to
start unless that equals the test's wavelength (405 nm for OPT-001, 450 nm
for OPT-002). The StarBright needs no calibration certificate for these two
tests: on the Equipment stage the wizard asks the machine whether the meter
is connected and delivering a reading, shows the result live, and locks
Next until it is (catalog `verify: live_meter`; the fixture is `verify:
none`). Then: dark reading, 30 → 100 % in 10 % steps, 10 s each (fixed, not
editable on the step),
meter at 5 Hz, value per step = mean of its last 5 s, LEDs off. The console
draws measured irradiance against the command with a linear fit, fills
the fields (per-step irradiance, slope, intercept, R², max deviation,
gain at 30 / 100 %, monotonic) and attaches the CSV + PNG. In simulation
mode the same flow runs against a simulated meter.

### Bench instruments — Ophir StarBright (DVT-SAF-012, DVT-SAF-007)

Step 2 of DVT-SAF-012 has a **Measure with the Ophir meter…** button. The
console switches the LEDs on at maximum, waits for a stable reading on the
meter, opens the door (API release, or you on the prompt), records the
irradiance against time until the UV is gone, switches the LEDs off, and
attaches the CSV and the irradiance-vs-time graph to the run. `uv_off_time`
is the door-open instant to the reading falling below 10 % of the plateau
(pass: ≤ 1 s). Meter backends: **StarLab USB** (Ophir's COM object — needs
StarLab installed and `pip install pywin32`), **serial** (RS-232 / USB-serial,
`pyserial`), or the **simulated meter** for rehearsal in simulation mode.
The backend, port, unit and aperture are remembered in the campaign store.

Step 3 of DVT-SAF-007 uses the same button with the **LED-thermistor
trigger**: LEDs on at maximum, stable reading, then the console prompts you
to pull the connector of the selected thermistor (right / left / back /
door — in simulation the open-thermistor fault is injected for you) and
records the decay. The trigger instant is the first machine poll where that
LED's reading is null, or your marker press; `led_off_time` is that instant
to the reading falling below 10 % of the plateau (pass: ≤ 2 s). The dialog
also fills `sensor_position`, `alarm_raised`, `error_code` and
`alarm_identifies_sensor` (the alarm text names the position). The catalog
step key `tool: led_off_timing` selects this trigger (`uv_off_timing` = door).

### Screen size

The console is laid out for 1500 x 920 logical pixels. On a smaller work
area (a 1920 x 1080 laptop at 150 % Windows scaling has only 1280 x 688) it
opens maximised in a compact layout (narrower rail, short title) and every
page scrolls vertically, so nothing is cut off. Dialogs are clamped to the
screen as well (`dvt_tool/ui/screen.py`).

### Process figures

Every test carries a generated engineering sheet (`dvt_tool/figures.py`,
exported to `docs/figures/`): header with the test id, title and step, the
top-view schematic with component tags (F1/F2 fuses, K1/K2 SSRs, E1 heater,
M1-M7 fans, RT1-RT6 thermistors, TC1/TC2 thermocouples, SV1 N2 valve,
QE1/QE2 O2 probes, H1-H4 LED panels, A1 controller, G1 PSU, X1 inlet, HMI),
and an ISO 7200-style title block with the catalog revision, date, legend
and tag key. The drawing is English in every console language by design;
only the card title is translated. Re-export with
`python -m dvt_tool.figures` (add `--steps` for one sheet per step).

### Several people at once — the campaign lives in the Google Drive folder

No server. Settings → Google Drive sync → mode `folder` pointing at the folder
Google Drive for Desktop synchronises (e.g. `G:\My Drive\sCure DVT`), shared
with every team member. Each console keeps its own local `campaign.db` and:

- appends every write it makes to **its own** journal file
  `<folder>/journal/<console-id>.jsonl` — one writer per file, so Drive never
  has to merge anything;
- replays the other consoles' journals into its local database every 15 s
  (and after each of its own writes), so every dashboard shows the whole team;
- copies attachments into `<folder>/attachments/<run>/`.

A run belongs to whoever started it first; a later claim from another
console is reported as a conflict and overridden, the same on every console.
Machine address, language, meter and SSH settings stay local. A new PC
bootstraps the whole campaign simply by opening the console on that folder.
Exports (XLSX, report, document) are regenerated by any console from the
merged state. Everyone must run the same catalog version (Git).

### Git checkpoints — the controlled history

Live team work stays in the Drive folder; Git keeps the reviewed history.
Reports → **Save checkpoint to Git…** (or automatically when a phase gate
is signed) exports the campaign and commits a snapshot under
`DVT/checkpoints/<campaign>/<YYYYMMDD-HHMM>_<label>/` — the campaign JSON,
the workbook, the report and a `CHECKPOINT.md` with who / when / progress per
machine — as one commit, pushed when a remote is configured. Only that folder
is committed; other changes in the working tree are untouched.

### Automatic tests — the console drives the machine

Some catalog steps carry a `tool:` key and the wizard shows a button that runs
them without operator action: `uv_off_timing` / `led_off_timing` (Ophir
StarBright: LEDs at maximum, trigger, irradiance vs time) and `led_fan_sweep`
(DVT-THM-005: LED-cooling fans at 100 / 90 / 80 / 70 %, LEDs at maximum, every
panel left to settle or stopped at the 75 °C limit). The console sends the
commands, watches the machine's own sensors, ends safe (LEDs off, fans 100 %),
hands the operator the final answer — the lowest duty with margin — and the
graph, fills the fields of every duty row of the unit and commits the rows the
wizard is not on.
