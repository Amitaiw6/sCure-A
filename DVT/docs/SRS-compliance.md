# SRS-DVT-SW Rev B — compliance review of `dvt_tool`

Reviewed 2026-08-31 against `DVT/docs/DVT_Verification_Plan_SRS_RevB.md` (Rev B requirements; Rev A items
SRS-DVT-001…075 are referenced by Rev B but the Rev A text is **not in this repository** — see "Open" below).

Legend: **Met** — implemented and exercised by a test or the smoke run · **Partial** — implemented with a stated gap ·
**Open** — not implemented / needs a decision.

## 5.1 Guided execution

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-080 | Single "next action" per unit from phase order + dependency graph + status | **Met** | `Engine.next_action` — Test Console "Next action" card; `tests/test_dvt_tool.py::test_wizard_gates_and_next_action` |
| SRS-DVT-081 | Readiness checklist per phase, signed before any test in the phase (TRR) | **Met** | `Store.sign_phase`, blocker `TRR` in `Engine.blockers_for`; Console → *Sign phase TRR* |
| SRS-DVT-082 | Blocked test visible but not startable, blocking reason shown | **Met** | Console: run visible in the runs table, *Start* disabled, red "Blocked:" list; supervisor override is a separate, logged action |
| SRS-DVT-083 | Preconditions as an explicit checklist before the first data field unlocks | **Met** | Wizard stage *Preconditions*: Next refuses until every box is ticked; data steps come after |
| SRS-DVT-084 | Safety-critical steps need explicit confirmation and show `safety_plan` first | **Met** | Wizard stage *Safety plan* (tests with `safety_plan` / `safety_critical`), checkbox required; *Finish* re-checks it |
| SRS-DVT-085 | Every instrument in `equipment` must have a calibration record valid on the run date, else block | **Met** | Blocker `CAL` (date compared to today); wizard *Equipment* stage; *Instruments* page to record; override is logged |
| SRS-DVT-086 | Redline any step with reason; captured in the run record and reproduced in the report | **Partial** | Redlines stored (`Store.add_redline`), shown in the wizard and counted in CSV/XLSX. **Gap:** the Markdown report lists a redline *count* per run, not the as-run text — add per-run redline lines to `export_report_md` |
| SRS-DVT-087 | WAIVED requires approver + rationale; counted separately from PASS everywhere | **Met** | `Store.waive` raises without approver/rationale; roll-up order FAIL > BLOCKED > WAIVED > PASS; separate column in Summary/report/dashboard KPIs |
| SRS-DVT-088 | Progress survives restart; part-completed run resumes at the step where it stopped | **Met** | `runs.current_step` + values persisted on every Next; wizard `_resume_index`; smoke run: leave at step 4 → resume at step 4 |

## 5.2 Everything in one place

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-090 | Single store for catalog, UUTs, equipment/calibration, run data, attachments, redlines, NCRs, waivers, approvals, reports | **Met** | `campaign.db` (SQLite) + `export/` next to it; catalog version stamped on every run |
| SRS-DVT-091 | Attachments stored against the run, retrievable from the comparison view | **Partial** | Stored + synced to Drive under `attachments/<run>/`; listed in the JSON snapshot. **Gap:** no in-app comparison view yet (see 095) |
| SRS-DVT-092 | Single search across tests, units, error codes, NCR text | **Met** | `Store.search` — Console *Search* card (runs, values, NCRs) |
| SRS-DVT-093 | Self-contained campaign archive (DB, attachments, catalog version) for backup/merge | **Partial** | `campaign.json` snapshot + DB + attachments are all in `export/` and on Drive. **Gap:** no one-click `.zip` with the catalog file itself and no merge tool — add *Reports → Export archive* |

## 5.3 Parameter sweeps

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-094 | `sweep` parameter → run set = tests × units × sweep values | **Met** | `Catalog.runs` (matrix rows and case matrices); DVT-THM-001 = 10 × 5 = 50 runs (tested) |
| SRS-DVT-095 | Comparison view grouped by sweep parameter (curve per unit) | **Met** | *Statistics* page: per test and numeric field, x = sweep value / repetition, one curve per unit, pass limit drawn; plus the tests × machines verdict matrix and the temperature-by-component comparison (SRS-DVT-195 below) |
| SRS-DVT-096 | Verdict per sweep value + rolled-up verdict, PASS only if every value passes | **Met** | `Engine.test_verdict` (per test / per unit); dashboard "Result" column; `test_sweep_rollup_and_reject_rescinds_children` |

## 5.4 Co-executed runs

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-097 | `co_executed_with` presented as one continuous execution | **Partial** | `Catalog.parent_row_for` knows the pairing and the child is linked to its parent run (`Store.link_parent`). **Gap:** the wizard does not yet chain the DVT-THM-003 stages onto the end of the DVT-THM-001 row automatically — the operator starts DVT-THM-003 separately. Proposed: after a DVT-THM-001 80 °C row reaches *Verdict*, offer "Continue with DVT-THM-003 (fast) on the descent" and auto-link |
| SRS-DVT-098 | Both runs linked in both directions, own verdict / trace / column | **Met** (data) | `parent_run_id`; each run keeps its own verdict and row |
| SRS-DVT-099 | Rejecting a parent rescinds co-executed children with the reason | **Met** | `Store.reject_run` → children `REJECTED`, reason "parent rejected: …" (tested) |
| SRS-DVT-100 | Supplementary runs storable, retrievable, excluded from progress | **Met** (data) | `Store.add_supplementary` (`supplementary=1`, excluded from `Engine.progress`, included in exports). **Gap:** no UI button yet to record a supplementary descent from the wizard |

## 5.5 Cloud synchronisation

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-110 | Every saved run/NCR/waiver/redline exported automatically to Drive: DB snapshot, per-test CSV, XLSX, report | **Met** | `kick_sync` after every commit (Next, Finish, Waive, NCR, calibration, TRR); `Exporter.export_all`; configured folder `G:\My Drive\sCure DVT` |
| SRS-DVT-111 | Drive API with the engineer's account **or** a synced folder; mode + last sync visible | **Met** | `drive.py` (api / folder / off); header pill "Drive ✓ hh:mm:ss"; Settings page |
| SRS-DVT-112 | Sync failure never blocks or loses a run; queued and retried; queue length visible | **Met** | committed locally first; `sync_queue`; pill shows "N queued — error" (tested with a broken backend) |

## §4 execution-order rules

| Rule | Status | Where |
|---|---|---|
| Phases gated; next phase opens only when the previous is closed for that unit | **Met** | `Engine.phase_closed`, blocker `PHASE` |
| Earth before power (DVT-ELE-001 before every powered test) | **Met** | blocker `EARTH` |
| Destructive last (unit that went through Phase 5 is a different article) | **Met** | blocker `DESTRUCTIVE` |
| Hipot once (DVT-ELE-003 not repeated except after transport) | **Partial** | single repetition in the catalog; no explicit guard against a second *supplementary* hipot — add a rule if supplementary runs get a UI |
| Phase 0: configuration frozen and signed before anything | **Met** | `Store.freeze_config`, blocker `CONFIG` |

## §2 NASA-framework items the software carries

| # | Item | Status |
|---|---|---|
| 3 | Success criteria frozen | **Met** — `pass_criteria` evaluated from the catalog; catalog version stamped on runs |
| 5 | Sample-size rationale when < ALL | **Met** — `Catalog.validate` rejects SINGLE without `sample_rationale` |
| 6 | Configuration freeze per unit | **Met** (freeze); **Open**: "any change invalidates prior runs" is not enforced |
| 8 | As-run procedure with redlines | **Partial** — see 086 |
| 9 | NCR on every FAIL, dispositioned and closed | **Met** — auto-open on FAIL, close with disposition |
| 11 | Witness signature | **Partial** — optional witness field on the verdict page; not enforced for Phase 1/5 (decision pending, plan item 13) |
| 12 | Calibration traceability | **Met** — records + blocker; `calibration_id` in the catalog is still null everywhere (data, not software) |
| 14 | Closure report lists unverified requirements | **Met** — report section "Not yet verified" |

## SRS-DVT-Tool additions (Rev 1)

| Req | Requirement | Status | Where / evidence |
|---|---|---|---|
| SRS-DVT-194 | Whole console in the selected language, catalog prose included; identifiers untouched | **Met** | `Catalog.load(path, lang)` + `catalog/DVT_test_catalog.he.yaml` (all 29 tests, phases, roles, subsystems, methods); engine / wizard / dashboard messages via `i18n.trf`; `tests/test_dvt_tool.py::test_hebrew_overlay_covers_every_test_and_keeps_identifiers`, `::test_overlay_refuses_mismatch_and_unknown_tests`, `::test_engine_messages_follow_console_language`. Exports (XLSX / Markdown / CSV) use whatever language the console ran in. |
| SRS-DVT-195 | Temperature per component, per machine — mean / std / n, between-machine std, spread, outliers; exported as CSV + XLSX sheet + report section + PNG charts | **Met** | `dvt_tool/tempstats.py` (pure: `component_of`, `summarise`, `collect`, `component_summary`, `render_png`); *Statistics* page card "Temperature by component — machine comparison" (`ErrorBarChart`); `Exporter.export_temp_stats` → `temperature_by_component.csv`, `charts/temp_<component>.png`, sheet `TempStats`, report section; *Reports* → "Temperature graphs →"; `tests/test_dvt_tool.py::test_tempstats_component_mapping_and_outliers`, `::test_tempstats_collect_and_export` |
| SRS-DVT-196 | Bench order — tests using the same instrument run one after the other; next action keeps the current setup and says what changes; Test Plans grouped by instrument | **Met** | `dvt_tool/bench.py` (`instrument_key`, `instruments_of`, `bench_order`, `bench_groups`, `setup_change`); `Engine.next_action` (bench order + last-finished-test preference, `NextAction.setup`); Test Console shows the 🔧 setup line; Test Plans tree: phase → instrument group → tests; `tests/test_dvt_tool.py::test_bench_order_groups_instruments_and_respects_dependencies`, `::test_next_action_keeps_the_bench_setup` |
| SRS-DVT-197 | One campaign document (HTML → PDF) with everything: catalog in bench order with figures, thresholds, status, results, open CONFIRM items | **Met** | `dvt_tool/docgen.py` (`DocBuilder`, `confirm_items`, `find_browser`; `python -m dvt_tool.docgen --lang he`); Reports → *Campaign document (PDF)* writes `<campaign>.document.pdf` (+ `.html`) to the export folder and opens it; `tests/test_dvt_tool.py::test_campaign_document_html_and_pdf` |

## Open (need a decision or the missing input)

1. **Rev A requirements SRS-DVT-001…075** — the text is not in the repo; Rev B says they "stand unchanged". They cannot be checked until the Rev A document is added under `DVT/docs/`. (SRS-DVT-012 and -053 are referenced by Rev B and are implemented as described there.)
2. **VCRM** (`requirement_ids`) — only REQ-29 and REQ-48 are linked; the other 66 MVP requirements must be entered in the catalog before baseline (framework item 4).
3. **Catalog CONFIRM items** — DVT-ENV-001 unit (currently null → 0 runs), LED thresholds `warning` / `protective_shutdown` (DVT-SAF-015 evaluates as BLOCKED until set), DVT-SAF-016 detection means (per-panel current sense or light-sensor sequence — none exists today) and its `time_to_alarm` limit, all "CONFIRM" limits.
4. Comparison / statistics view (095) and archive export (093) — proposed above; not blocking execution.

Gaps marked **Partial** that are pure software (086 report redlines, 093 archive, 097 auto-chaining, 100 UI) are tracked as the next increments of `dvt_tool`.
