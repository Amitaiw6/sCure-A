# Software Requirements Specification — sCure DVT Test Console

**Document:** SRS-DVT-TOOL, Rev 1 (draft for review) · **Date:** 2026-08-31
**System under test:** sCure / CureBox (UV post-cure unit), 5 units under test (UUT-01 … UUT-05)
**Companion documents:** `DVT_Verification_Plan_SRS_RevB.md` (the campaign plan; its SRS-DVT-08x/09x/1xx requirements are inherited here), `DVT_test_catalog.yaml` (the machine-readable test catalog), `SRS-compliance.md` (implementation status).

This document specifies the **software that runs the DVT campaign** — the test console the engineer uses to select a machine, be guided through every test, capture data, judge results and see the progress of the whole project across all machines. It is written so that the test list and the procedure of each test (which the author will supply next) plug in as catalog entries without changing the software.

---

## 1. Scope and goals

| Goal | What it means for the software |
|---|---|
| **One source of truth** | Tests, procedures, data, verdicts, anomalies, waivers and reports live in one application and one campaign database. No side spreadsheets. |
| **Project progress is always visible** | At any moment: % of the campaign completed, % per subsystem, which tests remain (and roughly how many bench hours), which unit is where. |
| **Five machines, one campaign** | The operator chooses the unit at the start of a session; the software derives what that unit owes; at the end (and at any time) the results of all five are compared side by side per test. |
| **Applicability by criterion** | Some tests run on every unit, some on exactly one, some on a defined subset (e.g. 3 units) — each with a written sample-size rationale. The run set follows from the catalog; the operator never decides it. |
| **NASA verification discipline** | Method classification, frozen success criteria, readiness reviews, configuration control, as-run records, anomaly closure, traceability and a closure report per NPR 7123.1D / NASA-SP-2016-6105. |
| **Everything talks to everything** | Catalog → run set → wizard → data → verdict → NCR → progress → dashboard → comparison → report → Drive. A change in one place is reflected everywhere. |

Out of scope: the electrical/thermal **limits** themselves (they come from IEC/EN 62368-1 and the design), and any control of the machine beyond what a test step needs.

---

## 2. Definitions

| Term | Meaning |
|---|---|
| **Test** | One catalog entry (`DVT-xxx-nnn`): purpose, method, applicability, equipment, preconditions, procedure steps, data fields, pass criteria. |
| **Run** | One executable instance: test × unit × variant (sweep row / case) × repetition. The unit of progress. |
| **Applicability rule** | `ALL` (every UUT), `SINGLE` (one named UUT), `SUBSET` (a named list of UUTs, e.g. 3) — with `sample_rationale` for anything less than ALL. |
| **Verdict** | Per run: PASS / FAIL / BLOCKED / WAIVED. Rolled up per test and per test × unit. |
| **Phase** | Ordered group of tests with an entry gate (TRR) and an exit gate. |
| **DUT** | The machine currently connected to the console (a real unit by address, or the built-in simulator). |

---

## 3. Users

| Role | Uses the software for |
|---|---|
| Test engineer / operator | Selects the unit, runs the wizard, records data, attaches logs. |
| Test lead | Signs readiness reviews, approves waivers, dispositions NCRs, reads progress and comparisons. |
| Quality / witness | Optional witness signature on safety-critical and destructive phases (decision pending). |
| Reviewer (offline) | Reads the exports on Google Drive (XLSX, report) without the application. |

---

## 4. Functional requirements

Identifiers continue the Rev B numbering. Each requirement has a verification method (T = test, D = demonstration, I = inspection).

### 4.1 Campaign definition (catalog)

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-120** | The software shall load the campaign from the test catalog (`DVT_test_catalog.yaml`) and refuse a catalog with structural errors (unknown dependency, step capturing an undeclared field, enum without values, test not assigned to a phase, SINGLE/SUBSET without sample rationale, SUBSET naming an unknown unit). | T |
| **SRS-DVT-121** | Each test shall declare `applicability.rule` ∈ {ALL, SINGLE, SUBSET}; SINGLE names one unit, SUBSET names the list of units and the **criterion** that selected them (in `sample_rationale`). | T |
| **SRS-DVT-122** | The software shall derive the complete run set (tests × applicable units × sweep/case variants × repetitions) from the catalog; the operator shall never be asked which runs a unit owes. | T |
| **SRS-DVT-123** | Adding a test to the catalog shall require no software change: the run set, the wizard, the progress figures, the comparison and the exports shall follow automatically after restart/reload. | D |
| **SRS-DVT-124** | Each test shall carry `method` ∈ {Test, Analysis, Inspection, Demonstration}, `requirement_ids` (VCRM links) and `pass_criteria` as a machine-evaluable expression; catalog thresholds may be referenced by name (e.g. `led_temperature_thresholds.working_limit`). | I |
| **SRS-DVT-125** | The catalog version shall be stamped on every run; changing `pass_criteria` of a baselined test shall require a catalog version increment (guarded by review; the software records which version each run was judged against). | I |

### 4.2 Machine (DUT) selection and connection

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-130** | At the start of a session the operator shall select (a) the **unit under test** (UUT-01 … UUT-05) and (b) the **machine address** to connect to (IP/hostname, remembered list, discovery), or the built-in **simulator**. Both selections shall be visible at all times in the header. | D |
| **SRS-DVT-131** | The software shall show the live state of the connected machine (chamber temperature, LED back-face temperatures, fan RPM, door, UV, heater, active fault/alarm code) and a SYSTEM STATUS indicator (OFFLINE / IDLE / HEATING / COOLING / CURING / FAULT). | D |
| **SRS-DVT-132** | During a run, any data field that maps to a live machine value shall offer a one-click capture ("from DUT"); captured values shall be marked as machine-sourced and the capture logged. | T |
| **SRS-DVT-133** | The software shall provide confirmed, logged controls to bring the machine to a step's required state (heat to target, cool at a rate, UV on/off, open door, stop, diagnostics). Controls shall be disabled when no machine is connected. | D |
| **SRS-DVT-134** | A **simulation mode** shall provide a simulated machine with the same interface (state, controls) and coarse physics, plus **fault injection** (door open, heater sensor open/short, LED thermistor open, LED fan disconnected/blocked, circulation fan loss, chamber fan loss, mains dropout, thermal cutout, mains voltage 110/230/240) so that every protective-function test can be rehearsed without hardware. Simulation shall be unmistakably indicated (banner, status prefix) and recorded on every run made in it. | T |

### 4.3 Guided execution (inherits SRS-DVT-080 … 088)

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-140** | For the selected unit the software shall present exactly one **next action**, derived from phase order, gates, dependencies and status, with the blocking reasons when it cannot start and a direct action to clear each (freeze configuration, sign readiness, record calibration, go to the prerequisite test). | D |
| **SRS-DVT-141** | A run shall be executed as a **wizard with one screen per stage**: Overview → Safety plan (if defined) → Equipment & calibration → Preconditions → Step 1 … N → Verdict → Done. Each stage states what to do; Next is refused until the stage's conditions are met. | D |
| **SRS-DVT-142** | Each procedure step screen shall show only that step's instruction and its data fields, validate type and plausible range on Next, and save on Next so that a restart resumes at the same stage (SRS-DVT-088). | T |
| **SRS-DVT-143** | The wizard shall show elapsed time of the current step, allow a redline (as-run deviation with reason) and file attachments at any step, and show the connected machine's state alongside. | D |
| **SRS-DVT-144** | On Finish the software shall evaluate the pass criteria automatically and commit PASS / FAIL / **BLOCKED** (a referenced value missing or a catalog threshold still undefined — never silently PASS); FAIL shall open an NCR automatically. | T |

### 4.4 Progress and status — the project view

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-150** | The software shall show the **campaign completion percentage** = committed runs / applicable runs (rejected runs excluded, supplementary runs excluded), with the absolute numbers. | T |
| **SRS-DVT-151** | The software shall show a **progress bar per subsystem** (Safety, Thermal, Electrical, Environmental, …) with its percentage and runs done/total, and per-subsystem counts of tests Complete / Running / Failed / Blocked / Pending. | D |
| **SRS-DVT-152** | The software shall list **what is left**: every test that still owes runs, with pending runs per unit and the estimated remaining bench time (Σ pending runs × `duration_est_min`). Selecting an entry shall open that test. | D |
| **SRS-DVT-153** | The software shall show per unit: current phase, runs done / owed, and open NCRs; and a campaign health indicator (nominal / blocked / failed). | D |
| **SRS-DVT-154** | A test's status shall be derived as: Failed if any run FAIL; else Running if a run is in progress; else Complete if every applicable run is committed; else Blocked if a BLOCKED verdict exists; else Pending. Its rolled-up result shall be FAIL > BLOCKED > WAIVED > PASS across its runs (SRS-DVT-096). | T |

### 4.5 Comparison across the five machines

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-160** | The software shall show a **verdict matrix** — tests as rows, the five units as columns — with the rolled-up verdict of each test on each unit, progress (done/owed) where not yet judged, and N/A where the test does not apply to that unit. | D |
| **SRS-DVT-161** | For any test and any numeric data field the software shall plot the values of all units against the sweep value (or repetition), one curve per unit, with the pass limit drawn when it can be read from the criteria (SRS-DVT-095), and the same numbers as a table. | D |
| **SRS-DVT-162** | The comparison shall be available at any time during the campaign, not only at the end, and shall be included in the exported workbook (Summary + per-test sheets with unit and variant columns). | I |

### 4.6 Verification discipline (NASA framework)

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-170** | Phases shall be gated: a phase opens for a unit only when the previous phase is closed for that unit; a **Test Readiness Review** checklist shall be signed (name, time) before the first run of a phase. | T |
| **SRS-DVT-171** | The software shall enforce the campaign's ordering rules from the plan: protective-earth bonding before any powered test; destructive tests last (a unit that went through them owes nothing further); hipot once per unit. | T |
| **SRS-DVT-172** | The unit configuration shall be recorded and **frozen** before Phase 1; the freeze (who, when, serial) shall be part of every export. | T |
| **SRS-DVT-173** | Every instrument named by a test shall have a calibration record valid on the run date; otherwise the run is blocked (override only by a logged supervisor action). | T |
| **SRS-DVT-174** | Success criteria shall be evaluated by the software from the frozen catalog expression, never typed by the operator. | T |
| **SRS-DVT-175** | Every FAIL shall create an NCR; NCRs shall be dispositioned and closed with name and text; open NCRs shall be visible on the console and counted in the health indicator. | T |
| **SRS-DVT-176** | Waivers shall require approver identity and rationale and shall be reported separately from PASS everywhere. | T |
| **SRS-DVT-177** | Redlines (as-run deviations) shall be reproduced in the report per run and step. | T |
| **SRS-DVT-178** | The closure report shall list requirements/tests **not verified**, all NCRs with dispositions, all waivers, and the configuration and calibration records — the report cannot claim completion while the unverified list is non-empty. | I |
| **SRS-DVT-179** | Every operator action that changes state (start, values, finish, waive, reject, redline, TRR sign-off, calibration, DUT control, blocker override) shall be logged with timestamp, actor and run id. | T |

### 4.7 Data, export and cloud

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-180** | All campaign data shall be committed locally first (single database); exports shall be regenerated after every commit: JSON snapshot, per-test CSV, one XLSX workbook (Summary, per-test sheets, NCR), Markdown report. | T |
| **SRS-DVT-181** | Exports shall be synchronised automatically to the engineer's Google Drive (Drive-for-Desktop folder or Drive API with the engineer's account); the mode, last sync time and queued items shall be visible; a sync failure shall never block or lose a result. | T |
| **SRS-DVT-182** | A self-contained campaign archive (database, attachments, catalog file, exports) shall be producible on demand for backup and for merging results from a second station. | D |

### 4.8 Usability

| ID | Requirement | V |
|---|---|---|
| **SRS-DVT-190** | One visual language across all screens (typography, cards, colours); state is encoded consistently: green = PASS/OK, red = FAIL/fault, amber = running/blocked/warning, purple = waived/simulation, grey = pending/offline. | I |
| **SRS-DVT-191** | Primary actions shall be reachable in one click from the screen where the operator is; a disabled primary action shall always show why and how to clear it. | D |
| **SRS-DVT-192** | Transitions between wizard stages shall be animated to make the step change obvious; a reduced-motion setting shall disable animations. | D |
| **SRS-DVT-193** | The application shall be usable on a 1366×768 laptop and scale up to a 4K monitor; tables and matrices scroll within their cards, never the whole window horizontally. | D |

---

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| **NFR-1** | Local-first: full function without network; Drive sync is best-effort and retried. |
| **NFR-2** | A run's data is durable the moment Next/Finish is pressed (write-ahead: committed before the UI advances). |
| **NFR-3** | UI responsiveness: no blocking network or export work on the UI thread (background workers, per-thread database connections). |
| **NFR-4** | Start-up in < 3 s with a 500-run campaign; dashboard refresh < 300 ms. |
| **NFR-5** | Runs on Windows 10/11 (primary) and Linux; Python 3.11+, PySide6; no admin rights required. |
| **NFR-6** | Machine control actions are confirmed, logged and refused when offline; the simulator is never confused with a real unit (banner + status prefix + `simulated` flag on runs). |

---

## 6. Interfaces

| Interface | Description |
|---|---|
| Catalog | `DVT_test_catalog.yaml` — schema in the plan, Appendix A; validated on load. |
| Machine | sCure hardware service HTTP API (`/api/state`, `/api/cure/heat`, `/api/cure/cool`, `/api/cure/stop`, `/api/uv`, `/api/door/open`, `/api/fans/<name>`, `/api/diagnostics/*`). |
| Simulator | In-process, same interface + `inject(fault, on)`, `set_mains(v)`, `ack()`. |
| Google Drive | Drive-for-Desktop folder (`G:\My Drive\sCure DVT`) or Drive API v3 (OAuth, scope `drive.file`). |
| Exports | `sCure-DVT.xlsx`, `sCure-DVT.report.md`, `sCure-DVT.campaign.json`, `csv/<test>.csv`, `attachments/<run>/…`. |

---

## 7. Traceability to the NASA verification framework

| NASA expectation (NPR 7123.1D / SP-2016-6105) | Requirement(s) |
|---|---|
| Verification method classified | 124 |
| Success criteria frozen before execution | 124, 125, 174 |
| Bidirectional traceability (VCRM) | 124 (requirement_ids), 178 |
| Sample-size rationale when not on all articles | 121 |
| Test article configuration controlled | 172 |
| Readiness review before each phase | 170 |
| As-run procedure with redlines | 143, 177 |
| Anomalies identified, dispositioned, closed | 144, 175 |
| Waivers formally approved | 176 |
| Independent witnessing (decision pending) | 4.3 witness field; enforcement TBD |
| Measurement equipment calibrated and traceable | 173 |
| Closure report with unverified list | 178 |

---

## 8. How the author's test list plugs in

For every test the author will provide: title, subsystem, purpose, **applicability** (all / one unit / which units and why), method, equipment, preconditions, the procedure steps and what is recorded at each step, the data fields with units and plausible ranges, the pass criteria, repetitions, estimated duration, dependencies, and (if applicable) sweep values or a case matrix. Each becomes one entry in `DVT_test_catalog.yaml`; the software does the rest (SRS-DVT-123).

---

## 9. Acceptance

The tool is accepted when, with the full test list loaded: the run set matches the plan's count; an operator can select a unit and be walked through a complete run in the wizard on the simulator with a fault injected and see the expected FAIL + NCR; the dashboard shows the campaign %, per-subsystem bars and the remaining list changing after each committed run; the five-unit matrix shows N/A / progress / verdict correctly for ALL, SINGLE and SUBSET tests; the XLSX and report on Drive match the application; and every requirement in §4 marked T passes its automated test.
