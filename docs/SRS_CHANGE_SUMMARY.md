# sCure Box SRS: Change Summary, Revision 1.0 to Revision 2.3 (draft)

Written in ASD-STE100 Simplified Technical English, Issue 9.

Hebrew version: [SRS_CHANGE_SUMMARY.he.md](SRS_CHANGE_SUMMARY.he.md)

## 1 Purpose

This document gives the changes to the sCure Box Software Requirements Specification (SRS). It starts at the first revision (1.0) and stops at revision 2.2. Revision 2.2 has the date 2026-11-17 and agrees with the firmware sCure CS 1.0.229.

The readers are the software, QA and systems teams. For each revision, the document tells what changed in the requirements, area by area. It does not give a software change log.

The sources are the SRS file `docs/sCure_SRS.html` and its git history. Other sources are `sCureBox-CS/CHANGE_SUMMARY.md` and `sCureBox-CS/config/versions.json`.

## 2 Revisions

| Revision | Date | Firmware checked against | Scope | SRS |
|---|---|---|---|---|
| 1.0 | 2026-07-05 | Not recorded. The text refers to the React UI and the Flask server of sCure-A. | First release. It gives the screen logic and the error registry. Many items are Open Issues. | [Revision table](sCure_SRS.html#revisions) |
| 1.0 (edit, no new number) | 2026-09-09 | sCure-A v0.8.39 and v0.8.40 (from the git commit messages) | Program time estimate, UV wavelength order, temperature-sensor alarms 9001 and 9050. | [Revision table](sCure_SRS.html#revisions) |
| 2.0 | 2026-10-23 | sCure CS 1.0.106 | All sections agree with the new C# firmware. Flow charts are new. All Open Issues were checked again. | [Revision table](sCure_SRS.html#revisions) |
| 2.1 | 2026-11-03 | sCure CS 1.0.141 | Nitrogen line monitor, serial number backup, BOFA extraction, UV-light confirmation, watchdog alarm 9017, swipe Home, P3 catalog, offline unit. | [Revision table](sCure_SRS.html#revisions) |
| 2.1 (edit, no new number) | 2026-11-08 | scurebox-cs 1.0.152 (from the git commit message) | Err 9007 applies only during the ramp up. | [Revision table](sCure_SRS.html#revisions) |
| 2.2 (first part) | 2026-11-13 | sCure CS 1.0.184, for the storage stick only | The backup medium is a USB storage stick. New code 4004. | [Revision table](sCure_SRS.html#revisions) |
| 2.2 (second part) | 2026-11-17 | sCure CS 1.0.229 | Organization HUB, UI languages, damper calibration, LED test changes, sensor severity changes, ten new Open Issues. | [Revision table](sCure_SRS.html#revisions) |
| 2.2 (edit) | 2026-11-17 | sCure CS 1.0.229 | [OI-64](sCure_SRS.html#oi-64) is open again. New [OI-84](sCure_SRS.html#oi-84): a real watchdog trip does not give Err 9017. | [Revision table](sCure_SRS.html#revisions) |
| 2.3 (draft) | 2026-11-18 | sCure CS 1.0.236 | Storage stick missing gives the warning Err 4005, which blocks nothing. New §11.8 UI languages and locale. New OI-85. | [Revision table](sCure_SRS.html#revisions) |

Notes:

- The git history starts on 2026-07-22. The first commit of `docs/sCure_SRS.html` already has revision 1.0 with the date 2026-07-05.
- Before 2026-07-22, the repository had a different document, `docs/SRS.md` (SRS-SCURE-2026-001, version 1.1.0). That commit removed it. This summary does not include it.
- The document text of revision 2.1 has the date 2026-11-03. Git received it on 2026-11-08.
- The edits on 2026-09-09 and 2026-11-08 have no row in the revision table of the SRS.

## 3 Revision 1.0: the first release (baseline)

Revision 1.0 gave the purpose and the logic of each screen. The file `sCure-UI.html` was the reference for the user interface. Many requirements were not complete and were Open Issues.

| SRS area | Requirements in revision 1.0 | SRS |
|---|---|---|
| Process | Four mechanisms with the names Drying, Heating, Curing and Cooling. Their sequence and parameters were not defined (OI-1). | [§1](sCure_SRS.html#intro) |
| Remote access | The process data went to the cloud and GrabCAD showed it to the user. | [§1.3](sCure_SRS.html#s-1-3) |
| Setup | The unit read the serial number (SN) from Storage, then from an SD backup. If there was no SN, the unit got one from a Cloud Service. | [§3.3.4](sCure_SRS.html#s-3-3-4) |
| Setup | The unit tried the cloud request up to five times. Then it registered itself in the cloud. | [§3.3.4](sCure_SRS.html#s-3-3-4) |
| Setup | The SN went to `/etc/scure/config.json`. The backup went to `/mnt/ssd2/scure/config_backup.json` on the SD card. | [§3.5](sCure_SRS.html#s-3-5) |
| Setup Name | The default name was "S-Cure" (OI-7). The only rule was "not empty" ([OI-8](sCure_SRS.html#oi-8)). The name also went to the SD backup. | [§4](sCure_SRS.html#name) |
| Connect Organization | The user loaded a CSV file from a USB drive. The first UUID in the file became the organization ID. The status of this section was "not finalized". | [§5](sCure_SRS.html#org) |
| Home | A fixed Start Cure button started the cure. An Edit button showed Duplicate, Edit and Delete on each row. | [§6.7](sCure_SRS.html#s-6-7) |
| Home | The only start gate was the nitrogen-only program check. Door and pre-cure checks were open (OI-13). | [§6.7.2](sCure_SRS.html#sec-step-rules) |
| Home | The builder gave each step a temperature and a time. OI-17 said that the step time was removed. The two texts did not agree. | [§6.7.2](sCure_SRS.html#sec-step-rules) |
| Home | The program time was the sum of the step times. | [§6.7.3](sCure_SRS.html#sec-estimate) |
| Cure Process | The screen controlled the run. A 1 s tick moved the ramp and the timers. | [§7.3](sCure_SRS.html#s-7-3) |
| Cure Process | The screen did a stall check (7004). The Timer Start and UV Start options were not applied (OI-16). | [§7.3.6](sCure_SRS.html#s-7-3-6) |
| Cure History | The screen was read-only. It had a Download report button. The operator could not delete a run. | [§8](sCure_SRS.html#history) |
| Errors | One registry, `public/config/errors.json`, with 37 codes in the ranges 3xxx to 9xxx. The first digit is the SRS section. | [§9](sCure_SRS.html#errors) |
| Errors | There were two severities, critical and warning. The rule that tells which fault stops a run was open (OI-19). | [§9.5.1](sCure_SRS.html#s-9-5-1) |
| Data | All data was in a PostgreSQL database. Without the database, the API gave HTTP 503. | [§10](sCure_SRS.html#data) |
| Settings | Damper, fan sliders and BOFA changed only the screen (OI-25). The fan and LED tests were simulated (OI-26). | [§11.3](sCure_SRS.html#s-11-3) |
| Settings | Nitrogen Mode had a 6 bar minimum, but the screen showed a fixed "2.0 bar" (OI-27). The manual clock did not change the system clock (OI-28). | [§11.3](sCure_SRS.html#s-11-3) |
| Open Issues | 23 open items: OI-1, OI-6 to OI-13, [OI-15](sCure_SRS.html#oi-15) to OI-28. | [§12](sCure_SRS.html#open) |

Not recorded: OI-2 to OI-5 and OI-14 are not in revision 1.0. The history does not show when or why they closed.

### 3.1 Edits on 2026-09-09 (document still revision 1.0)

| SRS area | Change | SRS |
|---|---|---|
| Home | The program time is an estimate of the real run, "~N min". It adds the step holds, the heating ramps and the cooling time. | [§6.7.3](sCure_SRS.html#sec-estimate) |
| Home | The estimate uses measured rates: 13, 50 and 80 s per °C for heating, and fixed cooling rates per mode. | [§6.7.3](sCure_SRS.html#sec-estimate) |
| Cure Process | New table for the UV wavelength selection: the LED_SWITCH relay, two SSRs and GPIO17. The relay moves first, then the SSRs, then the PWM. | [§7.4](sCure_SRS.html#s-7-4) |
| Errors | New code 9001, critical: chamber, Left LED or Right LED sensor open for one minute. | [§9.14.1](sCure_SRS.html#s-9-14-1) |
| Errors | New code 9050, warning: Back LED or Door LED sensor open. The registry then has 39 codes. | [§9.14.1](sCure_SRS.html#s-9-14-1) |
| Data | The cure run records `sensor_issues`. A new endpoint records the real time of each phase. | [§7.3.8](sCure_SRS.html#s-7-3-8) |

## 4 Revision 2.0 (2026-10-23, sCure CS 1.0.106)

Revision 2.0 changed the whole document. The requirements now agree with the C# firmware sCureBox-CS 1.0.106, not with the earlier React and Flask software.

### 4.1 Introduction and process

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Process types | Four mechanisms, not defined (OI-1). | Six process types: Drying, Heating, Cure, Bleaching, Nitrogen, Cooling. Each has an end condition. OI-1 is closed. | [§1.2](sCure_SRS.html#s-1-2) |
| Remote access | GrabCAD showed the process. | sCure Cloud is the only remote channel. The question about GrabCAD is [OI-29](sCure_SRS.html#oi-29). | [§1.3](sCure_SRS.html#s-1-3) |

### 4.2 Setup

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Boot self-test | Not specified. | Six checks at each power-on: door, temperature sensors, 405 nm LEDs, 450 nm LEDs, fans, firmware API. | [§3.3.1](sCure_SRS.html#s-3-3-1) |
| Self-test result | Not specified. | A failure gives Retry or Continue anyway. It gives no alert ([OI-33](sCure_SRS.html#oi-33)). A planned restart within 10 minutes does not do the LED and fan checks. | [§3.3.1](sCure_SRS.html#s-3-3-1) |
| SN source | Cloud Service, with SD restore. | The operator scans the SN barcode with a USB scanner. The SN has 3 to 40 characters. | [§3.3.4](sCure_SRS.html#s-3-3-4) |
| SN manual entry | Not specified. | Ten taps and the device password let a service person type the SN. | [§3.3.4](sCure_SRS.html#s-3-3-4) |
| Cloud steps | Internet check, cloud SN request, cloud registration. | The firmware does not do these steps. Codes 3001, 3002 and 3003 are not used ([OI-30](sCure_SRS.html#oi-30)). | [§3.3.4](sCure_SRS.html#s-3-3-4) |
| Configuration storage | `/etc/scure/config.json` and an SD backup. | `ui-settings.json` in `/var/lib/scurebox`, and the factory file `system.json`. There is no SD backup. OI-6 is closed as obsolete. | [§3.5](sCure_SRS.html#s-3-5) |
| Save fault | The unit shows an error and stops. | The unit only writes the fault to the log ([OI-31](sCure_SRS.html#oi-31)). | [§3.5](sCure_SRS.html#s-3-5) |
| Setup Name | Default "S-Cure" (OI-7). | Default "sCure". OI-7 is closed. | [§4.3.1](sCure_SRS.html#s-4-3-1) |
| Connect Organization | CSV file only. | CSV file or Sign in with Origin ([OI-34](sCure_SRS.html#oi-34)). | [§5.3.1](sCure_SRS.html#s-5-3-1) |

### 4.3 Home

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Start gates | Nitrogen-only check only (OI-13). | An active critical alert, an open door and the nitrogen-only check stop the start. Then a pre-check tests all fans. OI-13 is closed. | [§6.8](sCure_SRS.html#s-6-8) |
| Fan pre-check | Not specified. | A failed fan gives "Fan failure". The operator can select Cancel or Continue anyway. | [§6.8](sCure_SRS.html#s-6-8) |
| Machine start checks | Not specified. | The machine refuses a start that fails the program rules. A refusal gives 6015 or its own code. | [§9.5.1](sCure_SRS.html#s-9-5-1) |
| Step time | The builder showed a step time, but OI-17 said that the time was removed. The two texts did not agree. | Steps have a hold time: 1 to 120 min, Bleaching 1 to 720 min. OI-17 is closed as obsolete. | [§6.7.2](sCure_SRS.html#sec-step-rules) |
| Presets | Not listed. | Six presets. Some do not obey the program rules (OI-35). | [§6.5](sCure_SRS.html#s-6-5) |
| Selection | The first program was selected at load. | No program is selected at load. | [§6.5](sCure_SRS.html#s-6-5) |
| Print history | Written to PostgreSQL. | Prints come from sCure Cloud or from the API. A finished cure does not add a print ([OI-12](sCure_SRS.html#oi-12)). | [§6.4](sCure_SRS.html#s-6-4) |

### 4.4 Cure Process

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Run control | The screen controlled the run. | The firmware controls the run. The screen and the HTTP API use the same run. | [§7.3.1](sCure_SRS.html#s-7-3-1) |
| Run states | Not specified. | idle, preflight, running, paused, completed, aborted, error. | [§7.3.1](sCure_SRS.html#s-7-3-1) |
| Operator actions | Abort only. | Pause, Continue and Abort on the screen. Skip only through the API. | [§7.3.5](sCure_SRS.html#s-7-3-5) |
| Timer Start and UV Start | Not applied (OI-16). | Applied at run time. OI-16 is closed. | [§7.3.3](sCure_SRS.html#s-7-3-3) |
| Checks on the screen | Stall check (7004). | Also door open, frozen temperature value (9006), chamber sensor (9010), fan failure and LED panel checks. These checks are only on the screen ([OI-47](sCure_SRS.html#oi-47)). | [§7.3.6](sCure_SRS.html#s-7-3-6) |
| Door open | Door locked during the run. | The door watchdog stops the run after 10 s (6016). The screen says "Paused" but the run continues ([OI-42](sCure_SRS.html#oi-42)). | [§9.14.6](sCure_SRS.html#s-9-14-6) |
| Run record | Start, telemetry, finish. | Telemetry every 2 s, phase times, alerts in the run, sensor and fan issues. The unit keeps 25 runs. | [§7.3.8](sCure_SRS.html#s-7-3-8) |

### 4.5 Cure History

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Actions | Read-only. Download report. | Detail panel, Export report to USB, Delete a run, Delete all. | [§8.3](sCure_SRS.html#s-8-3) |
| Cloud | Not specified. | A deleted run is also deleted from sCure Cloud at the next sync. | [§8.3.3](sCure_SRS.html#s-8-3-3) |
| Retention | Not specified. | The newest 25 runs. | [§8.3](sCure_SRS.html#s-8-3) |
| Report file name | Not specified. | Two different names, one for each export path ([OI-49](sCure_SRS.html#oi-49)). | [§8.3.2](sCure_SRS.html#s-8-3-2) |

### 4.6 Errors and error registry

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Registry file | `public/config/errors.json`. | `sCureBox-CS/config/errors.json`, registry 4.0.0. | [§9.9](sCure_SRS.html#s-9-9) |
| Number of codes | 39. | 76. | [§9.11](sCure_SRS.html#s-9-11) |
| Code structure | Group codes, for example 9001 for all sensors. | One code for each part. 9001 to 9005, 9050 and 9051 are now family titles only. | [§9.3](sCure_SRS.html#s-9-3) |
| New codes | Not applicable. | 6016 (door watchdog), 9002 to 9007, 9010 to 9014, 9020 to 9025, 9030 to 9034, 9040 to 9045, 9051, 9052, 9060 to 9065. | [§9.11.6](sCure_SRS.html#s-9-11-6) |
| Severity change | 9082 was critical. | 9082 is a warning. | [§9.5](sCure_SRS.html#s-9-5) |
| Stop rule | Open (OI-19). | §9.5.1 gives the two gates: the Start Cure gate and the machine check before each step. OI-19 is closed. | [§9.5.1](sCure_SRS.html#s-9-5-1) |
| Error codes in the API | Free text (OI-18). | A refusal gives its registry code or 6015. OI-18 is closed. Unused codes are now [OI-59](sCure_SRS.html#oi-59). | [§9.4](sCure_SRS.html#s-9-4) |
| Alert clear | Only by the operator (OI-20). | The machine clears most codes. The screen keeps them until the operator closes them ([OI-61](sCure_SRS.html#oi-61)). | [§9.6](sCure_SRS.html#s-9-6) |
| Demo alerts | Seeded (OI-21). | No demo alerts. OI-21 is closed. | [§9.7](sCure_SRS.html#s-9-7) |

### 4.7 Data

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Storage | PostgreSQL only. HTTP 503 without it. | JSON files in the data directory are the default. PostgreSQL is optional ([OI-65](sCure_SRS.html#oi-65)). | [§10.1](sCure_SRS.html#s-10-1) |
| Tables | Normalized tables (OI-23, OI-24). | The tables apply only to the optional PostgreSQL backend. OI-23 and OI-24 are replaced. | [§10.7](sCure_SRS.html#s-10-7) |
| Retention | Not specified. | §10.2 gives the store, write time, retention and power-loss effect for each data type. | [§10.2](sCure_SRS.html#s-10-2) |
| Reflash | Not specified. | A reflash erases all data on the unit ([OI-67](sCure_SRS.html#oi-67)). | [§10.5](sCure_SRS.html#s-10-5) |

### 4.8 Settings

| Topic | Before (1.0) | Now (2.0) | SRS |
|---|---|---|---|
| Damper, fans, BOFA | Screen only (OI-25). | The controls operate the hardware. OI-25 is closed. Feedback gaps are [OI-50](sCure_SRS.html#oi-50) and [OI-51](sCure_SRS.html#oi-51). | [§11.3](sCure_SRS.html#s-11-3) |
| Fan and LED tests | Simulated (OI-26). | Real tests. The LED test lights the panels and measures the temperature increase. OI-26 is closed. | [§11.3](sCure_SRS.html#s-11-3) |
| Nitrogen Mode | 6 bar minimum. The screen showed a fixed "2.0 bar" (OI-27). | Live pressure. 1 bar minimum ([OI-53](sCure_SRS.html#oi-53)). | [§11.3](sCure_SRS.html#s-11-3) |
| Date and time | Apply did not set the clock (OI-28). | Apply sets the system clock. Auto Sync and the time zone are [OI-54](sCure_SRS.html#oi-54). | [§11.3](sCure_SRS.html#s-11-3) |
| Lead On Time | Field with warning W/1053. | Removed. The firmware shows component hours ([OI-56](sCure_SRS.html#oi-56)). | [§11.3](sCure_SRS.html#s-11-3) |
| Developer Mode | Not specified. | Ten taps and a four-digit PIN. The PIN is the same on all units ([OI-57](sCure_SRS.html#oi-57)). | [§11.5](sCure_SRS.html#s-11-5) |
| NFC | On/off switch. | The switch is locked when there is no NFC reader. A switch-on without a reader gives 9052. | [§11.3](sCure_SRS.html#s-11-3) |

### 4.9 Open Issues in revision 2.0

- 41 new Open Issues: [OI-29](sCure_SRS.html#oi-29) to [OI-69](sCure_SRS.html#oi-69).
- 19 issues from revision 1.0 are closed, replaced or obsolete. These are OI-1, 6, 7, 9, 11, 13, 16 to 28. OI-18 and OI-20 are "largely resolved", and OI-28 is "partly resolved". Other OIs now hold the parts that remain.
- 4 issues stay open from revision 1.0: [OI-8](sCure_SRS.html#oi-8), [OI-10](sCure_SRS.html#oi-10), [OI-12](sCure_SRS.html#oi-12), [OI-15](sCure_SRS.html#oi-15).

## 5 Revision 2.1 (2026-11-03, sCure CS 1.0.141)

### 5.1 Setup

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| SN backup | No backup. | The SN has a second copy on a removable card. Codes 3001 and 4003 are used for the first time. | [§3.3.6](sCure_SRS.html#s-3-3-6) |
| Boot self-test | Six checks. | Seven checks. The new check is the N2 pressure sensor, with a wait of up to 20 s. | [§3.3.1](sCure_SRS.html#s-3-3-1) |
| OI-6 | Obsolete. | Opened again and resolved, because the backup is back. | OI-6 |

### 5.2 Home

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| Start a cure | A Start Cure button. | Swipe a row to the right. The swipe uses the same gates as the button. | [§6.6.4](sCure_SRS.html#sec-swipe) |
| Row actions | Edit mode. | Swipe a row to the left to open a tray: Duplicate, Edit, Delete. | [§6.7.5](sCure_SRS.html#sec-edit-mode) |
| Program List | Six presets. | The 19 materials of the Stratasys P3 catalog. Their parameters are placeholders ([OI-70](sCure_SRS.html#oi-70)). | [§6.5](sCure_SRS.html#s-6-5) |
| Diagrams | Not applicable. | The Home screenshots and two flow charts still show the old button ([OI-71](sCure_SRS.html#oi-71)). | [OI-71](sCure_SRS.html#oi-71) |

### 5.3 Cure Process

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| BOFA extraction | Manual switch. | The machine runs the BOFA unit with the air-intake fan. The 24 V supply and the presence line are monitored (9048). | [§9.14.10](sCure_SRS.html#s-9-14-10) |
| Connector | Not applicable. | The BOFA connector is not measured on a unit ([OI-72](sCure_SRS.html#oi-72)). | [OI-72](sCure_SRS.html#oi-72) |

### 5.4 Errors and error registry

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| Number of codes | 76. | 84. | [§9.11](sCure_SRS.html#s-9-11) |
| Nitrogen line | No monitor. | Window 0.5 to 3 bar. New codes: 9008 (too high), 9009 (no supply), 9015 (no flow), 9016 (sensor not read). | [§9.14.8](sCure_SRS.html#s-9-14-8) |
| Output watchdog | A trip gave no alert ([OI-64](sCure_SRS.html#oi-64)). | A trip gives 9017, latched until the operator acknowledges it. [OI-64](sCure_SRS.html#oi-64) is closed. | [§9.14.7](sCure_SRS.html#s-9-14-7) |
| UV-light confirmation | Not applicable. | The panel photoresistors confirm the light (9046, 9047). The limits are not calibrated ([OI-73](sCure_SRS.html#oi-73)). | [§9.14.9](sCure_SRS.html#s-9-14-9) |
| 7005 | Not used. | Used only after a firmware hang that the DVT causes. An operator abort still gives no code ([OI-46](sCure_SRS.html#oi-46)). | [§9.11.5](sCure_SRS.html#s-9-11-5) |

Edit on 2026-11-08 (no new revision number): Err 9007 (heater does not heat) applies only during the ramp up. When the chamber is within 1.5 °C of its target, the check stops. The check starts again at the next heating start or a new target.

### 5.5 Data

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| Software update | The update keeps the data directory and `components.json`. | Same. New limits that are not in the unit's own `components.json` use the built-in values. | [§10.5](sCure_SRS.html#s-10-5) |
| Reflash | A reflash erases all data. | A reflash erases all data, but the SN comes back from the card at the first start. | [§10.5](sCure_SRS.html#s-10-5) |

### 5.6 Settings

| Topic | Before (2.0) | Now (2.1) | SRS |
|---|---|---|---|
| Nitrogen Mode | 1 bar minimum. | The pressure must be in the 0.5 to 3 bar window. | [§11.3](sCure_SRS.html#s-11-3) |
| Work Without Network | Not applicable. | New switch. A unit that is offline on purpose shows no network alarms. | [§11.3](sCure_SRS.html#s-11-3) |

### 5.7 Open Issues in revision 2.1

- 5 new: [OI-70](sCure_SRS.html#oi-70) (placeholder recipes), [OI-71](sCure_SRS.html#oi-71) (old Home diagrams), [OI-72](sCure_SRS.html#oi-72) (BOFA not measured), [OI-73](sCure_SRS.html#oi-73) (UV thresholds), OI-74 (no removable medium on the Origin image).
- Closed or replaced: [OI-64](sCure_SRS.html#oi-64) (resolved by 1.0.110), OI-35 (replaced by [OI-70](sCure_SRS.html#oi-70)), OI-6 (opened again and resolved).
- Partly resolved: [OI-53](sCure_SRS.html#oi-53) (pressure window), [OI-43](sCure_SRS.html#oi-43) (nitrogen line check), [OI-31](sCure_SRS.html#oi-31) part (b) for the SN.

## 6 Revision 2.2, first part (2026-11-13, storage stick, sCure CS 1.0.184)

The owner decided on 2026-11-13 that the backup medium is a USB storage stick, because the CM5 has no SD card slot. This part changed only the sections for that topic. The other sections stayed as checked against 1.0.141.

| SRS area | Before (2.1) | Now (2.2, first part) | SRS |
|---|---|---|---|
| Setup | The SN backup was on a card at `/mnt/ssd2/scure`. That path does not exist on the Origin image (OI-74). | The SN backup is on a USB storage stick. The stick has the identity file `scure-storage.json`. | [§3.5.1](sCure_SRS.html#s-3-5-1) |
| Setup | Not applicable. | The first unit that writes to a new stick binds the stick to its SN. | [§3.5.1](sCure_SRS.html#s-3-5-1) |
| Setup | A unit with an SN did not use the backup. | A unit with an SN never takes the SN from a stick. | [§3.3.6](sCure_SRS.html#s-3-3-6) |
| Data | Only the SN had a backup. | The stick also keeps the user materials, the component counters and the newest 25 cure reports. | [§3.5.1](sCure_SRS.html#s-3-5-1) |
| Data | Not applicable. | The data directory stays the primary copy. A file comes back from the stick only if it is not in the data directory. | [§3.5.1](sCure_SRS.html#s-3-5-1) |
| Errors | 84 codes. | 85 codes. New code 4004: the stick belongs to a different unit. The unit does not read or write that stick. | [§9.11.2](sCure_SRS.html#s-9-11-2) |
| Settings | Not applicable. | CSV import and exports do not show the storage stick. | [§11.3](sCure_SRS.html#s-11-3) |
| Open Issues | OI-74 open. | OI-74 is closed. [OI-67](sCure_SRS.html#oi-67) and [OI-31](sCure_SRS.html#oi-31) are partly settled. | OI-74 |

## 7 Revision 2.2, second part (2026-11-17, sCure CS 1.0.229)

### 7.1 Setup

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| LED checks in the boot self-test | 405 nm: 15 s and 0.8 °C. | First, all panels cool to 30 °C. Then 405 nm: 20 s and 1.0 °C. 450 nm: 30 s and 0.8 °C. | [§3.3.1](sCure_SRS.html#s-3-3-1) |
| Boot time | Not applicable. | A full self-test on a warm unit can take more than 20 minutes ([OI-83](sCure_SRS.html#oi-83)). | [OI-83](sCure_SRS.html#oi-83) |
| Fan check | A failed fan did not give an alarm. | The boot fan test gives the alarm of that fan. | [§3.3.1](sCure_SRS.html#s-3-3-1) |

### 7.2 Home

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| Organization HUB | Not applicable. | An offline unit can read the recent prints of its organization from a HUB on the local network. | [§6.4](sCure_SRS.html#s-6-4) |
| HUB types | Not applicable. | A PC with the sCure Hub, or an on-premises Origin print server. The HUB is read-only. | [§6.4](sCure_SRS.html#s-6-4) |
| Print filter | All prints. | Recent Prints and View All show only prints whose material agrees with a cure program. Case and spaces are ignored. | [§6.4](sCure_SRS.html#s-6-4) |
| Print time | The stored duration. | A print shows the time of its program. | [§6.4](sCure_SRS.html#s-6-4) |
| Remote actions | Not applicable. | sCure Cloud can delete a print. A job sent with an NFC tag starts when the operator shows the tag. | [§6.4](sCure_SRS.html#s-6-4) |

### 7.3 Cure Process

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| LED-fan check | The check was not done for 30 s after a pass. | The LED-fan check runs at every start (since 1.0.196). | [§7.3.6](sCure_SRS.html#s-7-3-6) |
| UV-light confirmation | On. | Off by default (since 1.0.199). | [§9.14.9](sCure_SRS.html#s-9-14-9) |
| Events | 7004 also occurred for each new heater or cooling fault. | One event for each fault. 7004 is only for a fault without its own code (since 1.0.194). | [§9.14.4](sCure_SRS.html#s-9-14-4) |
| Live display | A finished card showed "Done". | A finished card shows DONE in a full green ring, with the time of the phase. | [§7.3.4](sCure_SRS.html#s-7-3-4) |
| Status strip | It showed the internet state. | It does not show the internet state. | [§6.3](sCure_SRS.html#s-6-3) |

### 7.4 Errors and error registry

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| Number of codes | 85. | 85. There are no new codes. | [§9.11](sCure_SRS.html#s-9-11) |
| 9013 and 9014 | Warning. The Back and Door LED sensors did not stop a start. | Critical. The unit cannot start a cure without these sensors. | [§9.14.1](sCure_SRS.html#s-9-14-1) |
| 9050 | Warning. | Critical. The registry description still says "warning" ([OI-80](sCure_SRS.html#oi-80)). | [OI-80](sCure_SRS.html#oi-80) |
| Fan tests | A failed test did not give an alarm. | Settings, pre-check and boot fan tests give the alarm of that fan. | [§9.14.2](sCure_SRS.html#s-9-14-2) |
| Chamber Intake Fan | The same limits as the other fans. | The fan has its own wear and stop limits, for damper open and damper closed. | [§9.14.2](sCure_SRS.html#s-9-14-2) |
| Language of errors | English only. | The error texts on the screen are translated. The registry stays in English. | [§11.3](sCure_SRS.html#s-11-3) |

### 7.5 Data

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| Counters | Five counters. | A sixth counter for the LED cooling fans (since 1.0.207). | [§10.2](sCure_SRS.html#s-10-2) |
| HUB address | Not applicable. | Kept in `hub.json`. | [§10.2](sCure_SRS.html#s-10-2) |
| Damper angles | Not applicable. | Kept on the unit, not on the storage stick ([OI-79](sCure_SRS.html#oi-79)). | [OI-79](sCure_SRS.html#oi-79) |

### 7.6 Settings

| Topic | Before | Now (2.2) | SRS |
|---|---|---|---|
| Language | English only. | Settings › Language lists ten languages. Hebrew mirrors the layout. Nine languages are machine-translated drafts ([OI-78](sCure_SRS.html#oi-78)). | [§11.3](sCure_SRS.html#s-11-3) |
| Damper | OPEN and CLOSE only. | New Calibrate control. It uses the Chamber Intake Fan speed to find the open and closed angles. | [§11.3](sCure_SRS.html#s-11-3) |
| LED test | 15 s and 0.8 °C at 405 nm. | Pre-cool to 30 °C, then 20 s and 1.0 °C at 405 nm. | [§11.3](sCure_SRS.html#s-11-3) |
| Organization HUB | Not applicable. | New row, shown only when the unit works without a network. | [§11.3](sCure_SRS.html#s-11-3) |
| Test lock | Not specified. | The Settings controls are locked while a test runs. | [§11.3](sCure_SRS.html#s-11-3) |
| Developer Tools | LED and HDT calibration. | The ATP Tool is added (since 1.0.222). | [§11.5](sCure_SRS.html#s-11-5) |

### 7.7 Open Issues in revision 2.2

- 10 new: [OI-75](sCure_SRS.html#oi-75) to [OI-84](sCure_SRS.html#oi-84).
- Closed: OI-38 (print duration unit, 1.0.148).
- Main fault resolved: [OI-54](sCure_SRS.html#oi-54) (network time, 1.0.142 and 1.0.144). Parts (a) to (c) stay open.
- Opened again: [OI-64](sCure_SRS.html#oi-64). [OI-84](sCure_SRS.html#oi-84) continues it.

## 8 Latest change: OI-64 open again and new OI-84 (2026-11-17)

Revision 2.1 closed [OI-64](sCure_SRS.html#oi-64). It said that a watchdog trip always gives Err 9017. The last edit of revision 2.2 records that this is not true for a real trip.

| Item | Text in revision 2.2 | SRS |
|---|---|---|
| Fault | The watchdog cuts the heaters and the UV LEDs and writes a trip record. The firmware reads the record only during the DVT hang test. | [OI-84](sCure_SRS.html#oi-84) |
| Effect | After a real hang or crash, the outputs are off and the run stops. No 9017 occurs, and the operator does not know the cause. | [OI-84](sCure_SRS.html#oi-84) |
| Record storage | The record is in memory storage (`/run` or `/dev/shm`). A reboot erases it. | [§9.14.7](sCure_SRS.html#s-9-14-7) |
| Question ([OI-84](sCure_SRS.html#oi-84)) | Must the firmware read the record at each start and after each recovery and give 9017? Must the record stay after a reboot? | [OI-84](sCure_SRS.html#oi-84) |

Planned fix, not yet in the SRS: firmware 1.0.230 (WatchdogTripMonitor) is in work. It is not in revision 2.2, and it is not installed on a unit.

## 9 Revision 2.3, draft (2026-11-18, sCure CS 1.0.236)

| SRS area | Before (2.2) | Now (2.3 draft) | SRS |
|---|---|---|---|
| Setup | A unit with no storage stick gave no message. Err 4003 occurred only when the unit wrote its SN. | A unit that finished Setup and has no storage stick gives the warning Err 4005 "Storage Stick Missing". | [§3.5.1](sCure_SRS.html#req-stick-missing) |
| Setup | Not applicable. | Err 4005 does not block anything. Start Cure, Settings and exports stay available. Only the backup copies are not written. | [§3.5.1](sCure_SRS.html#req-stick-missing) |
| Setup | Not applicable. | The unit checks the stick 30 s after start, then every 10 s. There is one alert for each absence. The alert closes by itself when the stick is back. | [§3.5.1](sCure_SRS.html#req-stick-missing) |
| Errors | 85 codes. | 86 codes. New code 4005, warning, in all ten languages. | [§9.11.2](sCure_SRS.html#s-9-11-2) |
| Settings | The language rules were one row of §11.3. There were no locale rules. | New §11.8 with the language requirements LNG-01 to LNG-12. | [§11.8.1](sCure_SRS.html#s-11-8-1) |
| Settings | Not specified. | New locale requirements LOC-01 to LOC-07 (owner decision 2026-11-18): dates, times and numbers follow the language (e.g. 18.11.2026, 24,5 in German), a 24-hour clock switch with a 12-hour option, a keyboard for each language (Hebrew, European letters, Korean, Japanese kana, Chinese pinyin). The HUB address takes digits and dots only. The language can be chosen on the first Setup screen. | [§11.8.2](sCure_SRS.html#s-11-8-2) |
| Setup | The language could be chosen only in Settings. | The Welcome screen of Setup offers the language list; a new unit can be set up in the operator's language (1.0.232). | [§3.3.3](sCure_SRS.html#s-3-3-3) |
| Settings | No clock choice; 24-hour times. | New switch "24-hour clock"; off = 12-hour times (2:05 PM). The language decides until it is changed (1.0.232). | [§11.3](sCure_SRS.html#s-11-3) |
| Settings | The HUB address was typed on the full keyboard, optionally with a port. | The HUB address is entered on a number pad (digits and dots); OK only for a whole IPv4 address; the HUB is read on port 80 (1.0.233). | [§11.3](sCure_SRS.html#s-11-3) |
| Setup | Not applicable. | The hardware simulator has a storage stick to plug in and pull out, to show Err 4005 (1.0.233, simulator only). | [§3.5.1](sCure_SRS.html#s-3-5-1) |
| Settings | The only way back to Setup was Unlink, open to everyone; it cleared only the organization. | Developer Mode has a factory reset for production: it deletes the history, reports, alerts and counters, clears the organization and the name, resets every setting and keeps the SN; the screen restarts at Setup (1.0.234). | [§11.5](sCure_SRS.html#req-factory-reset) |
| Cure Process | A heated step that started above its target ended its ramp at once and held too hot. | It first cools to its target in Fast mode (phase "precooling"); the ramp, the timer and the UV start at the target (1.0.235). | [§7.3.3](sCure_SRS.html#req-precool) |
| Home | The program time was counted from 25 °C. | It is counted from the real chamber temperature on Home and at Start, including the pre-cool (1.0.235). | [§6.7.3](sCure_SRS.html#sec-estimate) |
| Cure Process | In Bleaching only the lit panel's LED fan ran (the door). | In Bleaching all four LED cooling fans run at 30 % while any LED is lit (1.0.236). | [§7.4](sCure_SRS.html#req-bleach-fans) |
| Open Issues | 57 open. | 57 open. OI-85 (locale) was opened and closed in this revision by the owner's decisions. | OI-85 |

Not in revision 2.3: the watchdog fix of firmware 1.0.230. The SRS still gives [OI-84](sCure_SRS.html#oi-84) as open.
