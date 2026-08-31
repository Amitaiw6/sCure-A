# DVT Verification Plan & Test Software SRS

**Project:** sCure / CureBox DVT
**Document:** SRS-DVT-SW, Rev B
**Supersedes:** Rev A
**Author:** Amitai Walker
**Machine-readable catalog:** `../catalog/DVT_test_catalog.yaml` v0.9 — 28 tests, 356 applicable runs
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

356 applicable runs, roughly 635 bench hours excluding transport transit.

| Phase | Tests | Runs |
|---|---|---|
| 0 — Incoming and configuration | inspection, config freeze | per unit |
| 1 — Electrical safety | ELE-001…005 | 35 |
| 2 — Protective functions | SAF-003…019 | 243 |
| 3 — Performance | THM-001…003 | 75 |
| 4 — Transport | ENV-001 | 1 |
| 5 — Destructive fault injection | SAF-001, SAF-002 | 2 |

| Test | Title | Applicability | Reps |
|---|---|---|---|
| ELE-001 | Protective earth bonding continuity | ALL | 1 |
| ELE-002 | Insulation resistance | ALL | 1 |
| ELE-003 | Dielectric strength (hipot) | ALL | 1 |
| ELE-004 | Touch current | ALL | 1 |
| ELE-005 | Rated input current, power, inrush | ALL | 3 |
| SAF-003 | Circulation fan failure during heating | ALL | 3 |
| SAF-004 | Heater sensor open circuit | ALL | 3 |
| SAF-005 | Heater sensor shorted | ALL | 3 |
| SAF-006 | LED thermistor detached from MCPCB | ALL | 1 |
| SAF-007 | LED thermistor open circuit | ALL | 4 |
| SAF-008 | LED cooling fan failure | ALL | 8 |
| SAF-009 | Chamber cooling fan failure | ALL | 2 |
| SAF-010 | Fault alarm coverage review | SINGLE | 1 |
| SAF-011 | 220 V selector on 110 V mains | ALL | 1 |
| SAF-012 | Door interlock | ALL | 3 |
| SAF-013 | Independent thermal cutout | ALL | 1 |
| SAF-014 | Watchdog / heartbeat loss | ALL | 3 |
| SAF-015 | Mains interruption during operation | ALL | 4 |
| SAF-016 | UV emission outside the enclosure | ALL | 1 |
| SAF-017 | Interlock disabled, disconnected or bypassed | ALL | 3 |
| SAF-018 | Software stack failure, per layer | SINGLE | 7 |
| SAF-019 | Degraded LED cooling, detection and fault isolation | ALL | 7 |
| THM-001 | Chamber thermal characterisation — step response, uniformity, heat-up | ALL | 10 |
| THM-002 | LED temperature over a 30 min cure, 30 / 80 °C chamber | ALL | 2 |
| THM-003 | Cool-down at fast / normal / slow rates, 25 °C ambient — co-executed on THM-001 descents | ALL | 3 |
| ENV-001 | Road transport, packaged | SINGLE | 1 |
| SAF-001 | 110 V selector on 230 V mains (destructive) | SINGLE | 1 |
| SAF-002 | Mains input short circuit (destructive) | SINGLE | 1 |

### New in Rev B

Added on engineering grounds, beyond the original list:

- **ELE-001 bonding continuity, on all five units.** Bonding depends on assembly workmanship — paint under a star washer, a missing strap — so it is a unit-to-unit variable, not a design property. It is the most common first-check finding.
- **ELE-003 hipot** and **ELE-002 insulation resistance** as its before/after reference.
- **ELE-004 touch current.** Four LED driver input filters plus the EMC filter stack Y-capacitance. This is the measurement most likely to come back over the limit, and finding that late is expensive.
- **ELE-005 inrush.** Four drivers and a 120 W PSU switching on together, against a 15 A time-lag fuse and a customer's 16 A breaker.
- **SAF-012 door interlock**, including a magnet defeat attempt. A hall or reed sensor driven by a door magnet is usually defeatable from outside unless the sensor is coded.
- **SAF-013 thermal cutout** — the protection that has to work when the software does not.
- **SAF-014 watchdog / heartbeat loss**, including process kill, not only heartbeat stop.
- **SAF-015 mains interruption.** A job silently marked complete after a power cut ships an under-cured part.
- **SAF-016 UV emission outside the enclosure** — leakage varies with door seal compression, so per unit.
- **SAF-017 interlock disconnected, shorted or bypassed** — the abnormal cases, as opposed to SAF-012 which is the normal open door.
- **SAF-018 software stack failure per layer** — UI kill, API kill, daemon kill, daemon hang, OS freeze, storage loss, I2C loss.
- **THM-001 merged** — uniformity, step response and heat-up time now come from one instrumented run per matrix row, sweeping setpoint 30–80 °C at 230 V plus the range extremes at 110 V and 240 V.
- **THM-002 LED temperature over a 30 minute cure**, all four panels, at 30 °C and 80 °C chamber.
- **THM-003 cool-down** at fast, normal and slow rates, ambient at 25 ± 1 °C, executed on the descent of the three THM-001 rows that end at 80 °C rather than as separate heat-ups.
- **SAF-019 degraded LED cooling** — fan weakened rather than failed, four-case matrix covering the tachometer asymmetry, detection before the limit, alarm naming the side.

### Recommended for later batches, not yet written

EMC pre-compliance (radiated emissions EN 55032, ESD EN 61000-4-2, EFT, surge); handle strength per 62368-1 clause 8.8.2 at 2× weight or 75 kg; stability and tip-over; chamber sealing and nitrogen fill; LED lifetime soak against the 4,500 h target; acoustic emission; liquid spill and ingress; UV irradiance and uniformity inside the chamber.

---

## 4. Execution Order — the Wizard Model

The operator is never asked "what should I run next". The application answers that.

### 4.1 Phases and gates

Phases are ordered and gated. A phase does not open until the previous one is closed for that unit.

| Phase | Contents | Gate to open the next phase |
|---|---|---|
| **0 — Incoming** | Visual inspection, serial number, configuration record and freeze, fuse verification, calibration check on all equipment | Configuration frozen and signed; all equipment calibrations valid through the planned phase |
| **1 — Electrical safety** | ELE-001 → ELE-002 → ELE-003 → ELE-004 → ELE-005 | All ELE tests PASS. No unit proceeds to powered fault injection with an unverified earth |
| **2 — Protective functions** | SAF-012, 013, 014, 004, 005, 003, 007, 006, 008, 009, 015, 016, 017, 011, 018, 019, then SAF-010 review | All protective functions PASS or have an approved disposition |
| **3 — Performance** | THM-001 matrix, THM-002, THM-003 | Data complete |
| **4 — Transport** | ENV-001 on the designated unit, with ELE-001/002 and a functional test repeated on return | Post-shipment functional test PASS |
| **5 — Destructive** | SAF-001, SAF-002 on the designated unit only, **last** | — |
| **6 — Closure** | VCRM review, unverified requirement list, NCR closure, report issue | Report issued |

Three ordering rules that are not negotiable and are enforced by the software:

1. **Earth before power.** ELE-001 precedes every powered test on that unit. Injecting faults into a unit whose protective earth has not been verified is how a test engineer gets hurt.
2. **Destructive last.** SAF-001 and SAF-002 consume protective devices and stress the harness. Any result taken from that unit afterwards is from a different article.
3. **Hipot once.** ELE-003 stresses insulation. It runs once per unit in Phase 1, and is not repeated except after transport, where degradation is the thing being looked for.

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

1. **Fan failure detection means.** Tach, current sense, or nothing? Without feedback, SAF-003 / 008 / 009 cannot pass. This is a hardware requirement, not a test parameter.
2. **LED thermistor detached but connected (SAF-006).** Reads a valid ambient value, so a range check cannot see it. Needs a plausibility rule — drive above threshold with no rate of rise, or cross-check against the other three panels.
3. **Mains voltage sensing / selector position readback (SAF-011).** If neither exists, the only detection is a heating-rate watchdog. It must be based on dT/dt, not elapsed time — a correctly configured unit takes 27–33 minutes to 80 °C, so any elapsed-time timeout below about 40 minutes false-triggers in normal use.

**Values to set**

4. Response time limits: 2 s for LED paths, 5 s proposed for heater paths, 1 s for the door interlock.
5. Uniformity limit — EVT gave 3 °C peak-to-peak at 70 °C with 15 thermocouples; Rev B proposes ≤5 °C at 16.
6. Hipot test voltage per barrier, from the insulation coordination analysis, agreed with the compliance lab.
7. UV leakage limit and the weighting to apply at 405 nm, which sits on the UV-A / visible-blue boundary where the two limits derive differently.
8. Chamber ceiling temperature for the runaway case, proposed 95 °C.

**Campaign scope**

9. **Requirement 48, heat-up ≤20 min, already fails at EVT** — 32.6 min at 110 V, 27.0 min at 233 V with the 500 W heater. Decide before Phase 3 whether the number stands or goes to a documented waiver. Running a DVT campaign against a limit known to be unachievable produces a failure you have already paid for.
10. Mains voltages: 110 / 230 / 240 covers nominal and high line. Low line — 99 V and 207 V — is where heat-up time is worst and is currently untested.
11. Which unit is designated destructive (proposed UUT-05), and which is shipped in ENV-001.
12. Transport: a single real shipment is one sample of an uncontrolled input. If the packaging design has to be defensible, add a lab simulation to ISTA 3E or ASTM D4169.
13. Witnessing: whether Phase 1 and Phase 5 require an independent signature.
14. PicoLog TC-08 is 8 channels — 16 thermocouples needs two synchronised units.
15. Overshoot, steady-state error, limit cycle, settling and uniformity limits for THM-001. The overshoot limit should come from the resin process window, not from control-theory habit.
16. The minimum controllable setpoint, stated as ambient + N °C. A heat-only chamber cannot hold 30 °C on a warm day, and the 30 and 40 °C points will show the worst overshoot and the slowest recovery in the whole sweep.
17. Whether the THM-001 matrix needs filling in. It runs the full setpoint sweep at 230 V and only the 30 / 80 °C extremes at 110 V and 240 V. If the extreme rows show uniformity differing materially from the 230 V curve, fill in the middle — not before.
18. Whether a service interlock bypass exists at all, and if so its credential, time limit and indication.
19. **LED temperature ladder — resolved in part.** 75 °C is the *working* limit: the temperature an LED may reach in normal operation, measured on the MCPCB back face 2 mm behind the LED. It is an acceptance criterion, not a trip point, so the protective shutdown sits above it. Still to set: the warning threshold and the protective shutdown value, the latter derived from the post-shutdown thermal overshoot measured in SAF-019.
19a. **The 50 °C firmware shutdown contradicts the 75 °C working limit** and must change. It is 25 °C below the working limit and 22 °C below what EVT actually measured at 80 °C chamber, so as it stands the machine shuts itself down during ordinary curing. Either the firmware value is stale or it refers to a different sensor point.
19b. **The 65 °C recommendation from the thermal ladder** was derived for the 4,500 h lifetime target, not the absolute maximum. A 75 °C back face puts the junction somewhere near 85–90 °C depending on the MCPCB stackup — inside the 100 °C absolute maximum, but with less lifetime margin than the 65 °C figure assumed. Check 75 °C against the L70 curve before accepting it, and update the LED lifetime entry in the risk register with the result.
20. Which LED position on each panel is the hot spot. A panel is 72 LEDs at 12S×6P; a one-time thermal survey per panel design fixes the instrumented position, and the survey becomes the evidence for that choice.
21. The alarm threshold for degraded cooling, set from the measured post-shutdown thermal overshoot in SAF-019 rather than assumed.
22. **Tachometer on the second fan of each pair.** Only one fan per side reports rotation. Without the second, a weakened unmonitored fan and a blocked shared air path are indistinguishable — both show a healthy tach and a rising panel. Fitting the lead converts an inference into a measurement; per-fan current sensing on the existing PCA9685 channels is the fallback if inputs are the constraint.
23. **A climate-controlled space for THM-003.** Cooling is driven by the difference to ambient, so a run at 21 °C and a run at 28 °C give different rates from identical hardware. Without a controlled room the five-unit comparison measures the weather. If none is available, at minimum schedule all five units under the same ambient and record it as a covariate.
24. Whether pairing each cooling mode with a different mains voltage is acceptable, given co-execution. Cooling is fan-driven from the 12 V rail with the heater off, so mains should not be a meaningful covariate — but if an anomaly appears, repeat that mode at 230 V standalone before concluding anything.
24a. The temperature band over which the cooling rate tolerance applies, and what is specified below the point where the fan saturates — below there the loop has no authority left and the honest specification is a time, not a rate.
25. Whether the cooling specification is meant to hold with a part in the chamber. All runs are currently empty, as EVT was; a loaded chamber has more thermal mass and cools more slowly.
26. Wording of the degraded-cooling message. The system may say the side is degraded; it may not name a specific fan unless the claim is actually true. A confidently wrong diagnosis sends a technician to replace a good fan.
