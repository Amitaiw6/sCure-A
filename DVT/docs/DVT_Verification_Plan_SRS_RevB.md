# DVT Verification Plan & Test Software SRS

**Project:** sCure / CureBox DVT
**Document:** SRS-DVT-SW, Rev B
**Supersedes:** Rev A
**Author:** Amitai Walker
**Machine-readable catalog:** `../catalog/DVT_test_catalog.yaml` v0.24 — 42 tests, 528 applicable runs
**Implementation:** `../dvt_tool/` (desktop application; see `../README.md`)

---

## 1. Purpose

One application that holds the entire DVT campaign: the test definitions, the order in which they must be run, guided execution, the captured data, the anomaly log, the progress state and the final verification report. Nothing lives in a side spreadsheet.

The campaign covers **5 units under test (UUT)**. Test applicability is defined per test; the software derives which runs each unit owes and never asks the operator to work that out.

---

## 2. NASA Verification Framework — Compliance Status

The framework is NPR 7123.1D and NASA/SP-2016-6105. The electrical and safety **limits** come from IEC/EN 62368-1 — NASA has no standard for a commercial curing oven, and spaceflight environmental standards (GSFC-STD-7000 GEVS, NASA-STD-7001/7002) are written for launch loads and are not applicable here. What NASA supplies, and what this plan adopts, is the discipline around the tests.

| # | NASA expectation | Status | Where |
|---|---|---|---|
| 1 | Verification method classified as Test / Analysis / Inspection / Demonstration | **Met** | `method` field, mandatory |
| 2 | V&V plan baselined at PDR | **Met by this document** | Rev B is the baseline artifact |
| 3 | Success criteria defined and frozen before execution | **Met** | `pass_criteria` immutable once baselined; change requires version increment |
| 4 | Bidirectional traceability, requirement ↔ verification (VCRM) | **Gap** | `requirement_ids` is empty on most tests. Must be populated against the 68 MVP requirements before baseline |
| 5 | Sample-size rationale where verification is not on all articles | **Met** | `sample_rationale` mandatory when applicability < ALL |
| 6 | Test article configuration controlled and recorded | **Partial** | UUT registry exists; needs a configuration freeze per unit and a rule that any change invalidates prior runs |
| 7 | Verification event readiness review before each phase (TRR) | **Gap — added in Rev B** | §4 phase gates, SRS-DVT-081 |
| 8 | As-run procedure with redlines captured | **Gap — added in Rev B** | SRS-DVT-086 |
| 9 | Anomaly identified, dispositioned and closed | **Met** | NCR record on every FAIL |
| 10 | Waivers and deviations formally approved | **Partial** | WAIVED verdict exists; approver identity and rationale now mandatory, SRS-DVT-087 |
| 11 | Independent witnessing / quality assurance of the verification event | **Gap** | Decide whether DVT requires a witness signature. Recommended for the electrical safety and destructive phases |
| 12 | Measurement equipment calibrated and traceable | **Partial** | `calibration_id` field exists but is null throughout — populate before Phase 1 |
| 13 | Test-as-you-fly — verify in the operational configuration | **Met** | `preconditions` per test; deviations recorded as waivers |
| 14 | Verification closure report, with unverified requirements stated | **Met** | SRS-DVT-053 blocks report issue without the unverified list |

**Four things to close before you can call this compliant:** the VCRM links (#4), the readiness gates (#7, now specified), calibration records (#12), and a decision on witnessing (#11).

---

## 3. Test Catalog Summary

518 applicable runs, roughly 770 bench hours excluding transport transit.

| Phase | Tests | Runs |
|---|---|---|
| 0 — Incoming and configuration | inspection, config freeze | per unit |
| 1 — Electrical safety | DVT-ELE-001…DVT-ELE-005 | 40 |
| 2 — Protective functions | DVT-GAS-001…006, DVT-SAF-001…018 | 319 |
| 3 — Performance | DVT-THM-001…DVT-THM-003, DVT-THM-004, DVT-GAS-007, DVT-NFC-001, DVT-OPT-001, DVT-OPT-002 | 165 |
| 4 — Transport | DVT-ENV-001 | 1 |
| 5 — Destructive fault injection | DVT-THM-006, DVT-SAF-018, DVT-SAF-019 | 3 |

| Test | Title | Applicability | Reps |
|---|---|---|---|
| DVT-ELE-001 | Protective earth bonding continuity | ALL | 1 |
| DVT-ELE-002 | Insulation resistance | ALL | 1 |
| DVT-ELE-003 | Dielectric strength (hipot) | ALL | 1 |
| DVT-ELE-004 | Touch current | ALL | 1 |
| DVT-ELE-005 | Rated input current, input power per mode (HEAT / CURE / whole machine), inrush — at 100 / 110 / 230 / 240 V | ALL | 4 |
| DVT-SAF-001 | Circulation fan failure during heating — heater cut-off read on the heater-body thermocouple | ALL | 3 |
| DVT-SAF-002 | Heater sensor open circuit — heater-off time read from the heater-body thermocouple (TC-08), rise-to-fall turn | ALL | 3 |
| DVT-SAF-003 | Heater sensor replaced by a fixed 10 kΩ resistor (frozen 25 °C reading) — detection within 3 min, heater off at the alarm, HEAT inhibited | ALL | 3 |
| DVT-SAF-004 | LED thermistor open circuit | ALL | 4 |
| DVT-SAF-005 | LED cooling fan failure | ALL | 8 |
| DVT-SAF-006 | Chamber cooling fan failure | ALL | 2 |
| DVT-SAF-020 | Fault alarm coverage review | SINGLE | 1 |
| DVT-SAF-007 | 220 V selector on 110 V mains | ALL | 1 |
| DVT-SAF-017 | Voltage selector in the mid position — heater open circuit, no-heating alarm must name the selector | ALL | 1 |
| DVT-SAF-008 | Door interlock — UV-off time measured with the Ophir StarBright (instrumented step) | ALL | 3 |
| DVT-SAF-009 | Independent thermal cutout — trip temperature and time under continuous heating with all software limits removed (TC-08 on the heater body at the cutout) | ALL | 1 |
| DVT-SAF-010 | Watchdog / heartbeat loss — SSR cut-off read on the heater-body thermocouple and the Ophir trace | ALL | 3 |
| DVT-SAF-011 | Mains interruption during operation — no auto-resume proven on the heater-body thermocouple | ALL | 4 |
| DVT-SAF-012 | UV emission outside the enclosure | ALL | 1 |
| DVT-SAF-013 | Interlock disabled, disconnected or bypassed | ALL | 3 |
| DVT-SAF-014 | Software stack failure, per layer | SINGLE | 7 |
| DVT-SAF-015 | Degraded LED cooling, detection and fault isolation | ALL | 7 |
| DVT-SAF-016 | LED panel electrically disconnected — detection at switch-on, panel identification | ALL | 8 |
| DVT-THM-001 | Chamber thermal characterisation — step response, uniformity, heat-up (230 V sweep + 30/80 °C at 100, 110, 240 V) | ALL | 12 |
| DVT-THM-002 | LED temperature over a 30 min cure, 30 / 80 °C chamber | ALL | 2 |
| DVT-THM-003 | Cool-down at fast / normal / slow rates, 25 °C ambient — co-executed on DVT-THM-001 descents | ALL | 3 |
| DVT-THM-004 | LED settled temperature vs LED-cooling fan duty 100 / 90 / 80 / 70 %, LEDs at maximum, 80 °C chamber — how far the airflow can be reduced | ALL | 4 |
| DVT-OPT-001 | UV irradiance vs commanded LED power, 405 nm — StarBright on the machine's USB, 30 → 100 % in 10 % steps, 15 s each | ALL | 5 |
| DVT-OPT-002 | UV irradiance vs commanded LED power, 450 nm — same, meter set to 450 nm | ALL | 5 |
| DVT-GAS-007 | Nitrogen purge — time to 95 % N2 (O2 ≤ 4.8 %) and hold time with the valve closed, chamber at ambient and at 80 °C | ALL | 4 |
| DVT-NFC-001 | Build-head NFC identification — read on insertion, correct head bound, swap, no tag, unknown tag, short seating, reader disabled | ALL | 6 |
| DVT-THM-006 | Heater over-drive on 230 V with the 110 V selector — time to shutdown (fuse opening) on the heater-body thermocouple (destructive) | SINGLE | 1 |
| DVT-ENV-001 | Road transport, packaged | SINGLE | 1 |
| DVT-GAS-001 | Nitrogen inlet over-pressure — 1.0 / 1.5 / 2.0 x rated, valve closed and open | ALL | 3 |
| DVT-GAS-002 | Supply low or lost — enable guard, pre-cure check, mid-purge, mid-cure | SINGLE | 4 |
| DVT-GAS-003 | Valve fail-safe — off 24 h, power loss, door, abort | ALL | 1 |
| DVT-GAS-004 | Venting — O2 safe before job complete and door release | ALL | 1 |
| DVT-GAS-005 | Room O2 depletion at the operator, smallest permitted room | SINGLE | 1 |
| DVT-SAF-018 | 110 V selector on 230 V mains (destructive) | SINGLE | 1 |
| DVT-SAF-019 | Mains input short circuit (destructive) | SINGLE | 1 |

### New in Rev B

Added on engineering grounds, beyond the original list:

- **DVT-ELE-001 bonding continuity, on all five units.** Bonding depends on assembly workmanship — paint under a star washer, a missing strap — so it is a unit-to-unit variable, not a design property. It is the most common first-check finding.
- **DVT-ELE-003 hipot** and **DVT-ELE-002 insulation resistance** as its before/after reference.
- **DVT-ELE-004 touch current.** Four LED driver input filters plus the EMC filter stack Y-capacitance. This is the measurement most likely to come back over the limit, and finding that late is expensive.
- **DVT-ELE-005 inrush and power budget.** Four drivers and a 120 W PSU switching on together, against a 15 A time-lag fuse and a customer's 16 A breaker. One run per mains voltage — 100 V added as the low-line point on the 110 V selector position (worst case for input current; 240 V is the worst case for power) — and the input power recorded per operating mode: idle, heater only, LEDs only (CURE without heating) and the whole machine working. The whole-machine figure is the rating-label number; the single-mode figures are the measured power budget the PSU sizing and the DVT-SAF-007 under-power detection rest on.
- **DVT-SAF-004 LED thermistor open circuit** — instrumented like DVT-SAF-008: the LEDs are at maximum on the Ophir head when the thermistor connector is pulled; led_off_time is the disconnection (first controller poll with no reading for that sensor, or the operator's marker) to the irradiance falling below 10 % of plateau, limit 2 s, and the alarm must name the position. Whether the controller as built cuts LED drive on a lost LED reading mid-cure is exactly what the trace shows — a trace that never drops is recorded as a software finding, not a waiver.
- **DVT-SAF-008 door interlock**, including a magnet defeat attempt. A hall or reed sensor driven by a door magnet is usually defeatable from outside unless the sensor is coded.
- **DVT-SAF-009 thermal cutout** — the protection that has to work when the software does not, so it is tested that way: every software temperature limit removed, heater at 100% without interruption, a type-K thermocouple on the heater body at the cutout logged by the PicoLog TC-08, and the two numbers the thermal design rests on recorded — the heater-body temperature at which the cutout opens and the time from heater-on to the trip. The software-visible proof that power was really removed is the chamber falling under a 100% heater command; what the controller reports meanwhile is recorded and, on the machine as built (no cutout input, no heater-response watchdog), expected to be nothing — a software finding, not a waiver. A manual mains abort ceiling on the heater-body thermocouple (CONFIRM 250 °C) protects the unit if the cutout never acts; using it is a FAIL.
- **DVT-SAF-010 watchdog / heartbeat loss**, including process kill, not only heartbeat stop.
- **DVT-SAF-011 mains interruption.** A job silently marked complete after a power cut ships an under-cured part.
- **DVT-SAF-012 UV emission outside the enclosure** — leakage varies with door seal compression, so per unit.
- **DVT-SAF-013 interlock disconnected, shorted or bypassed** — the abnormal cases, as opposed to DVT-SAF-008 which is the normal open door.
- **DVT-SAF-014 software stack failure per layer** — UI kill, API kill, daemon kill, daemon hang, OS freeze, storage loss, I2C loss.
- **DVT-THM-001 merged** — uniformity, step response and heat-up time now come from one instrumented run per matrix row, sweeping setpoint 30–80 °C at 230 V plus the range extremes at 110 V and 240 V — and, since 2026-09-06, at 100 V, the low line of the 110 V selector position and the longest heat-up in the campaign.
- **DVT-THM-002 LED temperature over a 30 minute cure**, all four panels, at 30 °C and 80 °C chamber.
- **DVT-THM-003 cool-down** at fast, normal and slow rates, ambient at 25 ± 1 °C, executed on the descent of the three DVT-THM-001 rows that end at 80 °C rather than as separate heat-ups.
- **DVT-THM-006 heater over-drive** — 230 V on the 110 V selector, the DVT-SAF-018 fault, but timed: the heater-body thermocouple (the DVT-SAF-009 bond) shows the body climbing steeply and turning down the instant the branch fuse opens; heater_off_time is the HEAT command to that turn, recorded with the body temperature at the turn, the peak, which fuse opened and the software's reaction. The acceptable over-drive time is an open decision (heater_thresholds.selector_mismatch_fuse_open_max, from the 0BLF005.T time-current curve at the measured branch current against the heater rating); until it is set the verdict is BLOCKED. Destructive, on UUT-05, may share the energisation with DVT-SAF-018.
- **DVT-OPT-001 / DVT-OPT-002 UV irradiance against the command** — the software treats the commanded LED power as calibrated system power; nothing verified it. The StarBright goes on the machine's own USB (the Pi reads it, no console PC in the loop), the machine steps 30 → 100 % at 405 nm and again at 450 nm with the meter set to match (the sweep refuses to start otherwise) and the console plots measured irradiance against the command. Linearity and absolute-output limits are open decisions; the bench run of 2026-09-14 at 450 nm gave 0.299 mW/cm² per %, R² 0.993, with the gain falling from 0.40 to 0.33 as the LEDs warm.
- **DVT-SAF-015 degraded LED cooling** — fan weakened rather than failed, four-case matrix covering the tachometer asymmetry, detection before the limit, alarm naming the side.
- **DVT-SAF-016 LED panel electrically disconnected** — one panel opened (LED string, then driver supply), LEDs switched on: the alarm must say a panel is not working, name the correct panel and tell the operator to check the LED; the job must not run with a dark panel. Per unit, because the connector and harness are workmanship.
- **DVT-SAF-008 instrumented (2026-09-06).** Step 2 is driven by the console: LEDs on at maximum, Ophir StarBright (StarLab USB, serial, or the simulated meter) sampled at 25 Hz, door released via the API or opened by the operator, irradiance recorded until it falls below 10 % of the plateau, LEDs off. The console attaches the CSV and the irradiance-vs-time graph (door-open and UV-off markers, measured uv_off_time against the 1 s limit) to the run and fills uv_off_time, residual_irradiance, alarm_raised and error_code. CONFIRM: serial command set against the StarBright manual; the head's aperture area for mW/cm2.
- **Heater shutdown is proven on the heater body (2026-09-06).** Every test that expects the heater to be cut — DVT-SAF-001, 004, 005, 013, 014, 015 — reads the de-energisation from the type-K thermocouple bonded to the heater body (PicoLog TC-08), not from the SSR command: the instant the trace turns from rising to falling is the moment power was removed, and the tests are run in the heat-up phase (heater at full output) so that turn is unmistakable. The reading lags the electrical event, so it is conservative; a FAIL on the trace is cross-checked at the SSR output before it is recorded. LED shutdown, correspondingly, is read from the Ophir StarBright irradiance trace (DVT-SAF-008, DVT-SAF-010).
- **DVT-SAF-017 voltage selector in the mid position (2026-09-06).** Between the 110 V and 230 V detents the selector is open and the heater simply receives nothing — no damage, no fuse, just a chamber that never heats. The system must detect the absence of heating within a bounded time and tell the customer to set the selector to the position matching their country's mains. The heater-body thermocouple staying flat is the proof of the open circuit (DVT-SAF-007, quarter power, still rises slowly). Today only the 25-minute stall rule can catch it and its text does not mention the selector — a software finding.

- **DVT-GAS-007 nitrogen purge — time to 95 % N2 and hold.** The machine has no oxygen sensor: the purge is a fixed time (Settings, default 120 s) after drying, then the valve closes and the UV cure runs on whatever atmosphere is left. An oxygen analyser (centre + worst corner) measures, per unit and at ambient / 80 °C, the time to O2 ≤ 4.8 % (= 95 % N2) and how long the chamber stays there with the valve closed. The programmed purge time must exceed the worst unit's time by 20 %; the hold must cover the longest cure that follows — otherwise the part cures in rising oxygen and the answer is a longer hold (seals), a top-up flow during the cure, or an oxygen sensor closing the loop. Limits `nitrogen_thresholds.purge_time_max_s` / `hold_time_min_s` are CONFIRM (BLOCKED until set).
- **Nitrogen subsystem, DVT-GAS-001…007 (2026-09-06).** The machine has one normally-closed solenoid on GPIO13 opened for a preset 120 s, no flow control, no line-pressure sensor on the board and no O2 sensor — so the software knows nothing about the nitrogen except that it commanded the valve. The tests measure what the software cannot: over-pressure containment with the valve closed and open (DVT-GAS-001, the case that fills the chamber without a command) — DVT-GAS-007 already measures what the purge achieves and how long the chamber holds it — the response to a missing or lost supply (DVT-GAS-002), that the valve only flows on command — off 24 h, power cut, door, abort (DVT-GAS-003), that the chamber is breathable before the door is released (DVT-GAS-004), the operator's O2 in the smallest permitted room (DVT-GAS-005) and the coil temperature with the valve held open (DVT-GAS-006). Every limit is a CONFIRM in `nitrogen_thresholds` and the tests stay BLOCKED until set.
- **DVT-NFC-001 build-head identification (2026-09-10).** The build head is a consumable with an NFC tag and the print record binds build head + tray membrane per print. Six cases per unit: registered head read and bound, swap follows the tag (catches a cached UID), no tag, unknown tag, 5 mm short seating, reader disabled — all reported to the operator, never a silent bind. Today the machine exposes only 'NFC enabled' and a top-bar indicator: no tag serial in /api/state and no error code for a missing or unknown tag — a software finding the test will show.
- **DVT-THM-004 LED temperature versus fan duty (2026-09-10).** LEDs at maximum in the 80 °C chamber, LED-cooling fans at 100 / 90 / 80 / 70 % in turn, every panel left to settle (or stopped at the 75 °C working limit). Each row is judged against the working limit; the lowest duty that passes on all five units, minus a margin (CONFIRM, proposed 5 °C), is the candidate production fan setting, and DVT-SAF-015's degraded-cooling thresholds come from the same curves. The bonded thermocouple against the built-in thermistor also gives the sensor offset the firmware protection must allow for.

### Recommended for later batches, not yet written

EMC pre-compliance (radiated emissions EN 55032, ESD EN 61000-4-2, EFT, surge); handle strength per 62368-1 clause 8.8.2 at 2× weight or 75 kg; stability and tip-over; LED lifetime soak against the 4,500 h target; acoustic emission; liquid spill and ingress; UV irradiance and uniformity inside the chamber.

---

## 4. Execution Order — the Wizard Model

The operator is never asked "what should I run next". The application answers that.

### 4.1 Phases and gates

Phases are ordered and gated. A phase does not open until the previous one is closed for that unit.

| Phase | Contents | Gate to open the next phase |
|---|---|---|
| **0 — Incoming** | Visual inspection, serial number, configuration record and freeze, fuse verification, calibration check on all equipment | Configuration frozen and signed; all equipment calibrations valid through the planned phase |
| **1 — Electrical safety** | DVT-ELE-001 → DVT-ELE-002 → DVT-ELE-003 → DVT-ELE-004 → DVT-ELE-005 | All ELE tests PASS. No unit proceeds to powered fault injection with an unverified earth |
| **2 — Protective functions** | DVT-SAF-008, 013, 014, 004, 005, 003, 007, 006, 008, 009, 015, 016, 017, 011, 018, 019, 020, 021, then DVT-SAF-020 review | All protective functions PASS or have an approved disposition |
| **3 — Performance** | DVT-THM-001 matrix, DVT-THM-002, DVT-THM-003 | Data complete |
| **4 — Transport** | DVT-ENV-001 on the designated unit, with DVT-ELE-001/002 and a functional test repeated on return | Post-shipment functional test PASS |
| **5 — Destructive** | DVT-THM-006, DVT-SAF-018, DVT-SAF-019 on the designated unit only, **last** | — |
| **6 — Closure** | VCRM review, unverified requirement list, NCR closure, report issue | Report issued |

Three ordering rules that are not negotiable and are enforced by the software:

1. **Earth before power.** DVT-ELE-001 precedes every powered test on that unit. Injecting faults into a unit whose protective earth has not been verified is how a test engineer gets hurt.
2. **Destructive last.** DVT-THM-006, DVT-SAF-018 and DVT-SAF-019 consume protective devices and stress the harness. Any result taken from that unit afterwards is from a different article.
3. **Hipot once.** DVT-ELE-003 stresses insulation. It runs once per unit in Phase 1, and is not repeated except after transport, where degradation is the thing being looked for.
4. **Same instrument, one after the other (bench order).** Within a phase the tool orders the tests so that those sharing an instrument set — the TC-08 heater-body thermocouple tests, the Ophir tests, the oxygen-analyser tests — run consecutively, and the *next action* keeps the setup already on the bench for that unit. Rules 1–3 and every dependency win over grouping: the order never asks for a test before the one it depends on (SRS-DVT-196).

### 4.2 Within a session

Select unit → the application shows the current phase, the readiness checklist for it, and the next test. For that test: preconditions checklist → equipment and calibration check → step-by-step procedure with data entry bound to each step → automatic verdict → NCR if FAIL → next test.

---

## 5. Software Requirements

Rev A requirements SRS-DVT-001 through 075 stand unchanged. The following are added.

### 5.1 Guided execution

- **SRS-DVT-080** The application shall present a single "next action" for the selected unit, derived from phase order, dependency graph and current status.
- **SRS-DVT-081** Each phase shall have a readiness checklist that must be completed and signed before any test in that phase can start. This is the Test Readiness Review gate.
- **SRS-DVT-082** A test whose dependencies or phase gate are not satisfied shall be visible but not startable, with the blocking reason shown.
- **SRS-DVT-083** Preconditions shall be presented as an explicit checklist that must be confirmed before the first data field unlocks.
- **SRS-DVT-084** Steps flagged as safety-critical (high voltage applied, destructive fault injection) shall require an explicit confirmation, and shall display the test's `safety_plan` before proceeding.
- **SRS-DVT-085** The application shall verify that every instrument named in `equipment` has a calibration record valid on the run date, and shall block the run if one has expired.
- **SRS-DVT-086** The operator shall be able to redline any procedure step during execution — mark it as performed differently, with the reason. Redlines are captured in the run record and reproduced in the report as the as-run procedure.
- **SRS-DVT-087** A WAIVED verdict shall require an approver identity and a written rationale; it shall be counted separately from PASS everywhere it is displayed.
- **SRS-DVT-088** Progress state shall survive application restart; a part-completed run resumes at the step where it stopped.

### 5.2 Everything in one place

- **SRS-DVT-090** The application shall be the single store for: test catalog, UUT registry, equipment and calibration records, run data, attachments, redlines, NCRs, waivers, approvals and generated reports.
- **SRS-DVT-091** Attachments (thermocouple logs, oscilloscope captures, photographs, radiometer exports) shall be stored against the run that produced them and shall be retrievable from the comparison view.
- **SRS-DVT-092** A single search across tests, units, error codes and NCR text shall be provided.
- **SRS-DVT-093** The application shall export a self-contained archive of the entire campaign — database, attachments and catalog version — for backup and for merging results from a second site.

### 5.3 Parameter sweeps

- **SRS-DVT-094** A test may declare a `sweep` parameter with a list of values; the applicable run set is then tests × units × sweep values.
- **SRS-DVT-095** The comparison view shall support grouping by sweep parameter, so a swept test renders as a curve per unit — overshoot against setpoint, for example — rather than as six unrelated rows.
- **SRS-DVT-096** A swept test shall report a verdict per sweep value and a rolled-up verdict for the test; the rolled-up verdict is PASS only if every value passes.

### 5.4 Co-executed runs

- **SRS-DVT-097** A test may declare `co_executed_with`, naming a parent test and the parent rows its runs ride on. The wizard shall present both procedures as one continuous execution rather than sending the operator to heat the chamber a second time.
- **SRS-DVT-098** Co-executed runs shall be linked in both directions in the run record, and each shall keep its own verdict, its own requirement trace and its own column in the comparison view.
- **SRS-DVT-099** Rejecting a parent run shall rescind its co-executed child runs, with the reason carried across. One thermal history cannot be half valid.
- **SRS-DVT-100** Data captured outside a test's declared applicability — the cooling descents from the 30–70 °C rows, for example — shall be storable as supplementary runs, retrievable in the comparison view, and excluded from progress metrics per SRS-DVT-012.

### 5.5 Cloud synchronisation (added with the implementation)

- **SRS-DVT-110** Every saved run, NCR, waiver and redline shall be exported automatically — without operator action — to the campaign folder on the engineer's Google Drive: the campaign database, a per-test CSV, a campaign workbook (XLSX, one sheet per test + summary) and the Markdown report.
- **SRS-DVT-111** Synchronisation shall use the Google Drive API with the engineer's own account (OAuth), or a local folder synchronised by Google Drive for Desktop / OneDrive when configured; the active mode and the last successful sync time shall be visible in the application.
- **SRS-DVT-112** A sync failure shall never block or lose a run: results are committed locally first, queued, and retried; the queue length is visible.

---

## 6. Open Decisions

Carried forward and consolidated. Each blocks baseline of the test it belongs to.

**Design questions that decide whether a test is passable at all**

1. **Fan failure detection means.** Tach, current sense, or nothing? Without feedback, DVT-SAF-001 / 008 / 009 cannot pass. This is a hardware requirement, not a test parameter.
2. **LED thermistor detached but connected (the old SAF-006, removed 2026-10-01).** Reads a valid ambient value, so a range check cannot see it. Needs a plausibility rule — drive above threshold with no rate of rise, or cross-check against the other three panels.
3. **Mains voltage sensing / selector position readback (DVT-SAF-007).** If neither exists, the only detection is a heating-rate watchdog. It must be based on dT/dt, not elapsed time — a correctly configured unit takes 27–33 minutes to 80 °C, so any elapsed-time timeout below about 40 minutes false-triggers in normal use.

**Values to set**

4. Response time limits: 2 s for LED paths, 5 s proposed for heater paths, 1 s for the door interlock.
5. Uniformity limit — EVT gave 3 °C peak-to-peak at 70 °C with 15 thermocouples; Rev B proposes ≤5 °C at 16.
6. Hipot test voltage per barrier, from the insulation coordination analysis, agreed with the compliance lab.
7. UV leakage limit and the weighting to apply at 405 nm, which sits on the UV-A / visible-blue boundary where the two limits derive differently.
8. Chamber ceiling temperature for the runaway case, proposed 95 °C.

**Campaign scope**

9. **Requirement 48, heat-up ≤20 min, already fails at EVT** — 32.6 min at 110 V, 27.0 min at 233 V with the 500 W heater. Decide before Phase 3 whether the number stands or goes to a documented waiver. Running a DVT campaign against a limit known to be unachievable produces a failure you have already paid for.
10. Mains voltages: 110 / 230 / 240 cover nominal and high line; DVT-THM-001 now also runs the 30 / 80 °C extremes at 100 V (low line on the 110 V side). Still open: 207 V, the -10 % low line on the 230 V side — add it if the 100 V heat-up comes out near the REQ-48 limit.
11. Which unit is designated destructive (proposed UUT-05), and which is shipped in DVT-ENV-001.
12. Transport: a single real shipment is one sample of an uncontrolled input. If the packaging design has to be defensible, add a lab simulation to ISTA 3E or ASTM D4169.
13. Witnessing: whether Phase 1 and Phase 5 require an independent signature.
14. PicoLog TC-08 is 8 channels — 16 thermocouples needs two synchronised units.
15. Overshoot, steady-state error, limit cycle, settling and uniformity limits for DVT-THM-001. The overshoot limit should come from the resin process window, not from control-theory habit.
16. The minimum controllable setpoint, stated as ambient + N °C. A heat-only chamber cannot hold 30 °C on a warm day, and the 30 and 40 °C points will show the worst overshoot and the slowest recovery in the whole sweep.
17. Whether the DVT-THM-001 matrix needs filling in. It runs the full setpoint sweep at 230 V and only the 30 / 80 °C extremes at 110 V and 240 V. If the extreme rows show uniformity differing materially from the 230 V curve, fill in the middle — not before.
18. Whether a service interlock bypass exists at all, and if so its credential, time limit and indication.
19. **LED temperature ladder — resolved in part.** 75 °C is the *working* limit: the temperature an LED may reach in normal operation, measured on the MCPCB back face 2 mm behind the LED. It is an acceptance criterion, not a trip point, so the protective shutdown sits above it. Still to set: the warning threshold and the protective shutdown value, the latter derived from the post-shutdown thermal overshoot measured in DVT-SAF-015.
19a. **The 50 °C firmware shutdown contradicts the 75 °C working limit** and must change. It is 25 °C below the working limit and 22 °C below what EVT actually measured at 80 °C chamber, so as it stands the machine shuts itself down during ordinary curing. Either the firmware value is stale or it refers to a different sensor point.
19b. **The 65 °C recommendation from the thermal ladder** was derived for the 4,500 h lifetime target, not the absolute maximum. A 75 °C back face puts the junction somewhere near 85–90 °C depending on the MCPCB stackup — inside the 100 °C absolute maximum, but with less lifetime margin than the 65 °C figure assumed. Check 75 °C against the L70 curve before accepting it, and update the LED lifetime entry in the risk register with the result.
20. Which LED position on each panel is the hot spot. A panel is 72 LEDs at 12S×6P; a one-time thermal survey per panel design fixes the instrumented position, and the survey becomes the evidence for that choice.
21. The alarm threshold for degraded cooling, set from the measured post-shutdown thermal overshoot in DVT-SAF-015 rather than assumed.
21a. **Per-panel LED output feedback for DVT-SAF-016.** The controller has no per-panel electrical feedback: `led_fault` only covers the SSR / wavelength-routing GPIO read-back. Three ways to name the dark panel with what exists or nearly exists: (a) the per-panel thermistor — a working panel self-heats within seconds of switch-on, a dark one tracks the chamber, so a rise-rate plausibility rule against the other three panels catches both disconnect points with no new hardware, at a detection time in the tens of seconds; (b) the two light sensors with a one-panel-at-a-time switch-on sequence at job start against a stored healthy baseline — fast, start-only unless repeated; (c) per-panel current sense on the driver output into the six spare ADS1115 inputs — immediate, continuous, the only one that tells an open string from a dead driver, needs a PCB / harness change. Also confirm whether the LED driver has a status output. Decide before Phase 2; without any of these DVT-SAF-016 fails by design and the response is a design change, not a waiver. The `time_to_alarm` limit follows from that decision.
22. **Tachometer on the second fan of each pair.** Only one fan per side reports rotation. Without the second, a weakened unmonitored fan and a blocked shared air path are indistinguishable — both show a healthy tach and a rising panel. Fitting the lead converts an inference into a measurement; per-fan current sensing on the existing PCA9685 channels is the fallback if inputs are the constraint.
23. **A climate-controlled space for DVT-THM-003.** Cooling is driven by the difference to ambient, so a run at 21 °C and a run at 28 °C give different rates from identical hardware. Without a controlled room the five-unit comparison measures the weather. If none is available, at minimum schedule all five units under the same ambient and record it as a covariate.
24. Whether pairing each cooling mode with a different mains voltage is acceptable, given co-execution. Cooling is fan-driven from the 12 V rail with the heater off, so mains should not be a meaningful covariate — but if an anomaly appears, repeat that mode at 230 V standalone before concluding anything.
24a. The temperature band over which the cooling rate tolerance applies, and what is specified below the point where the fan saturates — below there the loop has no authority left and the honest specification is a time, not a rate.
25. Whether the cooling specification is meant to hold with a part in the chamber. All runs are currently empty, as EVT was; a loaded chamber has more thermal mass and cools more slowly.
26. Wording of the degraded-cooling message. The system may say the side is degraded; it may not name a specific fan unless the claim is actually true. A confidently wrong diagnosis sends a technician to replace a good fan.
28. **Nitrogen purge limits for DVT-GAS-007** (`nitrogen_thresholds.purge_time_max_s`, `hold_time_min_s`), the N2 regulator pressure / flow the purge is specified at, and the chamber volume. The hold minimum is the longest UV cure that follows a purge in any released program; the purge maximum bounds the programmed nitrogen duration (default 120 s) — if the worst unit needs longer, the setting changes, not the limit. Until both are set the DVT-GAS-007 verdict is BLOCKED.
27. **Acceptable heater over-drive time for DVT-THM-006** (heater_thresholds.selector_mismatch_fuse_open_max). How long the heater may run on 230 V with the 110 V selector before the 0BLF005.T branch fuse must have opened — from the fuse's time-current curve at the branch current measured in DVT-SAF-018 and the heater element's rating. The heater-body ceiling of 250 °C (heater_thresholds.body_ceiling) also needs confirming against the heater and insulation ratings. Until both are set the DVT-THM-006 verdict is BLOCKED.
26. **Nitrogen limits (`nitrogen_thresholds`)**: the rated maximum inlet pressure (solenoid / tubing / fitting ratings), the chamber pressure limit with the valve open (door seal), the residual O2 the resin needs and the O2 rise the cure tolerates, the minimum room volume the manual will state, and the solenoid coil insulation class. DVT-GAS-001/002/003/008 are BLOCKED until these are set.
27. **No nitrogen line-pressure sensor on the board.** `io_bridge` reports `n2LinePressure = null`, so the 6 bar enable guard and the pre-cure "N₂ line pressure" check have nothing to read — and the Settings guard compares the missing value with 6 bar (`null < 6` is true), so on real hardware nitrogen mode cannot be enabled at all. Fit a pressure switch or transducer on the inlet (a spare ADS1115 input is enough) or remove the guard and rely on the O2 result. DVT-GAS-002 will show this.
28. **Chamber volume and purge exchange count.** The 120 s default purge is a guess; DVT-GAS-007's time to 95 % N2 is what sets it. Measure the chamber volume so consumption reads as exchanges.
29. **NFC tag data and messages.** The reader exists (NFC_RESET on the expander) but the software reports nothing about what it read: add the tag serial / bound build head to /api/state and error codes for 'no tag', 'unknown tag' and 'reader disabled', and decide whether a print may start without an identified build head. DVT-NFC-001 cases C, D and F have nothing to judge until then. Detection-time limit: CONFIRM (proposed 3 s).
