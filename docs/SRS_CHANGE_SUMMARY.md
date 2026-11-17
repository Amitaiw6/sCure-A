# sCure Box SRS: Change Summary, Revision 1.0 to Revision 2.2

Written in ASD-STE100 Simplified Technical English, Issue 9.

Hebrew version: [SRS_CHANGE_SUMMARY.he.md](SRS_CHANGE_SUMMARY.he.md)

## 1 Purpose

This document gives the changes to the sCure Box Software Requirements Specification (SRS). It starts at the first revision (1.0) and stops at revision 2.2. Revision 2.2 has the date 2026-11-17 and agrees with the firmware sCure CS 1.0.229.

The readers are the software, QA and systems teams. For each revision, the document tells what changed in the requirements, area by area. It does not give a software change log.

The sources are the SRS file `docs/sCure_SRS.html` and its git history. Other sources are `sCureBox-CS/CHANGE_SUMMARY.md` and `sCureBox-CS/config/versions.json`. When the sources do not show a fact clearly, this document says "not recorded".

## 2 Revisions

| Revision | Date | Firmware checked against | Scope |
|---|---|---|---|
| 1.0 | 2026-07-05 | Not recorded. The text refers to the React UI and the Flask server of sCure-A. | First release. It gives the screen logic and the error registry. Many items are Open Issues. |
| 1.0 (edit, no new number) | 2026-09-09 | sCure-A v0.8.39 and v0.8.40 (from the git commit messages) | Program time estimate, UV wavelength order, temperature-sensor alarms 9001 and 9050. |
| 2.0 | 2026-10-23 | sCure CS 1.0.106 | All sections agree with the new C# firmware. Flow charts are new. All Open Issues were checked again. |
| 2.1 | 2026-11-03 | sCure CS 1.0.141 | Nitrogen line monitor, serial number backup, BOFA extraction, UV-light confirmation, watchdog alarm 9017, swipe Home, P3 catalog, offline unit. |
| 2.1 (edit, no new number) | 2026-11-08 | scurebox-cs 1.0.152 (from the git commit message) | Err 9007 applies only during the ramp up. |
| 2.2 (first part) | 2026-11-13 | sCure CS 1.0.184, for the storage stick only | The backup medium is a USB storage stick. New code 4004. |
| 2.2 (second part) | 2026-11-17 | sCure CS 1.0.229 | Organization HUB, UI languages, damper calibration, LED test changes, sensor severity changes, ten new Open Issues. |
| 2.2 (edit) | 2026-11-17 | sCure CS 1.0.229 | OI-64 is open again. New OI-84: a real watchdog trip does not give Err 9017. |

Notes:

- The git history starts on 2026-07-22. The first commit of `docs/sCure_SRS.html` already has revision 1.0 with the date 2026-07-05.
- Before 2026-07-22, the repository had a different document, `docs/SRS.md` (SRS-SCURE-2026-001, version 1.1.0). That commit removed it. This summary does not include it.
- The document text of revision 2.1 has the date 2026-11-03. Git received it on 2026-11-08.
- The edits on 2026-09-09 and 2026-11-08 have no row in the revision table of the SRS.

## 3 Revision 1.0: the first release (baseline)

Revision 1.0 gave the purpose and the logic of each screen. The file `sCure-UI.html` was the reference for the user interface. Many requirements were not complete and were Open Issues.

| SRS area | Requirements in revision 1.0 |
|---|---|
| Process | Four mechanisms with the names Drying, Heating, Curing and Cooling. Their sequence and parameters were not defined (OI-1). |
| Remote access | The process data went to the cloud and GrabCAD showed it to the user. |
| Setup | The unit read the serial number (SN) from Storage, then from an SD backup. If there was no SN, the unit got one from a Cloud Service. |
| Setup | The unit tried the cloud request up to five times. Then it registered itself in the cloud. |
| Setup | The SN went to `/etc/scure/config.json`. The backup went to `/mnt/ssd2/scure/config_backup.json` on the SD card. |
| Setup Name | The default name was "S-Cure" (OI-7). The only rule was "not empty" (OI-8). The name also went to the SD backup. |
| Connect Organization | The user loaded a CSV file from a USB drive. The first UUID in the file became the organization ID. The status of this section was "not finalized". |
| Home | A fixed Start Cure button started the cure. An Edit button showed Duplicate, Edit and Delete on each row. |
| Home | The only start gate was the nitrogen-only program check. Door and pre-cure checks were open (OI-13). |
| Home | The builder gave each step a temperature and a time. OI-17 said that the step time was removed. The two texts did not agree. |
| Home | The program time was the sum of the step times. |
| Cure Process | The screen controlled the run. A 1 s tick moved the ramp and the timers. |
| Cure Process | The screen did a stall check (7004). The Timer Start and UV Start options were not applied (OI-16). |
| Cure History | The screen was read-only. It had a Download report button. The operator could not delete a run. |
| Errors | One registry, `public/config/errors.json`, with 37 codes in the ranges 3xxx to 9xxx. The first digit is the SRS section. |
| Errors | There were two severities, critical and warning. The rule that tells which fault stops a run was open (OI-19). |
| Data | All data was in a PostgreSQL database. Without the database, the API gave HTTP 503. |
| Settings | Damper, fan sliders and BOFA changed only the screen (OI-25). The fan and LED tests were simulated (OI-26). |
| Settings | Nitrogen Mode had a 6 bar minimum, but the screen showed a fixed "2.0 bar" (OI-27). The manual clock did not change the system clock (OI-28). |
| Open Issues | 23 open items: OI-1, OI-6 to OI-13, OI-15 to OI-28. |

Not recorded: OI-2 to OI-5 and OI-14 are not in revision 1.0. The history does not show when or why they closed.

### 3.1 Edits on 2026-09-09 (document still revision 1.0)

| SRS area | Change |
|---|---|
| Home | The program time is an estimate of the real run, "~N min". It adds the step holds, the heating ramps and the cooling time. |
| Home | The estimate uses measured rates: 13, 50 and 80 s per °C for heating, and fixed cooling rates per mode. |
| Cure Process | New table for the UV wavelength selection: the LED_SWITCH relay, two SSRs and GPIO17. The relay moves first, then the SSRs, then the PWM. |
| Errors | New code 9001, critical: chamber, Left LED or Right LED sensor open for one minute. |
| Errors | New code 9050, warning: Back LED or Door LED sensor open. The registry then has 39 codes. |
| Data | The cure run records `sensor_issues`. A new endpoint records the real time of each phase. |

## 4 Revision 2.0 (2026-10-23, sCure CS 1.0.106)

Revision 2.0 changed the whole document. The requirements now agree with the C# firmware sCureBox-CS 1.0.106, not with the earlier React and Flask software.

### 4.1 Introduction and process

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Process types | Four mechanisms, not defined (OI-1). | Six process types: Drying, Heating, Cure, Bleaching, Nitrogen, Cooling. Each has an end condition. OI-1 is closed. |
| Remote access | GrabCAD showed the process. | sCure Cloud is the only remote channel. The question about GrabCAD is OI-29. |

### 4.2 Setup

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Boot self-test | Not specified. | Six checks at each power-on: door, temperature sensors, 405 nm LEDs, 450 nm LEDs, fans, firmware API. |
| Self-test result | Not specified. | A failure gives Retry or Continue anyway. It gives no alert (OI-33). A planned restart within 10 minutes does not do the LED and fan checks. |
| SN source | Cloud Service, with SD restore. | The operator scans the SN barcode with a USB scanner. The SN has 3 to 40 characters. |
| SN manual entry | Not specified. | Ten taps and the device password let a service person type the SN. |
| Cloud steps | Internet check, cloud SN request, cloud registration. | The firmware does not do these steps. Codes 3001, 3002 and 3003 are not used (OI-30). |
| Configuration storage | `/etc/scure/config.json` and an SD backup. | `ui-settings.json` in `/var/lib/scurebox`, and the factory file `system.json`. There is no SD backup. OI-6 is closed as obsolete. |
| Save fault | The unit shows an error and stops. | The unit only writes the fault to the log (OI-31). |
| Setup Name | Default "S-Cure" (OI-7). | Default "sCure". OI-7 is closed. |
| Connect Organization | CSV file only. | CSV file or Sign in with Origin (OI-34). |

### 4.3 Home

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Start gates | Nitrogen-only check only (OI-13). | An active critical alert, an open door and the nitrogen-only check stop the start. Then a pre-check tests all fans. OI-13 is closed. |
| Fan pre-check | Not specified. | A failed fan gives "Fan failure". The operator can select Cancel or Continue anyway. |
| Machine start checks | Not specified. | The machine refuses a start that fails the program rules. A refusal gives 6015 or its own code. |
| Step time | The builder showed a step time, but OI-17 said that the time was removed. The two texts did not agree. | Steps have a hold time: 1 to 120 min, Bleaching 1 to 720 min. OI-17 is closed as obsolete. |
| Presets | Not listed. | Six presets. Some do not obey the program rules (OI-35). |
| Selection | The first program was selected at load. | No program is selected at load. |
| Print history | Written to PostgreSQL. | Prints come from sCure Cloud or from the API. A finished cure does not add a print (OI-12). |

### 4.4 Cure Process

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Run control | The screen controlled the run. | The firmware controls the run. The screen and the HTTP API use the same run. |
| Run states | Not specified. | idle, preflight, running, paused, completed, aborted, error. |
| Operator actions | Abort only. | Pause, Continue and Abort on the screen. Skip only through the API. |
| Timer Start and UV Start | Not applied (OI-16). | Applied at run time. OI-16 is closed. |
| Checks on the screen | Stall check (7004). | Also door open, frozen temperature value (9006), chamber sensor (9010), fan failure and LED panel checks. These checks are only on the screen (OI-47). |
| Door open | Door locked during the run. | The door watchdog stops the run after 10 s (6016). The screen says "Paused" but the run continues (OI-42). |
| Run record | Start, telemetry, finish. | Telemetry every 2 s, phase times, alerts in the run, sensor and fan issues. The unit keeps 25 runs. |

### 4.5 Cure History

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Actions | Read-only. Download report. | Detail panel, Export report to USB, Delete a run, Delete all. |
| Cloud | Not specified. | A deleted run is also deleted from sCure Cloud at the next sync. |
| Retention | Not specified. | The newest 25 runs. |
| Report file name | Not specified. | Two different names, one for each export path (OI-49). |

### 4.6 Errors and error registry

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Registry file | `public/config/errors.json`. | `sCureBox-CS/config/errors.json`, registry 4.0.0. |
| Number of codes | 39. | 76. |
| Code structure | Group codes, for example 9001 for all sensors. | One code for each part. 9001 to 9005, 9050 and 9051 are now family titles only. |
| New codes | Not applicable. | 6016 (door watchdog), 9002 to 9007, 9010 to 9014, 9020 to 9025, 9030 to 9034, 9040 to 9045, 9051, 9052, 9060 to 9065. |
| Severity change | 9082 was critical. | 9082 is a warning. |
| Stop rule | Open (OI-19). | §9.5.1 gives the two gates: the Start Cure gate and the machine check before each step. OI-19 is closed. |
| Error codes in the API | Free text (OI-18). | A refusal gives its registry code or 6015. OI-18 is closed. Unused codes are now OI-59. |
| Alert clear | Only by the operator (OI-20). | The machine clears most codes. The screen keeps them until the operator closes them (OI-61). |
| Demo alerts | Seeded (OI-21). | No demo alerts. OI-21 is closed. |

### 4.7 Data

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Storage | PostgreSQL only. HTTP 503 without it. | JSON files in the data directory are the default. PostgreSQL is optional (OI-65). |
| Tables | Normalized tables (OI-23, OI-24). | The tables apply only to the optional PostgreSQL backend. OI-23 and OI-24 are replaced. |
| Retention | Not specified. | §10.2 gives the store, write time, retention and power-loss effect for each data type. |
| Reflash | Not specified. | A reflash erases all data on the unit (OI-67). |

### 4.8 Settings

| Topic | Before (1.0) | Now (2.0) |
|---|---|---|
| Damper, fans, BOFA | Screen only (OI-25). | The controls operate the hardware. OI-25 is closed. Feedback gaps are OI-50 and OI-51. |
| Fan and LED tests | Simulated (OI-26). | Real tests. The LED test lights the panels and measures the temperature increase. OI-26 is closed. |
| Nitrogen Mode | 6 bar minimum. The screen showed a fixed "2.0 bar" (OI-27). | Live pressure. 1 bar minimum (OI-53). |
| Date and time | Apply did not set the clock (OI-28). | Apply sets the system clock. Auto Sync and the time zone are OI-54. |
| Lead On Time | Field with warning W/1053. | Removed. The firmware shows component hours (OI-56). |
| Developer Mode | Not specified. | Ten taps and a four-digit PIN. The PIN is the same on all units (OI-57). |
| NFC | On/off switch. | The switch is locked when there is no NFC reader. A switch-on without a reader gives 9052. |

### 4.9 Open Issues in revision 2.0

- 41 new Open Issues: OI-29 to OI-69.
- 19 issues from revision 1.0 are closed, replaced or obsolete. These are OI-1, 6, 7, 9, 11, 13, 16 to 28. OI-18 and OI-20 are "largely resolved", and OI-28 is "partly resolved". Other OIs now hold the parts that remain.
- 4 issues stay open from revision 1.0: OI-8, OI-10, OI-12, OI-15.

## 5 Revision 2.1 (2026-11-03, sCure CS 1.0.141)

### 5.1 Setup

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| SN backup | No backup. | The SN has a second copy on a removable card. Codes 3001 and 4003 are used for the first time. |
| Boot self-test | Six checks. | Seven checks. The new check is the N2 pressure sensor, with a wait of up to 20 s. |
| OI-6 | Obsolete. | Opened again and resolved, because the backup is back. |

### 5.2 Home

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| Start a cure | A Start Cure button. | Swipe a row to the right. The swipe uses the same gates as the button. |
| Row actions | Edit mode. | Swipe a row to the left to open a tray: Duplicate, Edit, Delete. |
| Program List | Six presets. | The 19 materials of the Stratasys P3 catalog. Their parameters are placeholders (OI-70). |
| Diagrams | Not applicable. | The Home screenshots and two flow charts still show the old button (OI-71). |

### 5.3 Cure Process

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| BOFA extraction | Manual switch. | The machine runs the BOFA unit with the air-intake fan. The 24 V supply and the presence line are monitored (9048). |
| Connector | Not applicable. | The BOFA connector is not measured on a unit (OI-72). |

### 5.4 Errors and error registry

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| Number of codes | 76. | 84. |
| Nitrogen line | No monitor. | Window 0.5 to 3 bar. New codes: 9008 (too high), 9009 (no supply), 9015 (no flow), 9016 (sensor not read). |
| Output watchdog | A trip gave no alert (OI-64). | A trip gives 9017, latched until the operator acknowledges it. OI-64 is closed. |
| UV-light confirmation | Not applicable. | The panel photoresistors confirm the light (9046, 9047). The limits are not calibrated (OI-73). |
| 7005 | Not used. | Used only after a firmware hang that the DVT causes. An operator abort still gives no code (OI-46). |

Edit on 2026-11-08 (no new revision number): Err 9007 (heater does not heat) applies only during the ramp up. When the chamber is within 1.5 °C of its target, the check stops. The check starts again at the next heating start or a new target.

### 5.5 Data

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| Software update | The update keeps the data directory and `components.json`. | Same. New limits that are not in the unit's own `components.json` use the built-in values. |
| Reflash | A reflash erases all data. | A reflash erases all data, but the SN comes back from the card at the first start. |

### 5.6 Settings

| Topic | Before (2.0) | Now (2.1) |
|---|---|---|
| Nitrogen Mode | 1 bar minimum. | The pressure must be in the 0.5 to 3 bar window. |
| Work Without Network | Not applicable. | New switch. A unit that is offline on purpose shows no network alarms. |

### 5.7 Open Issues in revision 2.1

- 5 new: OI-70 (placeholder recipes), OI-71 (old Home diagrams), OI-72 (BOFA not measured), OI-73 (UV thresholds), OI-74 (no removable medium on the Origin image).
- Closed or replaced: OI-64 (resolved by 1.0.110), OI-35 (replaced by OI-70), OI-6 (opened again and resolved).
- Partly resolved: OI-53 (pressure window), OI-43 (nitrogen line check), OI-31 part (b) for the SN.

## 6 Revision 2.2, first part (2026-11-13, storage stick, sCure CS 1.0.184)

The owner decided on 2026-11-13 that the backup medium is a USB storage stick, because the CM5 has no SD card slot. This part changed only the sections for that topic. The other sections stayed as checked against 1.0.141.

| SRS area | Before (2.1) | Now (2.2, first part) |
|---|---|---|
| Setup | The SN backup was on a card at `/mnt/ssd2/scure`. That path does not exist on the Origin image (OI-74). | The SN backup is on a USB storage stick. The stick has the identity file `scure-storage.json`. |
| Setup | Not applicable. | The first unit that writes to a new stick binds the stick to its SN. |
| Setup | A unit with an SN did not use the backup. | A unit with an SN never takes the SN from a stick. |
| Data | Only the SN had a backup. | The stick also keeps the user materials, the component counters and the newest 25 cure reports. |
| Data | Not applicable. | The data directory stays the primary copy. A file comes back from the stick only if it is not in the data directory. |
| Errors | 84 codes. | 85 codes. New code 4004: the stick belongs to a different unit. The unit does not read or write that stick. |
| Settings | Not applicable. | CSV import and exports do not show the storage stick. |
| Open Issues | OI-74 open. | OI-74 is closed. OI-67 and OI-31 are partly settled. |

## 7 Revision 2.2, second part (2026-11-17, sCure CS 1.0.229)

### 7.1 Setup

| Topic | Before | Now (2.2) |
|---|---|---|
| LED checks in the boot self-test | 405 nm: 15 s and 0.8 °C. | First, all panels cool to 30 °C. Then 405 nm: 20 s and 1.0 °C. 450 nm: 30 s and 0.8 °C. |
| Boot time | Not applicable. | A full self-test on a warm unit can take more than 20 minutes (OI-83). |
| Fan check | A failed fan did not give an alarm. | The boot fan test gives the alarm of that fan. |

### 7.2 Home

| Topic | Before | Now (2.2) |
|---|---|---|
| Organization HUB | Not applicable. | An offline unit can read the recent prints of its organization from a HUB on the local network. |
| HUB types | Not applicable. | A PC with the sCure Hub, or an on-premises Origin print server. The HUB is read-only. |
| Print filter | All prints. | Recent Prints and View All show only prints whose material agrees with a cure program. Case and spaces are ignored. |
| Print time | The stored duration. | A print shows the time of its program. |
| Remote actions | Not applicable. | sCure Cloud can delete a print. A job sent with an NFC tag starts when the operator shows the tag. |

### 7.3 Cure Process

| Topic | Before | Now (2.2) |
|---|---|---|
| LED-fan check | The check was not done for 30 s after a pass. | The LED-fan check runs at every start (since 1.0.196). |
| UV-light confirmation | On. | Off by default (since 1.0.199). |
| Events | 7004 also occurred for each new heater or cooling fault. | One event for each fault. 7004 is only for a fault without its own code (since 1.0.194). |
| Live display | A finished card showed "Done". | A finished card shows DONE in a full green ring, with the time of the phase. |
| Status strip | It showed the internet state. | It does not show the internet state. |

### 7.4 Errors and error registry

| Topic | Before | Now (2.2) |
|---|---|---|
| Number of codes | 85. | 85. There are no new codes. |
| 9013 and 9014 | Warning. The Back and Door LED sensors did not stop a start. | Critical. The unit cannot start a cure without these sensors. |
| 9050 | Warning. | Critical. The registry description still says "warning" (OI-80). |
| Fan tests | A failed test did not give an alarm. | Settings, pre-check and boot fan tests give the alarm of that fan. |
| Chamber Intake Fan | The same limits as the other fans. | The fan has its own wear and stop limits, for damper open and damper closed. |
| Language of errors | English only. | The error texts on the screen are translated. The registry stays in English. |

### 7.5 Data

| Topic | Before | Now (2.2) |
|---|---|---|
| Counters | Five counters. | A sixth counter for the LED cooling fans (since 1.0.207). |
| HUB address | Not applicable. | Kept in `hub.json`. |
| Damper angles | Not applicable. | Kept on the unit, not on the storage stick (OI-79). |

### 7.6 Settings

| Topic | Before | Now (2.2) |
|---|---|---|
| Language | English only. | Settings › Language lists ten languages. Hebrew mirrors the layout. Nine languages are machine-translated drafts (OI-78). |
| Damper | OPEN and CLOSE only. | New Calibrate control. It uses the Chamber Intake Fan speed to find the open and closed angles. |
| LED test | 15 s and 0.8 °C at 405 nm. | Pre-cool to 30 °C, then 20 s and 1.0 °C at 405 nm. |
| Organization HUB | Not applicable. | New row, shown only when the unit works without a network. |
| Test lock | Not specified. | The Settings controls are locked while a test runs. |
| Developer Tools | LED and HDT calibration. | The ATP Tool is added (since 1.0.222). |

### 7.7 Open Issues in revision 2.2

- 10 new: OI-75 to OI-84.
- Closed: OI-38 (print duration unit, 1.0.148).
- Main fault resolved: OI-54 (network time, 1.0.142 and 1.0.144). Parts (a) to (c) stay open.
- Opened again: OI-64. OI-84 continues it.

## 8 Latest change: OI-64 open again and new OI-84 (2026-11-17)

Revision 2.1 closed OI-64. It said that a watchdog trip always gives Err 9017. The last edit of revision 2.2 records that this is not true for a real trip.

| Item | Text in revision 2.2 |
|---|---|
| Fault | The watchdog cuts the heaters and the UV LEDs and writes a trip record. The firmware reads the record only during the DVT hang test. |
| Effect | After a real hang or crash, the outputs are off and the run stops. No 9017 occurs, and the operator does not know the cause. |
| Record storage | The record is in memory storage (`/run` or `/dev/shm`). A reboot erases it. |
| Question (OI-84) | Must the firmware read the record at each start and after each recovery and give 9017? Must the record stay after a reboot? |

Planned fix, not yet in the SRS: firmware 1.0.230 (WatchdogTripMonitor) is in work. It is not in revision 2.2, and it is not installed on a unit.

## 9 Open Issues across all revisions

| Revision | New | Closed, replaced or obsolete | Open at the end of the revision |
|---|---|---|---|
| 1.0 | 23 (OI-1, OI-6 to OI-13, OI-15 to OI-28) | Not recorded (OI-2 to OI-5 and OI-14 are not in the document) | 23 |
| 2.0 | 41 (OI-29 to OI-69) | 19 | 45 |
| 2.1 | 5 (OI-70 to OI-74) | 2 (OI-35, OI-64). OI-6 was opened again and closed again. | 48 |
| 2.2, first part | 0 | 1 (OI-74) | 47 |
| 2.2, second part and edit | 10 (OI-75 to OI-84) | 1 (OI-38). OI-64 is open again. | 57 |

Totals: 79 numbered issues were opened. 22 are closed, replaced or obsolete. 57 are open now.

Notes:

- The SRS closed OI-18 and OI-20 as "largely resolved" and OI-28 as "partly resolved". These counts include them as closed. Other OIs hold the parts that remain.
- OI-64 closed in revision 2.1 and is open again in revision 2.2. It counts as open.
- Some open issues are partly settled: OI-31, OI-43, OI-53, OI-54, OI-67.

Important open issues for the teams:

| Issue | Topic | Why it is important |
|---|---|---|
| OI-84 (OI-64) | Watchdog trip | A real firmware hang gives no 9017. The operator does not know why the run stopped. |
| OI-47 | Monitor on the screen only | A run started through the API does not get the screen checks. |
| OI-42 | Door open in a run | The screen says "Paused" but the heater and UV stay on until the 10 s watchdog. |
| OI-63 | LED panel checks | The checks are off in the shipped configuration. A dark panel is not found during a cure. |
| OI-59 | Unused codes | 20 of the 85 codes are not used. The screens show their own text. |
| OI-61 | Screen alerts | A critical alert that the machine cleared still stops Start Cure until the operator closes it. |
| OI-70 | P3 recipes | The 19 catalog programs have placeholder parameters. |
| OI-30 | SN source | No cloud registration, no uniqueness check, and no way to correct an SN. |
| OI-57 | Developer PIN | One fixed PIN on all units, with no attempt limit. |
| OI-67 | Reflash | The storage stick keeps only part of the data. Calibration and settings are lost. |
| OI-75 | HUB sign-in | The firmware uses a fixed account and plain HTTP to the Origin print server. |
| OI-78 | Translations | Nine languages are drafts. They include safety texts. |

Important closures:

| Issue | Revision | Result |
|---|---|---|
| OI-1 | 2.0 | The six process types and their rules are specified. |
| OI-13 | 2.0 | Start Cure gates are specified: critical alert, door, fan pre-check, machine checks. |
| OI-19 | 2.0 | §9.5.1 gives the stop rule for each code. |
| OI-25, OI-26 | 2.0 | Settings controls and diagnostics operate the real hardware. |
| OI-74 | 2.2 | The backup medium is a USB storage stick. |
| OI-38 | 2.2 | The portal sends minutes. The unit keeps seconds. |
