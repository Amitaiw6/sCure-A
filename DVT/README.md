# sCure DVT — verification campaign folder + application

Everything for the Design Verification Test campaign lives here: the test
catalog (the single source of truth), the verification plan / SRS, and the
desktop application that runs the campaign and keeps your Google Drive
up to date.

```
DVT/
├── catalog/DVT_test_catalog.yaml     28 tests, 5 UUTs, phases + gates — ADD NEW SYSTEM TESTS HERE
├── docs/DVT_Verification_Plan_SRS_RevB.md
├── dvt_tool/                          the application
│   ├── app.py        desktop UI (PySide6)      python -m dvt_tool.app
│   ├── catalog.py    load/validate the YAML, expand tests × units × sweep/case × reps into runs
│   ├── criteria.py   safe evaluator of pass_criteria (PASS / FAIL / BLOCKED)
│   ├── store.py      SQLite campaign store: runs, values, redlines, NCRs, waivers, attachments, calibration, TRR sign-off
│   ├── engine.py     wizard: phase gates, "earth before power", dependencies, next action, rolled-up verdicts
│   ├── export.py     JSON snapshot + per-test CSV + XLSX workbook + Markdown report
│   └── drive.py      Google Drive sync (Drive API with your account, or a Drive-for-Desktop / OneDrive folder)
└── tests/            pytest
```

## Run the application

```powershell
cd C:\Users\User\Documents\GitHub\sCure-A\DVT
..\.venv\Scripts\python -m dvt_tool.app
```

Data lives in `%USERPROFILE%\.scure-dvt\` (`campaign.db`, `export\`, `sync.json`).

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

### Adding a system test

Append an entry to `catalog/DVT_test_catalog.yaml` (copy the closest
existing test), assign it to a phase in the `phases:` list, and restart the
app — the run set, the wizard order and the exports follow automatically.
`Catalog.load()` refuses a catalog with an unknown dependency, a step that
captures an undeclared field, an enum without values, or a test not in any
phase. `pytest` in this folder runs the same validation.

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
