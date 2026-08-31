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

### How a session goes (SRS §4.2)

1. Pick the unit on the left. The centre panel says what to do next — or why
   nothing can start yet (configuration not frozen, phase TRR not signed,
   ELE-001 not passed, a dependency missing, an instrument without a valid
   calibration record). Nothing has to be worked out by the operator.
2. **Start this run** → safety plan (if any) → equipment/calibration status →
   preconditions checklist (steps unlock only when all are ticked) →
   step-by-step procedure with the data fields bound to each step.
3. **Save values** as you go (survives restart), **Evaluate** to see the
   verdict, **Finish run** to commit it. FAIL opens an NCR automatically.
   **Waive…** needs an approver + rationale and is counted separately from
   PASS. **Redline this step** records how a step was actually performed.
   **Reject run…** (ambient drift, warm start) also rescinds co-executed
   children.
4. Every commit is exported and pushed to Drive in the background; the pill
   at the top shows the last sync and how many items are queued if Drive is
   unreachable. Nothing is ever lost — it is committed locally first.

### Adding a system test

Append an entry to `catalog/DVT_test_catalog.yaml` (copy the closest
existing test), assign it to a phase in the `phases:` list, and restart the
app — the run set, the wizard order and the exports follow automatically.
`Catalog.load()` refuses a catalog with an unknown dependency, a step that
captures an undeclared field, an enum without values, or a test not in any
phase. `pytest` in this folder runs the same validation.

## Google Drive

Google Drive for Desktop is **not** installed on this PC, so the default mode
is the **Drive API with your own Google account**:

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
