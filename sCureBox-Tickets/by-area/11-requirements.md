## Requirements catalogue (SRS)

### Sources

| Tag | Document | Revision / written against | Role |
|---|---|---|---|
| **P** | `docs/sCure_SRS.html` | Revision 2.1, 2026-11-03, sCure CS firmware 1.0.141 | Product SRS the owner reviews; per screen (§1-§12) with the full error catalog and the Open Issues. Identical copy lives in `sCure-A/docs/sCure_SRS.html`; the two must stay identical. |
| **E** | `docs/06-srs.md` | Revision A, 2026-09-23, software 1.0.32 (some rows updated later, e.g. SRS-UI-14..18, SRS-STEP-14..16, §13 items 19-21) | Engineering SRS: architecture, Mermaid flows, numbered requirements `SRS-<area>-<n>` with source files, known gaps. |
| **Q** | `docs/03-ui-and-qa.md` | undated | React-era UI reuse rules, program validation summary, estimate, simulation model, QA layers. |
| **R** | `docs/srs/README.md` | Rev A (software 1.0.32) | Describes the generated Stratasys-template `.docx` (SRS-CUREBOXCTRL-RevA) and how it is rebuilt. |

The repo is at 1.0.152 and targets .NET 10; source E still says .NET 8 and 1.0.32, source P says 1.0.141. Where the sources disagree the row says so, and the disagreement is also listed in "Conflicts between sources" at the end. Nothing here is invented: each row restates one statement from a source.

### How to use this catalogue

* **Req id.** Ids that exist in a source are copied exactly: `ERR-01..26`, `DB-01..14` (P), `SRS-RUN-*`, `SRS-STEP-*`, `SRS-SAFE-*`, `SRS-VAL-*`, `SRS-UI-*`, `SRS-DATA-*`, `SRS-NFR-*` (E). A statement without an id gets `SRS-<chapter>-<n>`: `SRS-3-7` = product SRS (P) chapter 3, item 7; `SRS-E5-4` = engineering SRS (E) chapter 5, item 4; `SRS-Q-n` = 03-ui-and-qa.md; `SRS-R-n` = srs/README.md.
* **Area** says which part of the system owns the requirement: Domain, Hardware, Application-Process, Application-Platform, Dvt-Hdt, Api, Native UI, Kiosk-Web, Deploy-Ops.
* **Verified by** says how to prove it. The codes are:
  * `UT-Dom`, `UT-HW`, `UT-App`, `UT-UI`: xunit unit tests in `tests/SCureBox.{Domain,Hardware,Application,Ui}.Tests`. Domain tests use a fake `TimeProvider`; UI tests run Avalonia headless.
  * `IT-API`: in-process `WebApplicationFactory` integration test in simulation (`tests/SCureBox.Api.Tests`).
  * `QA-live`: a row in the shared QA table, run with `qa/qa-tool.html` or `node qa/run-qa.mjs --api http://<unit>:3001`. `qa/run-all.ps1` chains the build, all tests, a simulated server and the QA table.
  * `Bench`: measured on a real unit (scope, thermocouple, Ophir, tach), or a DVT test.
  * `Review`: checked by inspecting docs, config or the image.
  * `Build-gate`: enforced by a test that fails the build (for example `ErrorCoverageTests`).
* A ticket is done only when every row whose Area matches the ticket has a passing "Verified by".
* Rows that say **(OI-nn)** depend on an open question. Build them as the row states, which is the current firmware behaviour, and do not resolve the question yourself.

### Requirement count per chapter

| Source / chapter | Rows |
|---|---|
| P §1 Introduction | 17 |
| P §2 Definitions | 14 |
| P §3 Setup | 44 |
| P §4 Setup Name | 11 |
| P §5 Connect Organization | 18 |
| P §6 Home | 132 |
| P §7 Cure Process | 141 |
| P §8 Cure History | 32 |
| P §9 Error Management (48 SRS-9 + ERR-01..26) | 74 |
| P §10 Data (35 SRS-10 + DB-01..14) | 49 |
| P §11 Settings | 44 |
| E §1-§2 Scope and context | 5 |
| E §3 Environment | 3 |
| E §4 Architecture | 6 |
| E §5 Process flows | 19 |
| E §6 Program building | 4 |
| E §7 External interfaces | 32 |
| E §8 Lifecycle | 13 |
| E §9 Functional (RUN 11, STEP 16, SAFE 20, VAL 11, UI 18, DATA 11) | 87 |
| E §10 Non-functional | 11 |
| E §12 / §14 Verification and document control | 9 |
| Q 03-ui-and-qa.md | 21 |
| R srs/README.md | 4 |
| **Total** | **790** |

There are also 84 error codes (the Error code list), 17 source conflicts, and 73 open questions.

---

## Part P - Product SRS (`docs/sCure_SRS.html`, rev 2.1)

### P §1 Introduction & System Overview

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-1-1 | A Material is an ordered list of steps, each of one of six process types (Drying, Heating, Cure, Bleaching, Nitrogen, Cooling). The unit executes the steps one after another as a single uninterrupted run, from Start until the part is ready. | Domain | UT-Dom (RecipeStateMachine) |
| SRS-1-2 | Drying heats the chamber to a low target with the damper closed. Once the target is reached the damper opens and the chamber intake fan runs, venting moisture while the temperature is held. The step ends when the target was reached and the hold time has elapsed. | Application-Process | UT-App, QA-live |
| SRS-1-3 | Heating heats the chamber to the target with the damper closed and holds it. It ends when the target was reached and the hold time has elapsed. | Application-Process | UT-App |
| SRS-1-4 | Cure exposes the part to 405 nm UV at the step's UV intensity, normally at a chamber target temperature. A Cure step without a temperature is UV-only (no heating). It ends when the hold time has elapsed, counted from target reached or from step start as the step specifies. | Application-Process | UT-App, UT-Dom |
| SRS-1-5 | Bleaching behaves as Cure but with 450 nm light. | Application-Process | UT-App |
| SRS-1-6 | Nitrogen purges the chamber with N2. Nitrogen steps run only when Nitrogen Mode is on in Settings, otherwise they are skipped. A step ends after a fixed purge time. | Application-Process | UT-App, IT-API |
| SRS-1-7 | Cooling switches UV and heating off, opens the damper and runs the fans at the selected rate (Fast / Medium / Slow). It ends when the chamber has reached the step's target. | Application-Process | UT-App |
| SRS-1-8 | During a run and while idle, the firmware supervises the door, the temperature sensors, the fans and the UV LED panels, and stops the outputs on a fault. | Application-Process | UT-App (SupervisionService) |
| SRS-1-9 | At every power-on the unit runs a boot self-test (door, temperature sensors, 405 nm and 450 nm LEDs, chamber fans, N2 pressure sensor, firmware API) before Setup or Home is shown. | Native UI | UT-UI (boot order) |
| SRS-1-10 | When an external fume extractor (BOFA) is declared connected in Settings, the machine drives it whenever the air-intake fan runs (Drying, UV-only ventilation, Cooling, manual intake duty) and stops it with that fan, so chamber gases always go to the extractor and never into the room. | Application-Process | UT-App, Bench (OI-72) |
| SRS-1-11 | The touchscreen gives continuous access to the process state (Cure Process, Cure History and Alerts screens). | Native UI | UT-UI |
| SRS-1-12 | With a cloud connection configured, the firmware syncs with sCure Cloud at a regular interval. It sends system state (chamber temperature, door, heating / cooling / UV status, internet status, component run-time counters), user Materials, recent prints and recent cure runs (summaries without telemetry), and alerts raised and cleared in the last 48 h. | Application-Platform | UT-App (CloudSyncAgent) |
| SRS-1-13 | sCure Cloud may send only data commands back (add / update / delete a Material, send a print). No cloud command actuates hardware. | Application-Platform | UT-App, Review |
| SRS-1-14 | A DVT test requested from sCure Cloud runs only after the operator confirms it with Start on the unit's screen. | Dvt-Hdt | UT-App, Bench |
| SRS-1-15 | Deleting a cure run on the unit also deletes its report from sCure Cloud. | Application-Platform | UT-App (CloudReportDeletions) |
| SRS-1-16 | The reference UI file `sCure-UI.html` is the single source of truth for layout, screen structure and navigation. The SRS specifies logic only, with one screenshot placeholder per screen. | Native UI | Review |
| SRS-1-17 | Where the SRS and the firmware differ, the difference is listed as an Open Issue (§12). | Deploy-Ops | Review |

### P §2 Definitions & Abbreviations (normative content only)

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-2-1 | "sCure" is the product name used in the UI. The firmware plus touchscreen UI is "sCure CS". | Native UI | Review |
| SRS-2-2 | Ramp is the part of a step spent reaching the target. Hold is the part spent at target, counted by the step's hold time. | Domain | Review |
| SRS-2-3 | The boot self-test has seven checks, in this order: Door Closed, Temperature Sensors, UV LEDs 405nm, UV LEDs 450nm, Chamber Fans, N2 Pressure Sensor, API Server. | Native UI | UT-UI |
| SRS-2-4 | A planned restart is a restart after a clean firmware stop (Settings reboot, software update, self-restart) at most 10 minutes earlier. It skips the UV LED and fan checks, but the N2 pressure-sensor check still runs. | Native UI | UT-UI, UT-App |
| SRS-2-5 | A USB barcode scanner acts as a keyboard (types the code, then Enter), and the unit reads it without any text field having focus. | Native UI | UT-UI (BarcodeScanner) |
| SRS-2-6 | The device password (PIN) unlocks Developer Mode, and at Setup it also unlocks typing the SN by hand. | Native UI | UT-UI |
| SRS-2-7 | The UI settings file `ui-settings.json` in the data directory (`/var/lib/scurebox`) holds SN, System Name, organizationId, setupComplete, Nitrogen Mode, favorites and Developer Mode. | Native UI | UT-UI (UiSettingsStore) |
| SRS-2-8 | The system identity file `system.json` (installed config dir) holds the factory identity (model, hardware revision, default SN / organization / setupComplete). Every installation replaces it, and it is read-only for the UI. | Deploy-Ops | Review |
| SRS-2-9 | The configuration backup `config_backup.json` lives on the removable card under `/mnt/ssd2/scure`, overridable with `SCURE_SD_DIR`, and holds the serial number. | Application-Platform | UT-App (SerialBackup) |
| SRS-2-10 | The UV light sensor is a photoresistor behind the Left and Right panels, read as a resistance and used only to confirm that a commanded panel emits light. It is never used as a temperature. | Hardware | UT-HW |
| SRS-2-11 | "Offline on purpose" means Work Without Network is set, or the unit was never enrolled in sCure Cloud. Such a unit reports nothing about the missing uplink. | Application-Platform | UT-App |
| SRS-2-12 | sCure Cloud is configured per unit with service URL, machine key, display name and interval. | Application-Platform | UT-App |
| SRS-2-13 | The Origin website (`app.origin.io`) is used only for organization sign-in. sCure Cloud and the Origin website are distinct, and neither assigns the SN. | Application-Platform | Review |
| SRS-2-14 | GrabCAD is not used by sCure CS (OI-29). | Application-Platform | Review |

### P §3 Setup Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-3-1 | Setup is a full-screen first-run wizard: record the SN by barcode when the unit has none, name the unit, link or skip the organization, save, and mark Setup complete. Afterwards Home is shown. | Native UI | UT-UI |
| SRS-3-2 | Setup does not contact sCure Cloud: there is no cloud SN assignment and no cloud registration (OI-30). | Native UI | Review |
| SRS-3-3 | After leaving Welcome, a step indicator shows the Setup steps. The Serial Number step appears in it only when that step is needed. | Native UI | UT-UI |
| SRS-3-4 | At every firmware start the Boot screen shows the logo, then runs the seven checks one after another in the order of SRS-2-3. | Native UI | UT-UI |
| SRS-3-5 | Check 1, Door Closed: passes when the door sensor reads closed. While the door is open the screen shows "Close the door to continue" and waits up to 60 s. On failure it shows "The door is open - close it and retry" or "The door sensor is not reading". | Native UI | UT-UI |
| SRS-3-6 | Check 2, Temperature Sensors: passes when every supervised sensor (chamber and LED panel sensors) and both side-panel sensors give a valid reading. It waits up to 5 s after start-up for the first reading. On failure it shows "Not reading: <sensor list>". | Native UI | UT-UI |
| SRS-3-7 | Check 3, UV LEDs 405nm: the 405 nm panels are lit for 15 s and must warm by at least 0.8 °C (same test as the Settings LED Test). On failure it shows the LED test's message or "The LED test failed". | Native UI | UT-UI, Bench |
| SRS-3-8 | Check 4, UV LEDs 450nm: same as check 3 for the 450 nm panels, lit for 30 s. | Native UI | UT-UI, Bench |
| SRS-3-9 | Check 5, Chamber Fans: passes when no fan fails the all-fans fan test. A fan rated "worn" (warning) still passes. On failure it shows "Not spinning: <fan (RPM)> ..." or "The fan test failed". | Native UI | UT-UI |
| SRS-3-10 | Check 6, N2 Pressure Sensor: passes as soon as the line-pressure sensor gives a valid reading, waiting up to 20 s. With `pressure_sensor.required = false` it passes without being judged. On failure it shows the Err 9016 text "N2 pressure sensor not reading - check that the nitrogen pressure sensor is connected". | Native UI | UT-UI |
| SRS-3-11 | Check 7, API Server: passes when the firmware's state interface answers. On failure it shows "The firmware API is not answering". | Native UI | UT-UI |
| SRS-3-12 | The chamber-fan check opens the damper before spinning the fans and closes it afterwards. A damper that is already open is left open, and a damper that will not open does not stop the check. | Native UI | UT-UI, UT-App |
| SRS-3-13 | The UV LED checks run only if check 1 passed. With the door not closed they are reported failed with "Skipped - the door is not closed", and no UV light is switched on. | Native UI | UT-UI |
| SRS-3-14 | On a planned restart (clean stop at most 10 min before start), checks 3, 4 and 5 pass without running and check 6 still runs. After a power loss, crash or watchdog stop (no clean stop recorded) the full self-test runs. | Native UI | UT-UI |
| SRS-3-15 | With no IO board (simulation), checks 2 to 6 pass immediately. | Native UI | UT-UI |
| SRS-3-16 | A check that cannot run is reported as failed with "The check could not run: ...". | Native UI | UT-UI |
| SRS-3-17 | When all checks pass, the screen shows "All systems operational" and proceeds by itself to the Setup gate. | Native UI | UT-UI |
| SRS-3-18 | On one or more failures the screen stays on the result ("<n> of 7 checks failed", with a reason per check) and offers Retry (all checks again, without the logo) and Continue anyway (to the Setup gate). A failed self-test does not lock the unit and raises no alert (OI-33). | Native UI | UT-UI |
| SRS-3-19 | Setup gate: read setupComplete (the machine value, else the system.json factory value). If complete, show Home; otherwise show the Welcome step. | Native UI | UT-UI |
| SRS-3-20 | Unlink in Settings clears organizationId and setupComplete, so Setup is shown again. SN and System Name are kept: the repeated Setup skips the SN step and pre-fills the name. | Native UI | UT-UI |
| SRS-3-21 | Welcome shows "Congratulations on your new sCure curing system. Let's set it up in just a few steps." with Get Started. On Get Started, if an SN is stored (machine value, else system.json) the SN step is skipped and Name is shown; otherwise the SN step is shown. | Native UI | UT-UI |
| SRS-3-22 | The SN step waits for a scan ("Scan the barcode" / "Waiting for the scanner..."). A scanner connected while the step is shown is detected automatically. | Native UI | UT-UI |
| SRS-3-23 | A scanned code is accepted only while the SN step is on screen. A valid SN is 3-40 characters of letters and digits, and after the first character also `.` `_` `/` `-`. Surrounding spaces are removed. | Native UI | UT-UI |
| SRS-3-24 | On a valid scan the step shows "Serial number scanned" with the SN and enables Next. Scanning again replaces the SN. | Native UI | UT-UI |
| SRS-3-25 | On an invalid code the step shows "<code> is not a valid serial number" (code truncated to 40 characters) and keeps waiting. An SN accepted earlier in the step is kept. | Native UI | UT-UI |
| SRS-3-26 | The SN step cannot be skipped. Next stays disabled until a valid SN is scanned or typed, and there is no way back to Welcome. | Native UI | UT-UI |
| SRS-3-27 | Manual SN entry (service): ten taps on the barcode-label picture open the device-password pad. With the correct password the SN field opens the on-screen keyboard, and the same validity rule applies. Entering the password here does not leave Developer Mode on. | Native UI | UT-UI |
| SRS-3-28 | On Next the SN is saved on the machine and Name is shown. From then on the SN is shown in Settings and written into every cure run and cure report. | Native UI | UT-UI, UT-App |
| SRS-3-29 | The SN cannot be changed later from the UI (OI-30). | Native UI | UT-UI |
| SRS-3-30 | Setup ends on the Link Organization step, which marks Setup complete and shows Home. | Native UI | UT-UI |
| SRS-3-31 | SN restore from the card runs when the settings are first read at start-up, before the Setup gate, and is invisible to the operator. If the unit has no SN of its own and the card holds a backup, that SN becomes the unit's SN, is written back to the data directory, and Setup skips the SN step. | Application-Platform | UT-App, UT-UI |
| SRS-3-32 | If a backup exists but cannot be used (unreadable, or no serial number in it), the unit starts without an SN, raises Err 3001 Serial Number Restore Failed, and sends the operator to the SN step. | Application-Platform | UT-UI |
| SRS-3-33 | A unit that already has an SN ignores the card. A card moved between machines never changes the identity of a machine that has an SN. | Application-Platform | UT-App |
| SRS-3-34 | No card mounted is not an error at start-up: the unit simply has no second copy. | Application-Platform | UT-App |
| SRS-3-35 | Codes 3002 (Cloud Communication Failed) and 3003 (No Internet Connection) are never raised: Setup requests no SN from the cloud, registers nothing, and does not check the internet (OI-30). | Native UI | Build-gate (ErrorCoverageTests) |
| SRS-3-36 | The Setup flow chart is a draw.io swimlane (lanes Storage, UI sCure, Machine) with editable source `docs/diagrams/setup-flow.drawio`, rendered with `tools/drawio-to-svg.mjs` and `tools/svg-to-grid-png.mjs`. The flow has no terminal error. | Deploy-Ops | Review |
| SRS-3-37 | Setup values are kept in three files: `ui-settings.json` (data dir, survives installs and updates), `system.json` (factory, replaced by every install, read-only for the UI) and `config_backup.json` on the card (serialNumber, device name, write time). A machine value always takes precedence over the factory value. | Application-Platform | UT-UI |
| SRS-3-38 | Each change is written to `ui-settings.json` at once, through a temporary file plus replace. | Native UI | UT-UI |
| SRS-3-39 | If `ui-settings.json` cannot be written, the fault is only logged: the user is not informed and the flow continues. If it cannot be read, the defaults are used (Setup not complete, no SN) (OI-31). | Native UI | UT-UI |
| SRS-3-40 | Every serial number set is also written to the card at the moment it is set, through a temporary file beside the target plus a move. | Application-Platform | UT-App |
| SRS-3-41 | If the SN cannot be written to the card (no card mounted, or the write failed), Err 4003 SD Backup Write Failed is raised. It does not block Setup or the machine. | Application-Platform | UT-UI |
| SRS-3-42 | The backup directory is used only when it, or its parent, already exists, so a card that is not mounted is never created on the system disk. | Application-Platform | UT-App |
| SRS-3-43 | Only the identity is backed up. Programs, history, counters and calibration are not (OI-67). | Application-Platform | Review |
| SRS-3-44 | Measured fact (2026-11-03, Origin image, unit 0xb2c91946, fw 1.0.140): `/mnt/ssd2` does not exist and cannot be created (read-only root, no removable medium), the data dir is `/opt/data/scurebox/data` on the same eMMC, and so every SN set raises 4003 (OI-74). | Deploy-Ops | Bench |

### P §4 Setup Name Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-4-1 | The Name step assigns the System Name, which is shown in the top bar, in Settings, in the Link Organization subtitle, and in cure runs and reports. | Native UI | UT-UI |
| SRS-4-2 | The System Name is not sent to sCure Cloud (OI-32). | Application-Platform | Review |
| SRS-4-3 | The step shows the title "Name Your Cure Box", the hint "Choose a name to identify this device", a Device Name field and Next. The field is pre-filled with the saved System Name, else the default "sCure". An illustration shows the name as it is typed. | Native UI | UT-UI |
| SRS-4-4 | Next is enabled at once, so the default can be accepted without typing. | Native UI | UT-UI |
| SRS-4-5 | Tapping the field opens the on-screen keyboard with the current name. Closing the keyboard keeps the text typed so far. | Native UI | UT-UI |
| SRS-4-6 | An empty or spaces-only name disables Next, and the field shows "Tap to enter name...". No other rule is applied: no length, character or uniqueness limit (OI-8). | Native UI | UT-UI |
| SRS-4-7 | On Next the name is trimmed, saved as systemName in `ui-settings.json`, and Link Organization is shown. The name is saved again when Setup finishes. | Native UI | UT-UI |
| SRS-4-8 | systemName is loaded at start-up and available to all screens, and a change shows at once. It can be changed in Settings, where saving an empty name restores "sCure". | Native UI | UT-UI |
| SRS-4-9 | systemName has no secondary backup copy. | Native UI | Review |
| SRS-4-10 | An empty name raises no message and no alert (4001 is not raised). A save failure is only logged, and the user proceeds (OI-31). | Native UI | UT-UI |
| SRS-4-11 | The step contacts no cloud service. Its flow is `docs/diagrams/setup-name-flow.drawio` (lanes Storage, UI sCure). | Native UI | Review |

### P §5 Connect Organization Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-5-1 | Link Organization is the final Setup step. It links the unit to an Origin organization or lets the user skip. Without an organization, Home shows no print history. | Native UI | UT-UI |
| SRS-5-2 | The step shows the title "Link Organization", the subtitle "Link <System Name> to your organization", the options "Upload Organization CSV" ("Select the CSV file from the USB drive") and "Sign in to Origin" ("Use your Origin account"), a Link Organization button disabled until an organization is found, and "Continue without organization". | Native UI | UT-UI |
| SRS-5-3 | The two source options are hidden while an organization is shown as found. | Native UI | UT-UI |
| SRS-5-4 | Upload Organization CSV opens a USB file browser ("Select organization CSV"). It lists `.csv` files on every mounted USB drive, from the root to two folder levels below, skipping hidden folders, at most 200 files. With none it shows "No CSV file found on a USB drive". Closing without a choice leaves the step unchanged. | Native UI | UT-UI |
| SRS-5-5 | The chosen file is read as text, and the first UUID found anywhere in it (hex 8-4-4-4-12, any case) is the Organization ID (OI-10). | Native UI | UT-UI |
| SRS-5-6 | When a UUID is found, the step shows "Organization Found" with the ID and "from <file name>", and Link Organization is enabled. | Native UI | UT-UI |
| SRS-5-7 | With no UUID, or an unreadable file, the step shows "No valid organization ID found in CSV file", sets no ID, keeps Link disabled, and lets the user pick another file. No alert is raised (5001 is not raised). | Native UI | UT-UI |
| SRS-5-8 | Sign in to Origin opens the Origin website (`app.origin.io`, the configured sign-in address) inside a "Sign in to Origin" dialog. Text fields open the on-screen keyboard, and password fields are masked. | Native UI | UT-UI, Bench |
| SRS-5-9 | Only the organization (organizationId UUID, plus the account name or e-mail for display) is taken from the signed-in site. Each sign-in uses a new empty browser profile that is deleted afterwards. The dialog states "Only the organization is taken from your account. Nothing about your sign-in is stored on this machine." | Native UI | UT-UI, Review |
| SRS-5-10 | On success the dialog closes and the step shows "Organization Found" with the ID and "from Origin account <e-mail or name>". Link is enabled. | Native UI | UT-UI |
| SRS-5-11 | Sign-in timeout is configurable, default 300 s, limited to 30-1800 s. A timeout shows "Sign-in took too long - try again". Other failures show "Origin sign-in failed - try again", "No web browser found on this machine" or "Origin sign-in is not set up on this machine". Try Again or cancel; cancel leaves the step unchanged. | Native UI | UT-UI |
| SRS-5-12 | The step does not check the internet before sign-in (OI-34). | Native UI | Review |
| SRS-5-13 | While an organization is shown as found, Change clears it so the user can choose a source again. | Native UI | UT-UI |
| SRS-5-14 | Link Organization (enabled only with an ID) saves the System Name, sets organizationId, sets setupComplete = true, persists, and shows Home. | Native UI | UT-UI |
| SRS-5-15 | Continue without organization marks Setup complete with organizationId saved empty, persists, and shows Home. | Native UI | UT-UI |
| SRS-5-16 | The organization is optional and can be linked or changed later in Settings with the same two sources and UUID rule. organizationId is not sent to sCure Cloud (OI-32). | Native UI | UT-UI |
| SRS-5-17 | organizationId and setupComplete are stored in `ui-settings.json`. Until saved, the system.json defaults apply. There is no secondary backup. | Native UI | UT-UI |
| SRS-5-18 | An invalid CSV, a cancelled choice and a failed sign-in are recoverable and return to the source choice. A config save failure is only logged and Home is shown (OI-31). The flow source is `docs/diagrams/setup-org-flow.drawio` (lanes Storage, UI sCure, Cloud). | Native UI | UT-UI, Review |

### P §6 Home Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-6-1 | Home is the main hub. From it the operator reviews recent prints, manages the program library (presets and user programs), creates, imports, duplicates or edits programs, and selects and starts a cure. | Native UI | UT-UI |
| SRS-6-2 | Each time Home is shown its state is rebuilt: programs re-read (presets plus user, favorites first), favorites and organization link re-read, recent prints re-read. Nothing is pre-selected, and an earlier selection is not kept. While loading, the list shows "Loading materials...". | Native UI | UT-UI |
| SRS-6-3 | Home has no Start Cure button and no Edit mode (removed in 1.0.133). Swiping a row right (a program row, or a print row whose material resolves to a program) starts a cure. Swiping left opens the actions (Duplicate / Edit / Delete). | Native UI | UT-UI |
| SRS-6-4 | The swipe gestures are shortcuts onto the same paths, never a second code path: every Start Cure gate (critical alert, door, nitrogen-only, fan pre-check) applies to a swipe. | Native UI | UT-UI |
| SRS-6-5 | The Program List header reads "Swipe a program right to start it, left to change or delete it". | Native UI | UT-UI |
| SRS-6-6 | With no organization linked, Recent Prints shows the "No organization" card and View All is hidden. The Program List and starting are unaffected. | Native UI | UT-UI |
| SRS-6-7 | With an organization linked and an empty history, the screen shows "No prints yet." With no programs it shows "No materials yet. Upload a CSV or create a new material." and no cure can be started. | Native UI | UT-UI |
| SRS-6-8 | Showing Home and starting a cure need no live printer connection and no cloud call. Gates use the machine state (door, refreshed about once per second) and the active alerts. | Native UI | UT-UI |
| SRS-6-9 | The top bar is shared by all main screens and refreshes on machine-state change (about 1 Hz), alerts, settings or screen change. | Native UI | UT-UI |
| SRS-6-10 | Back arrow: shown on every screen except Home and Cure Process. It returns to the previous screen, else Home. | Native UI | UT-UI |
| SRS-6-11 | Logo plus name shows the sCure logo and the system name (default "sCure"). It has no action. | Native UI | UT-UI |
| SRS-6-12 | Door button: hidden on Cure Process. When the door is closed or unknown it reads "Open Door". A tap asks the machine to open the door and shows "Door Open" at once, and the next state refresh confirms or corrects it. When the door is open it reads "Door Open", highlighted and disabled. | Native UI | UT-UI |
| SRS-6-13 | Temperature: display only, hidden on Cure Process. It shows the chamber temperature to 0.1 °C ("--.-°C" with no reading), plus "Target: N°C" while a target is set. The value turns red once the heater has been on continuously for more than 10 s. | Native UI | UT-UI |
| SRS-6-14 | DEV badge: shown only in Developer Mode and not on developer screens. It opens the developer menu and is inert during a cure. | Native UI | UT-UI |
| SRS-6-15 | N2 indicator: shown while Nitrogen Mode is on, with an "active" state while nitrogen flows. | Native UI | UT-UI |
| SRS-6-16 | NFC indicator: shown when NFC is enabled and the USB reader is detected, and also while detection has not reported yet. | Native UI | UT-UI |
| SRS-6-17 | History opens Cure History. The Alerts bell opens Alerts and carries a badge with the active count: red when any critical is active, orange when only warnings are. | Native UI | UT-UI |
| SRS-6-18 | The Settings gear opens Settings. A repeated press sequence requests Developer Mode instead (see SRS-11-41). | Native UI | UT-UI |
| SRS-6-19 | The Network globe opens the Network screen and is shown red when the internet check reports the connection down. | Native UI | UT-UI |
| SRS-6-20 | During a cure, History, Alerts, Settings, Network and DEV are inert, and Back, Door and Temperature are hidden. | Native UI | UT-UI |
| SRS-6-21 | Moves between top-level screens replace the previous navigation entry, so Back returns to Home. Top-bar controls never change Home's selection. | Native UI | UT-UI |
| SRS-6-22 | Recent Prints shows the first 3 entries of the on-device print-history store, never a live cloud call. Order is newest first with PostgreSQL (`v_print_history`) and stored order with `print_history.json`. | Native UI | UT-UI |
| SRS-6-23 | The print store is exposed as `GET /api/print-history` and replaced whole by `POST /api/print-history`, and it persists across restart and reboot. | Api | IT-API, QA-live |
| SRS-6-24 | Print entries are created only by the cloud `send_print` command (put at the front) or by `POST /api/print-history`. The box adds no print when a cure finishes. Prints cured through View All are removed when that cure completes (OI-12). | Application-Platform | UT-App, IT-API |
| SRS-6-25 | Print record fields: id, printName, materialName, printerName, date (local ISO), duration (seconds, shown as whole minutes rounded up, "N min"; OI-38), status, steps, csvFile (stored, not used by Home). | Domain | UT-Dom, IT-API |
| SRS-6-26 | Print status icons: completed / ok / success shows a green ✓; aborted / warning / partial an orange ⚠; anything else a red ✕. | Native UI | UT-UI |
| SRS-6-27 | A print stores the material name, not the recipe. The program run is the one the name resolves to at selection time. | Native UI | UT-UI |
| SRS-6-28 | Each recent-print row shows status icon, print name, material, duration, relative time and printer. Relative time is "Nm ago" under 60 min, "Nh ago" under 24 h, else "Nd ago". | Native UI | UT-UI |
| SRS-6-29 | Tapping a print toggles its selection. Selecting clears the Program List selection and resolves the program by name: the first program in list order (favorites first) whose name equals materialName. With no match nothing is active, without a hint. Tapping again deselects. | Native UI | UT-UI |
| SRS-6-30 | Selecting a print does no printer or cloud validation. A cure started from a Recent Prints selection does not remove the print from history. | Native UI | UT-UI |
| SRS-6-31 | Swiping a print row right runs its program, looked up by name at that moment. When the name is not found the answer is "No program named <x> is on this machine" and nothing starts. Print rows have no left-swipe tray. | Native UI | UT-UI |
| SRS-6-32 | Prints may be combined only when their material names are equal (OI-15). | Native UI | UT-UI |
| SRS-6-33 | View All is shown in the Recent Prints header only when an organization is linked. It opens the Print History dialog over Home and changes nothing by itself. | Native UI | UT-UI |
| SRS-6-34 | Print History lists all store entries by date, newest first, with unreadable dates last. The title is "Print History (N)", or "(shown/total)" while filtered, plus "— N selected" while a selection exists. | Native UI | UT-UI |
| SRS-6-35 | Each Print History entry shows checkbox, status icon, print name, material, date and time, duration (minutes rounded up) and printer. | Native UI | UT-UI |
| SRS-6-36 | The Filters button opens the filter bar and shows the active-filter count. Material ("All Materials" plus the names present, alphabetical), Printer (same), and From / To dates (yyyy-mm-dd on the keyboard; To includes the whole end day; undated entries hidden while a date filter is set; invalid text ignored). | Native UI | UT-UI |
| SRS-6-37 | Filters combine with AND, update list and count at once, and Clear removes all. There is no free-text search. Empty results show "No results match the filters.", and an empty store shows "No print history yet." Filtering keeps the selection. | Native UI | UT-UI |
| SRS-6-38 | Pick one (no selection): a row tap closes the dialog with material plus print id, and Home selects the program by name. Nothing starts. The print id is kept, so the print is removed from history when the next cure started on Home completes (OI-37). | Native UI | UT-UI |
| SRS-6-39 | Multi-select: the checkbox toggles a row, and once a selection exists a row tap toggles too. Clear Selection empties it. The strip reads "Ready to cure <material>", "Ready to cure N× <material>" or "⚠ Cannot cure different materials together!". | Native UI | UT-UI |
| SRS-6-40 | Cure Together is enabled only when all selected prints share one material name. It closes the dialog with the material and ids, and Home selects the program by name. With two or more prints and open gates (program found, door closed, no critical) it runs the Start Cure sequence at once with those ids, otherwise it only selects. Completion removes the selected prints from history, and an aborted cure leaves them. | Native UI | UT-UI |
| SRS-6-41 | Close leaves Home unchanged. Print History validation uses material names only, with no printer, cloud or live-job checks. | Native UI | UT-UI |
| SRS-6-42 | The organization link gates only the print-history display, never curing. Customers without a Stratasys printer can still build programs and run cures. | Native UI | UT-UI |
| SRS-6-43 | Program List title is "Program List (N)". Sources are presets (read-only; PostgreSQL seed or `config/presets.json`) plus user programs (PostgreSQL or `user_materials.json`, always written back as a whole list). The cloud can add, replace or delete user programs. Programs are device-local, not organization-scoped. | Native UI | UT-UI, IT-API |
| SRS-6-44 | 19 presets ship, the Stratasys P3 catalog: P3 Stretch 80 V2, LOCTITE 3D IND403 High Modulus, Ultracur3D ST45, LOCTITE 3D 3843 High Toughness, LOCTITE 3D 3172 High Impact, LOCTITE 3D IND405 Clear, LOCTITE 3D IND402 High Rebound, P3 Silicone 25A, P3 MED Silicone 25A, LOCTITE 3D IND3380 ESD, LOCTITE 3D 3955 FST, P3 Stretch IND475, Stratasys Dura56, LOCTITE 3D MED 412, LOCTITE 3D MED 413, Somos WeatherX 100, Ultracur3D RG 3280, LOCTITE 3D IND3785 Low Migration, P3 Deflect 110. The collection pages (Open Materials for P3, P3 Silicones) are not shipped. | Deploy-Ops | Review, UT-Dom |
| SRS-6-45 | Every bundled program dries, cures and cools. None peaks above 65 °C, none cools below 30 °C, none needs nitrogen hardware, and none is estimated above one hour by the machine's estimator. Each uses one of four profiles (rigid, high-temperature, clear with a Bleaching step, elastomer / silicone), and the values are placeholders (OI-70). | Domain | UT-Dom (presets vs estimator / validator) |
| SRS-6-46 | Each program row shows a favorite star, a lock (preset) or plus (user), the name, "~N min" estimated duration, and a decorative chevron. | Native UI | UT-UI |
| SRS-6-47 | Order: favorites first, then the rest. Within each group the store order is kept (presets before user programs). | Native UI | UT-UI |
| SRS-6-48 | Selection is single. A tap makes the program active, clears any print selection and highlights the row. A re-tap keeps it selected, with no deselect. A tap only selects; running is the right swipe. | Native UI | UT-UI |
| SRS-6-49 | Program names need not be unique, and resolution by name takes the first match in list order (OI-39). | Native UI | UT-UI |
| SRS-6-50 | The star toggles favorite and re-reads and re-orders the list, and it starts nothing. Favorites are stored as `favoriteMaterialIds` in `ui-settings.json`: device-local, not per user, organization or cloud. They persist across reboot. Deleting a user program removes it from favorites. They apply to presets and user programs, and prints have no star. | Native UI | UT-UI |
| SRS-6-51 | Presets (lock icon) cannot be edited or deleted, but can be duplicated into an editable user program. In the cure flow they behave like user programs (OI-36). | Native UI | UT-UI |
| SRS-6-52 | A row tap (outside the star) only selects: it opens no details and starts nothing. The chevron has no action. | Native UI | UT-UI |
| SRS-6-53 | Swipe right on a program or print row must travel past half the row width and at least 180 px. The row then slides off (160 ms) over a green Start Cure layer, and the full Start Cure sequence starts when it arrives. | Native UI | UT-UI |
| SRS-6-54 | Swipe left (program rows only) opens the tray after 120 px: Duplicate, plus Edit and Delete for user programs. | Native UI | UT-UI |
| SRS-6-55 | An open tray closes on 60 px back, a tap anywhere, a selection, or another row's tray opening. Only one tray is open at a time. | Native UI | UT-UI |
| SRS-6-56 | Any shorter drag springs back and does nothing. Putting a row back can never start a cure, and an open tray can only be closed. | Native UI | UT-UI |
| SRS-6-57 | The gesture claims the finger only after 14 px of mostly sideways travel (abs(dx) > 1.2·abs(dy)). Until then a tap selects and a vertical drag scrolls. Once claimed, the page does not scroll and the lift judges only sideways travel. | Native UI | UT-UI |
| SRS-6-58 | Nothing happens until the finger lifts, and dragging back abandons the gesture. | Native UI | UT-UI |
| SRS-6-59 | A right swipe against an open door answers "Close the door to start the cure" in an OK-only dialog. | Native UI | UT-UI |
| SRS-6-60 | The row slide is stepped once per drawn frame, so it is smooth on the panel even with UI animations off (the unit default). | Native UI | Bench, UT-UI |
| SRS-6-61 | `POST /api/ui/swipe?program=<name or index>&dir=left|right` performs the same gesture for QA / DVT and answers start, open, close or none. | Api | IT-API, QA-live |
| SRS-6-62 | Duplicate saves "<name> Copy" (then "Copy 2", "Copy 3"... until unused) as a user program at once, with copied steps, a new id and its estimate. It re-reads the list and opens the editor ("Edit Program"). It works on presets and user programs, and cancelling the editor keeps the saved copy. | Native UI | UT-UI |
| SRS-6-63 | Edit (user programs only) opens "Edit Program", and Update Program saves under the same id. | Native UI | UT-UI |
| SRS-6-64 | Delete (user programs only) asks "Delete “<name>”?" / "The program will be removed from this machine. This cannot be undone." (Delete / Cancel). It removes the program from user programs, favorites and the selection. Presets are never deleted, and preset trays show only Duplicate. | Native UI | UT-UI |
| SRS-6-65 | The CSV header button opens Import from CSV. Imported programs are not auto-selected, and the list is re-read when the dialog closes. | Native UI | UT-UI |
| SRS-6-66 | "+ New" opens an empty editor ("Build Cure Program", button "Save Program"). The saved program is stored, the list re-read, and nothing auto-selected. | Native UI | UT-UI |
| SRS-6-67 | The editor is a dialog over Home that does not close on an outside tap. It creates a program, or edits a user program or fresh duplicate ("Edit Program" / "Update Program"). Edit and Duplicate load name and steps normalised. | Native UI | UT-UI |
| SRS-6-68 | Name: the keyboard opens on tap and the text is trimmed. A name is required to save, and uniqueness is not checked. | Native UI | UT-UI |
| SRS-6-69 | Steps show as a horizontal strip of "Step N" cards edited inline, with fields per process. Numeric fields open a number pad limited to the current range and have −/+ buttons (temperature ±5 °C, time ±1 min, UV ±5 %) that stop at the range ends. | Native UI | UT-UI |
| SRS-6-70 | Add Step appends the forced process (Cure after an N2 purge, Cooling after the Cure/Bleaching following a purge), otherwise Heating with defaults, and scrolls it into view. | Native UI | UT-UI |
| SRS-6-71 | The trash icon removes a step. The program may be emptied, but saving an empty program is refused. | Native UI | UT-UI |
| SRS-6-72 | After every change steps are renumbered, each card's process list is limited to the legal processes, and every value is clamped into range (later heated steps raised to the running minimum, Cooling targets lowered to their ceiling). | Native UI | UT-UI (EditorRules) |
| SRS-6-73 | Footer summary: "N steps · H min holds · ~T min total". H sums hold times (Cooling and N2 count 0). T is the estimate. | Native UI | UT-UI |
| SRS-6-74 | The CSV button writes the steps in the 10-column format to the USB drive as `<name>.csv` (`untitled.csv` without a name). It shows "Saved <file> to USB", or "No Disk-on-Key connected — connect one and try again" (alert 9081), or the write error (alert 9082). Export does not save the program and works even when the program is invalid. | Native UI | UT-UI |
| SRS-6-75 | Cancel closes and discards unsaved changes. | Native UI | UT-UI |
| SRS-6-76 | Save / Update checks, in order, showing only the first failure above the footer: name ("Enter a material name"), at least one step ("Add at least one step"), then every program rule. On failure the editor stays open. On success it stores (new id for New, same id for Edit), stores the estimate as totalDuration, closes, re-reads the list, and does not auto-select. | Native UI | UT-UI |
| SRS-6-77 | The same program rules apply in the editor (live clamp plus Save), in CSV import, and at Start on the machine (with the Start relaxation of SRS-6-104). | Domain | UT-Dom |
| SRS-6-78 | Processes are offered in this order: Drying, Heating, Cure (405 nm), Bleaching (450 nm), Cooling, N2 Purge. | Native UI | UT-UI |
| SRS-6-79 | Card fields: Heating and Drying show Process, Temperature, Time. Cure and Bleaching show Process, Chamber Heating On/Off, Temperature plus Timer Start plus UV Start (only with heating On), Time, UV Intensity. Cooling shows Process, Target Temp, Cooling Mode (no Time). N2 Purge shows only Process, with the note "The N₂ purge runs automatically if nitrogen is enabled; otherwise it is skipped." | Native UI | UT-UI |
| SRS-6-80 | Heating: 30-80 °C and at least the running minimum, time 1-120 min. | Domain | UT-Dom |
| SRS-6-81 | Drying: 30-50 °C and at least the running minimum, time 1-120 min. | Domain | UT-Dom |
| SRS-6-82 | Cure (405 nm): with Chamber Heating On, 30-80 °C and at least the running minimum. With Off, no temperature (UV only). Time 1-120 min. UV 10-100 % (default 30 %). Timer Start and UV Start only with heating On. | Domain | UT-Dom |
| SRS-6-83 | Bleaching (450 nm): as Cure, but time 1-720 min (12 h). | Domain | UT-Dom |
| SRS-6-84 | Cooling: target from 30 °C up to the cooling ceiling, which is the last heated temperature − 5 °C (never below 30), or 75 °C if nothing was heated since the previous Cooling. No time. Mode Fast / Medium / Slow, default Medium. It resets the running minimum and vents an N2 purge. | Domain | UT-Dom |
| SRS-6-85 | N2 Purge: no temperature or time. It runs only with Nitrogen Mode on, and with Nitrogen Mode off the N2 steps are dropped at Start. | Domain | UT-Dom, UT-App |
| SRS-6-86 | Values are whole numbers. The pad accepts any whole value in range, not only multiples of 5. | Native UI | UT-UI |
| SRS-6-87 | Defaults: Add Step gives Heating 40 °C / 10 min (raised to the running minimum, capped at the process maximum). A forced Cure is 40 °C (or the running minimum) / 10 min / UV 30 % / Timer Start and UV Start at temperature. A forced Cooling is 30 °C (capped at the ceiling), Medium. Switching to Cooling sets 30 °C (capped). Switching from Cooling sets 40 °C (or the running minimum). Chamber Heating defaults to On. | Native UI | UT-UI |
| SRS-6-88 | Timer Start "At temperature" (on-target, default) starts the step time when the target is reached. "On ramp start" (on-ramp) starts it with the ramp. | Domain | UT-Dom |
| SRS-6-89 | UV Start "At temperature" (at-target, default) lights the UV when the target is reached. "On ramp start" (at-start) lights it at ramp start. | Domain | UT-Dom |
| SRS-6-90 | TimerMode and UVStart are stored on the step and in the CSV and applied at runtime. With heating Off there is no temperature, Timer Start or UV Start. A Ventilation value from a CSV or older program is kept unchanged, and the editor offers no field for it. | Domain | UT-Dom |
| SRS-6-91 | Sequencing: after an N2 Purge only Cure or Bleaching may follow. After the Cure/Bleaching that follows a purge, only Cooling (the vent). | Domain | UT-Dom |
| SRS-6-92 | A purge is offered only while fewer than 2 purges precede the position and a Cooling has occurred since the previous purge (the first purge needs none). At most 2 purges per program. | Domain | UT-Dom |
| SRS-6-93 | Running minimum: a heated step (Heating, Drying, heated Cure/Bleaching) may not ask for less than the last heated step since the most recent Cooling. N2 and UV-only steps do not change it, and Cooling resets it to 30 °C. Lowering a temperature in the editor raises the following heated steps. | Domain | UT-Dom |
| SRS-6-94 | Drying is capped at 50 °C. A Drying step after a hotter step shows 50 °C, and Save reports "Temperature (50°C) cannot be lower than the previous step (…°C) without a Cooling step" until a Cooling is placed before it. | Domain | UT-Dom |
| SRS-6-95 | A Cooling target must be at least 5 °C below the last heated step. | Domain | UT-Dom |
| SRS-6-96 | On Save and import all failures are collected; the editor shows the first, the import lists all. Rule "at least one step" gives "Add at least one step". | Domain | UT-Dom |
| SRS-6-97 | Heated-temperature messages: "Step N: Invalid temperature T (must be 30-80 for <process>)" (30-50 for Drying), and "Step N: <process> needs a target temperature (30-80°C)" when Heating or Drying lack one. | Domain | UT-Dom |
| SRS-6-98 | Cooling-target messages: "Step N: Cooling needs a target temperature (30-75°C)" and "Step N: Invalid temperature T (must be 30-75 for Cooling)". | Domain | UT-Dom |
| SRS-6-99 | Time and UV messages: "Step N: Invalid time T (must be 1-120)" (1-720 for Bleaching), and "Step N: Invalid UV intensity U (must be 10-100)". | Domain | UT-Dom |
| SRS-6-100 | N2 count message: "Step N: A maximum of 2 nitrogen purge steps is allowed". | Domain | UT-Dom |
| SRS-6-101 | N2 block messages. Editor: "After an N₂ purge, add a Cure or Bleaching step" and "Add a Cooling step after the Cure/Bleaching step that follows the N₂ purge". CSV: "Add a Cure or Bleaching step after the N₂ purge" and "Nitrogen must be vented — add a Cooling step after the N₂ purge". Both: "Step N: After nitrogen, only Cure or Bleaching is allowed" and "Step N: Only Cooling is allowed after the Cure/Bleaching step that follows the N₂ purge". | Domain | UT-Dom |
| SRS-6-102 | Temperature-chain message: "Step N: Temperature (T°C) cannot be lower than the previous step (P°C) without a Cooling step". | Domain | UT-Dom |
| SRS-6-103 | Cooling-gap message: "Step N: Cooling target (T°C) must be at least 5°C below the previous step (P°C)". | Domain | UT-Dom |
| SRS-6-104 | At Start the machine re-checks the program with the API limits (heated 30-80 °C, Drying 30-50 °C, Cooling 20-80 °C, UV 10-100 %), then the same program rules. One relaxation: a Cooling target of 20-80 °C is accepted even outside the editor's 30-75 °C. | Application-Process | UT-App (RecipeValidator), IT-API |
| SRS-6-105 | The step-transition state machine is drawn in `docs/diagrams/step-rules-flow.drawio`: Normal steps super-state, plus the N2 cycle N2 → Cure/Bleaching → Cooling (max 2, Cooling since the previous purge). | Domain | Review |
| SRS-6-106 | The estimate ("~N min" per row, editor "~T min total", stored totalDuration) is in whole minutes rounded up. | Domain | UT-Dom (ProgramEstimator) |
| SRS-6-107 | The estimate starts at 25 °C and carries the chamber temperature through the steps. A heated step adds the ramp from the carried temperature to the target (13 s/°C up to 45 °C, 50 s/°C from 45 to 75 °C, 80 s/°C above 75 °C; nothing when the target is not higher) plus the hold. With Timer Start "On ramp start" only the part of the ramp longer than the hold is added. UV-only adds the hold only. | Domain | UT-Dom |
| SRS-6-108 | Cooling adds the fall from the carried temperature to the target at 2.5 (Fast), 1.5 (Medium) or 0.8 (Slow) °C/min. A blank target counts as 25 °C. | Domain | UT-Dom |
| SRS-6-109 | N2 Purge adds 120 s. The Program List and the editor always count it, while the Cure Process screen leaves N2 out when Nitrogen Mode is off (OI-40). | Domain | UT-Dom, UT-UI |
| SRS-6-110 | Import from CSV dialog: "Upload CSV files. Each file becomes a material in your list." It has an example table (Step · Process · Temp · Time · UV% · Mode, six rows) and the footnote "Temp: 30-80°C (Drying 30-50°C, Cooling 30-75°C) · Time: 1-120 min (Bleaching up to 720) · UV: 10-100% · Mode: fast/medium/slow". It does not close on an outside tap. | Native UI | UT-UI |
| SRS-6-111 | The import picker "Select program CSV" lists `*.csv` on every mounted USB drive (root plus 2 levels, hidden skipped, max 200). Files are picked and imported one at a time, and the operator can browse again. Closing imports nothing. | Native UI | UT-UI |
| SRS-6-112 | Per file: an unreadable file gives "Cannot read file: …". Otherwise the file is parsed row by row and checked against the program rules, and all messages are collected (structural and row errors, then rule failures). | Domain | UT-Dom (ProgramCsv) |
| SRS-6-113 | A file without messages becomes a user program named after the file (minus `.csv`), with a new id, normalised steps and totalDuration = estimate. It is stored at once and not auto-selected. | Native UI | UT-UI |
| SRS-6-114 | Result per file: "✓ <file> — Added" or "✕ <file> — Failed" with every message. Done is enabled only with at least one result and no failure, and Cancel always closes. Added files are never rolled back. Home re-reads on close. | Native UI | UT-UI |
| SRS-6-115 | Parsing: a UTF-8 BOM and CRLF are accepted and blank lines skipped. Fewer than 2 lines gives "CSV must have a header row and at least one data row". A header without Step or Process gives "Missing required header: "Step" or "Process"". | Domain | UT-Dom |
| SRS-6-116 | Columns are read by position, comma-separated, with no quoting. The 10-column layout is normal. The legacy 5-column `Step,Process,Temperature,Intensity,Time` is accepted, recognised from the header. | Domain | UT-Dom |
| SRS-6-117 | Per row (a failing row is reported and skipped, and the file fails): at least 4 columns ("Row i: Not enough columns (need at least 4)"). Process is exactly Heating, Drying, Cure, Cooling, Bleacher or Nitrogen, case-sensitive ("Row i: Invalid process …"). Time 1-120 (Bleacher 1-720) on Heating / Drying / Cure / Bleacher rows, fractions dropped ("Row i: Invalid time …"). Temperature 30-80 (Drying 30-50, Cooling 30-75) ("Row i: Invalid temperature …"). UV 10-100 ("Row i: Invalid UV intensity …"). | Domain | UT-Dom |
| SRS-6-118 | Blank values: temperature becomes 40 °C on heated rows and 25 °C on Cooling (which then always fails, OI-41). UV becomes 30 %. An unknown or blank cooling mode becomes Medium. An unknown Timer / UV start keeps the default (at temperature). | Domain | UT-Dom |
| SRS-6-119 | With no parsable row and no other message: "No valid steps found". | Domain | UT-Dom |
| SRS-6-120 | The CSV header columns, in this order: `Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,UVRampPercent,CoolingMode,Ventilation`. A missing or invalid Step is replaced by the row number, and steps are renumbered. Temperature `off` on Cure/Bleacher means UV only, and blank means Nitrogen. Time is blank for Cooling / Nitrogen. TimerMode is `on-ramp` or `on-target`. UVStart is `at-start` or `at-target`. UVRampPercent is read when 10-100, else ignored, and exported blank. CoolingMode is `fast`, `medium` or `slow`. Ventilation is `on` or `off`, only on UV-only rows. | Domain | UT-Dom |
| SRS-6-121 | Start Cure sequence, step 1: the swiped row becomes active. A print whose material is not on the machine answers "No program named <x> is on this machine". A gesture during a start in progress is ignored. | Native UI | UT-UI |
| SRS-6-122 | Critical-alert gate: any active critical opens "Critical alert active", listing up to four as "<code> — <message> (<detail>)" with "A cure cannot start while a critical alert is active. Handle it/them on the Alerts screen first:". Close returns to Home, Go to alerts opens Alerts, and nothing starts. | Native UI | UT-UI |
| SRS-6-123 | Door gate: a door reported open gives "Close the door to start the cure" (OK only) and nothing starts. An unknown door state does not block. | Native UI | UT-UI |
| SRS-6-124 | Nitrogen-only guard: when every step is an N2 purge and Nitrogen Mode is off, "Cannot Start Cure" shows "This material contains only nitrogen purge steps, but nitrogen is not enabled on the system." / "Enable nitrogen in Settings or choose a different material." and OK returns to Home (registry 6014, not raised as an alert). | Native UI | UT-UI |
| SRS-6-125 | System pre-check: the "Running System Pre-Check" dialog runs a fan test on all fans. A fan not already running is driven at 100 % for 2 s, then every fan is measured for 1 s and judged against the fan-health limits: FAIL when not turning or at or below its stop threshold, WARN when worn. WARN does not hold the start. With no machine answer the check is skipped. | Native UI | UT-UI, UT-App |
| SRS-6-126 | On any FAIL, "Fan failure — process not started" lists "<fan> — not rotating" with the consequence text. Cancel returns to Home with nothing started. Continue anyway overrides the failed fans for this run (recorded) and continues. | Native UI | UT-UI |
| SRS-6-127 | Cure Process opens with the program (and View All print ids). The pre-check dialog stays up until the program start has answered, at most 45 s. | Native UI | UT-UI |
| SRS-6-128 | Machine-side start: N2 steps are dropped when Nitrogen Mode is off. The start is refused if a program is running, another process is active, or the start check fails. Otherwise the machine runs its own checks (heater-fan spin-up, LED-fan pre-flight) and creates the cure-run record. | Application-Process | UT-App, IT-API |
| SRS-6-129 | A refusal closes the pre-check, raises the alert (6015 unless the refusal has its own code), shows the error (with Retry for a temperature-sensor fault), and returns to Home. | Native UI | UT-UI |
| SRS-6-130 | Codes 6001-6014 are shown as inline text or dialogs, not raised as alerts. Alerts raised from Home are 9081 / 9082 (CSV export) and the Start refusal code (6015 or the machine's) (OI-59). | Native UI | Build-gate |
| SRS-6-131 | Every completed right swipe either starts the cure or answers with its reason (critical, door, nitrogen-only, missing program). It is never silently ignored. Below threshold it means nothing, and during a start in progress it is dropped. | Native UI | UT-UI |
| SRS-6-132 | A program with N2 steps and Nitrogen Mode off starts, with the N2 steps dropped. | Application-Process | UT-App |

### P §7 Cure Process Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-7-1 | The Cure Process screen hands the program to the firmware, which sequences it on its own 1 Hz loop. The screen shows the header, one card per step and live gauges, and lets the operator Pause, Continue and Abort. It reacts to faults and ends in completion (with report) or abort / error. | Native UI | UT-UI |
| SRS-7-2 | The header reads "Cure — material · step X/Y · overall %". The active step's status bar reads, e.g., "27°C → 45°C · Timer starts at target". Pause and Abort sit on the active card. While a run is on screen the top bar has no Back, no door control, and inactive navigation. | Native UI | UT-UI |
| SRS-7-3 | The run is owned by the firmware, not the screen. The firmware advances it once per second and reports state, current step, phase and clocks, and the screen renders that at 1 Hz. | Application-Process | UT-App, IT-API |
| SRS-7-4 | States: idle (left by Start); preflight (left when the first step begins, or by Abort); running, with phase ramping / holding / cooling / nitrogen (left on last step done → completed, Pause → paused, Abort → aborted, refused command or run-ending fault → error); paused (outputs stopped, clocks frozen, phase "paused"; Continue → running, Abort → aborted); completed, aborted and error are final, and error carries code and message. | Domain | UT-Dom |
| SRS-7-5 | A program with no steps is refused at Start with 7001 (conflicts with SRS-RUN-5, see Conflicts). | Application-Process | UT-App |
| SRS-7-6 | Start is refused with 6015 while another run is preflight, running or paused, or any process (heating, cooling, UV) is active. An invalid program is refused with the validator's code (7001 / 7002 / 7003). | Application-Process | UT-App, IT-API |
| SRS-7-7 | Pause requires running, Continue requires paused, and Abort requires preflight, running or paused. | Domain | UT-Dom |
| SRS-7-8 | The same run control (status, start, pause, resume, abort, skip) exists on the screen and on `/api/recipe/*` and reaches the same firmware run. The supervision dialogs exist only on the screen (OI-47). | Api | IT-API, UT-UI |
| SRS-7-9 | The screen is reachable only from Start Cure after its gates. It receives the program and, for Cure Together, the pending print ids. | Native UI | UT-UI |
| SRS-7-10 | With Nitrogen Mode off, N2 steps are removed before start: they get no card and are not executed. | Native UI | UT-UI |
| SRS-7-11 | On start the screen acknowledges a door abort still latched from an earlier run, creates a run id, and starts the run. The start answers only after the first step's checks (several seconds), so it runs off the display thread. The screen stays live, and the "Running System Pre-Check" spinner stays until the first status is shown, at most 45 s. | Native UI | UT-UI |
| SRS-7-12 | A start refusal is shown as "Hardware: <message>" and raised on Alerts with its code. A 9010-9012 or 9006 refusal opens the heater-fault dialog with Retry (start again) and Cancel (Home). Any other code shows its registry description, then Home. | Native UI | UT-UI |
| SRS-7-13 | Steps run strictly in program order, and a step ends only by its own completion criterion or Skip. | Domain | UT-Dom |
| SRS-7-14 | Heating completes when chamber ≥ target − 0.5 °C (ramp done) and then the step time has elapsed. Drying (target ≤ 50 °C) completes the same way. | Domain | UT-Dom |
| SRS-7-15 | Cure / Bleaching with a target begins with the heater only (UV Start at temperature) or heater plus UV (on ramp start), and completes as Heating. With "at temperature", UV is lit the moment the ramp completes. | Domain | UT-Dom |
| SRS-7-16 | Cure / Bleaching without a target: heater off, UV on at once, optional ventilation, phase holding. It completes when the step time elapses, with no ramp. | Domain | UT-Dom |
| SRS-7-17 | Cooling (phase cooling) completes at chamber ≤ target + 0.5 °C and has no timer. | Domain | UT-Dom |
| SRS-7-18 | N2 Purge (phase nitrogen) opens the valve, completes after a fixed 120 s, and closes the valve. | Domain | UT-Dom |
| SRS-7-19 | Timer Start "on ramp start" counts the step time from step start through the ramp, but the step never ends before the target is reached. | Domain | UT-Dom |
| SRS-7-20 | With no chamber reading, a ramp is taken as complete after its estimated ramp time (13 / 50 / 80 s per °C for targets up to 45 / 75 / 80 °C, from the start temperature or 25 °C). Cooling is taken as complete after its estimated time (2.5 / 1.5 / 0.8 °C/min). | Domain | UT-Dom |
| SRS-7-21 | At a step end, the next step's commands are issued in the same pass. After the last step every cure output stops and the run completes. | Domain | UT-Dom |
| SRS-7-22 | Each step command passes the step pre-flight first. A refused step command fails the run (error with the refusal's code) and stops every cure output. | Application-Process | UT-App |
| SRS-7-23 | Header progress is elapsed run time (pauses excluded) against the program estimate (from 25 °C, 120 s per N2), and reads 100 % on completion. | Native UI | UT-UI |
| SRS-7-24 | Step cards: pending cards show "Waiting…", finished cards "Done", each with its estimated duration. The active card shows the following. Heating / Drying: RAMP °C during the ramp, REMAINING once holding. Cure / Bleaching: like Heating while ramping with Timer Start at temperature, otherwise remaining time and "UV curing at <i>%" (with "(no heat)" or "(no heat, vented)" for UV-only). Cooling: EST. REMAINING, computed live from temperature and mode rate, and "Cooling to <target>°C · now <t>°C". N2: seconds left of 120. | Native UI | UT-UI |
| SRS-7-25 | Status bar while ramping: "<chamber>°C → <target>°C" with "Timer starts at target" or "Timer running — started with the ramp". During a purge: "Nitrogen Purge · <n>s remaining". Otherwise: "Next: <next step> (Hold at <t>°C Intensity <i>% for <n> min)" or "Final phase (Process complete)". | Native UI | UT-UI |
| SRS-7-26 | During a cure the door is released only by Pause and by Open Door on the completion overlay. | Native UI | UT-UI |
| SRS-7-27 | Pause (active card, only while running and no other dialog is open) opens "Pause the Process?". It explains that heating, UV and gas stop, the door is released, and the step continues where it stopped, with a quality note (surface finish, shape, dimensional accuracy) and the hot-surface caution. Buttons: Keep Running / Pause & Open Door. | Native UI | UT-UI |
| SRS-7-28 | On Pause confirm, the firmware pauses: UV off, heater element off, N2 closed, cooling and ventilation stopped, damper closed. The heater fan gets the normal run-on (30 % up to 15 min). Every run clock freezes. The door magnet is released for 2 s. The full-screen "Process Paused — Door Released" overlay shows the step on hold, the caution and a door gate line. | Application-Process | UT-App, UT-UI |
| SRS-7-29 | On the Paused overlay, Continue is enabled only while the door reads closed (also when state cannot be read). Stop Process aborts. | Native UI | UT-UI |
| SRS-7-30 | Continue: the firmware shifts every clock by the pause length, returns the heater fan to run duty, and re-issues the current step command. Heating, Drying and Cooling re-issue as is. Cure / Bleaching re-issues heater plus UV if UV was lit (or UV-only), heater only if still waiting for target. N2 re-opens the valve. The re-issued command passes pre-flight again, and if refused the run fails. | Application-Process | UT-Dom, UT-App |
| SRS-7-31 | Paused time is excluded from step timers, phase-timing records, overall progress and completion total time. | Domain | UT-Dom |
| SRS-7-32 | Abort (active card; after the run ends the same button only returns Home) opens "Stop the Cure Process?". The dialog says the cycle ends immediately, cannot be resumed and points to Pause, warns that appearance and surface may be affected and that a partially cured model may warp or lose shape and dimensional accuracy, and shows the caution. Buttons: Keep Running / Yes, Stop. | Native UI | UT-UI |
| SRS-7-33 | Abort (or Stop / Abort in any supervision dialog) stops every cure output (the heater fan gets its run-on). The run ends aborted without an error code, fan overrides granted during the run are withdrawn, and the screen returns to Home (OI-46). | Application-Process | UT-App, UT-UI |
| SRS-7-34 | Hot-surface caution in the Pause, Paused and Abort dialogs. At chamber ≥ 40 °C: "Caution — hot surfaces inside. The chamber is at <t>°C. Wear heat-resistant gloves and avoid contact with the chamber and the model." Below 40 °C: "Caution — hot surface. The chamber and the model may still be warm — wear gloves when handling." | Native UI | UT-UI |
| SRS-7-35 | Skip (end the current step now with its timing record, begin the next, or complete on the last step) is available only over the HTTP API. The screen has no Skip button. | Api | IT-API |
| SRS-7-36 | Leaving the Cure screen while the run is preflight, running or paused aborts the run. A run aborted elsewhere (API) takes the screen back to Home. | Native UI | UT-UI |
| SRS-7-37 | Screen supervision runs once per second while running and the machine answers, in the order of the next rows. It handles one condition at a time and opens nothing new while a dialog is up. | Native UI | UT-UI |
| SRS-7-38 | Door reads open: the "Door Open — Process Paused" overlay shows a 10 s countdown ("Close the door now, or the process will be aborted in …") and closes when the door closes. The firmware door watchdog aborts after 10 s with 6016 (OI-42). | Native UI | UT-UI |
| SRS-7-39 | Frozen heater reading (9006): the run pauses, and the heater-fault dialog "Heater switched off — temperature reading frozen" says the machine restarts itself in a minute and heating stays refused until the reading moves. The only choice is Stop process (abort). | Native UI | UT-UI |
| SRS-7-40 | Chamber sensor not reading (9010, heater detail): the run pauses, and the dialog "Heater switched off — temperature sensor not reading" has no continue-anyway. Retry runs Continue, which re-checks the sensor; if still open the run fails with 9010. Stop process aborts. | Native UI | UT-UI |
| SRS-7-41 | Fan failure (a fan critical and not overridden, or a 9020-9025 / 9030-9034 alert naming a fan): the run pauses and a dialog lists each fan "not rotating". Continue anyway overrides those fans for the rest of the run and continues. Stop process aborts. | Native UI | UT-UI |
| SRS-7-42 | LED panel not heating, judged only while UV is on and `led_heating.enabled` (off when shipped): the run pauses, one alert is raised per cold panel (9040 Left, 9041 Right, 9044 Back, 9045 Door), and an LED-failure dialog opens. Continue anyway stops judging those panels this run and continues. Stop aborts. | Native UI | UT-UI |
| SRS-7-43 | Temperature stall: in a ramping or cooling phase, the chamber moved less than 1 °C in the right direction over 5 min, five windows in a row (about 25 min). This raises 7004 and "Temperature Warning": "The system is unable to reach the target temperature of <t>°C. Current temperature: <c>°C. Continuing may cause distortion of the printed models." The run is not paused. Continue restarts the windows. Abort aborts. | Native UI | UT-UI |
| SRS-7-44 | Screen LED-panel check: when UV turns on, every panel thermistor (Left, Right, Back, Door) reading below 30 °C is sampled, skipping Door while bleaching. After 15 s (30 s when intensity < 60 % or bleaching) each must have risen at least max(0.35, 0.8 × intensity/100 × window/15) °C. One check per UV-on stretch, restarted on a new step, a pause and a continue. | Native UI | UT-UI |
| SRS-7-45 | Run-ending faults: on an error end the screen raises the code on Alerts. Door abort 6016 returns to Home at once, with 6016 kept until dismissed. A temperature-sensor code gives the heater-fault dialog with OK. Any other code shows the registry description. Then Home. | Native UI | UT-UI |
| SRS-7-46 | On completed, the status bar reads "Cure complete!" and the "Cure Complete!" overlay shows "The curing process for <material> has been completed successfully.", total time (pauses excluded), step count and a single Open Door button. | Native UI | UT-UI |
| SRS-7-47 | In parallel, the report is built from telemetry (no telemetry means no report), saved with the run, and exported to USB when present. A successful export adds "Saved to USB", otherwise it stays silent. | Application-Platform | UT-App, UT-UI |
| SRS-7-48 | Open Door: for a Cure Together batch the pending print rows are deleted. UV and heater are switched off, the door magnet is released for 2 s, and the screen returns to Home. The heater-fan run-on continues. | Native UI | UT-UI |
| SRS-7-49 | Run start record: run id, status running, material name, step count, step processes, first target temperature, machine serial number. Only the newest 25 runs are kept, and older runs with their telemetry and reports are removed when a new run starts. | Application-Process | UT-App |
| SRS-7-50 | Telemetry every 2 s while running: run time (pauses excluded), chamber temperature, every LED-panel temperature, UV on / wavelength / intensity / per-zone outputs, target temperature, heater PWM and element state, every fan RPM and duty, damper open, N2 active, door closed. | Application-Process | UT-App |
| SRS-7-51 | Phase timing at the end of every step, a skipped one included: program, step, process, target, planned minutes, start and end time, seconds, ramp seconds (heated steps), start and end chamber temperature, cooling mode, UV intensity, timer mode, run id. It is shown in the report. | Domain | UT-Dom, UT-App |
| SRS-7-52 | Alerts during the run: each raised code is recorded with run time and detail. A code that clears and returns is recorded again, and the run-ending failure is added with its code and message. | Application-Process | UT-App |
| SRS-7-53 | Run finish record: status, steps completed, the run alerts, and the sensor issues (not reading) and fan issues (warning or critical with deficit) present at the end (OI-48). | Application-Process | UT-App |
| SRS-7-54 | A run interrupted by power loss is marked error when history is next loaded. | Application-Process | UT-App |
| SRS-7-55 | Each step is executed by one machine command. The command runs the step pre-flight, sets up the outputs and hands temperature control to the heater or cooling loop. It reports a refusal with a code instead of energising anything. | Application-Process | UT-App |
| SRS-7-56 | Heat(target), used by Heating and by the Cure / Bleaching ramp with UV Start at temperature. Pre-flight: fans and sensors. Drives UV off, cooling and ventilation stopped, damper closed, heater loop to target. Ends on the next step's command or Stop all. | Application-Process | UT-App |
| SRS-7-57 | Dry(target ≤ 50 °C). Pre-flight: fans, sensors and the chamber-fan spin test. Drives as Heat. When the heater loop first reports target reached (±1.5 °C), the damper opens and the chamber cooling fan runs 30 % for the rest of the step. The chamber fan stops with the step. | Application-Process | UT-App |
| SRS-7-58 | Cure UV(wavelength, target, intensity). Pre-flight: fans, sensors and the LED-fan spin test. Drives cooling and ventilation stopped, damper closed, heater loop to target, UV on at wavelength and intensity. | Application-Process | UT-App |
| SRS-7-59 | UV only(wavelength, intensity, ventilation). Pre-flight: fans, sensors and the LED-fan spin test. Drives heater element off, cooling stopped, UV on. With ventilation, the damper opens and the chamber cooling fan runs at `ventilation.fan_pwm` (default 60 %). | Application-Process | UT-App |
| SRS-7-60 | Cool(target, mode). Pre-flight: fans, sensors and the chamber-fan spin test. Drives UV off, heater element and heater-fan run-on off, damper open, heater fan 100 %, and the chamber cooling fan at fixed `cooling.mode_pwms` (Fast 100 / Medium 60 / Slow 30 %). Fast also runs the four LED fans at 100 % while no LED is lit. The loop ends itself at chamber ≤ target: chamber fan and LED-fan boost off, damper closed. | Application-Process | UT-App |
| SRS-7-61 | Nitrogen(on/off). No step pre-flight (sensors, critical fan) (OI-43); the line-pressure rules apply instead (0.5-3 bar, sensor reading). Drives only the N2 valve. The last closed-valve reading is kept as the flow-check baseline. The valve closes at purge end, or at once on 9008 or 9015. | Application-Process | UT-App |
| SRS-7-62 | Stop all (end of program, Pause, Abort, run failure, critical fan): UV off, N2 closed, cooling and the Fast LED-fan boost stopped, ventilation off, heater element off (heater fan run-on), damper closed. | Application-Process | UT-App |
| SRS-7-63 | Door abort (door watchdog): heater element and heater fan off at once (no run-on), then Stop all, every fan group 0 %, BOFA off. It is latched as 6016 until acknowledged or the next process start. | Application-Process | UT-App |
| SRS-7-64 | Step pre-flight (1): a fan latched critical and not overridden refuses the step with that fan's code (9020-9025). | Application-Process | UT-App |
| SRS-7-65 | Step pre-flight (2): a latched frozen-reading fault refuses the step with 9006. | Application-Process | UT-App |
| SRS-7-66 | Step pre-flight (3): chamber, Left LED and Right LED thermistors must read valid (−20…120 °C) on three reads 0.5 s apart. Otherwise the step is refused with the first open sensor's code (9010 / 9011 / 9012), and the alert is raised at once. | Application-Process | UT-App |
| SRS-7-67 | Step pre-flight (4), Dry and Cool only: the chamber cooling fan is spun at 100 % for 1.5 s and must read at least `fan_health.led_fan_min_rpm` (100 RPM) over 0.5 s, else refused with 9034. Skipped while cooling already drives that fan, when overridden, and for 30 s after a pass. | Application-Process | UT-App |
| SRS-7-68 | Step pre-flight (5), UV commands: every LED fan of the panels about to be lit is spun the same way, else refused with the first failing fan's code (9030-9033, one alert per fan). Skipped while UV is already on and for 30 s after a pass. | Application-Process | UT-App |
| SRS-7-69 | The heater is never switched on directly. Starting heater control is refused when the target is < 30 °C, cooling is active, the door does not read closed ("Door is Open - Operation Disabled"), or the chamber thermistor is invalid. | Application-Process | UT-App (HeatingLoop) |
| SRS-7-70 | At heater start the heater fan is driven at 100 % (`heater.fan_pwm`), given 2 s to spin up, and must reach 100 RPM (`heater.min_fan_rpm`) over 1 s, else heater control is refused. | Application-Process | UT-App |
| SRS-7-71 | A PI controller with a delta-sigma modulator switches the heater element every 50 ms to reach and hold the target. "At temperature" means within ±1.5 °C. | Application-Process | UT-Dom, UT-App, Bench |
| SRS-7-72 | Every 10 s the heater fan RPM and thermistor are re-checked. A failure, an invalid chamber reading at any sample, or the element state changed from outside switches the heater off at once and records a heater fault. | Application-Process | UT-App |
| SRS-7-73 | UV LEDs are switched directly, with no closed loop. | Hardware | Review |
| SRS-7-74 | From program start to end the heater fan is held at 100 % in every step, also without heating, and a heater stop inside the run keeps that duty. | Application-Process | UT-App |
| SRS-7-75 | On Pause and at run end (completed, aborted, error) the heater fan goes into run-on: element off at once, fan at 30 % (`heating.cooldown_fan_pwm`) for 15 min (`heating.cooldown_sec` = 900). Then every fan goes off (lit-LED fans excepted) and the damper closes. | Application-Process | UT-App |
| SRS-7-76 | A firmware stop or restart during heating, a held run or a run-on stores the run-on still due and resumes it on the next start. | Application-Process | UT-App |
| SRS-7-77 | Only a door abort switches the heater fan off without run-on. | Application-Process | UT-App |
| SRS-7-78 | Three outputs select the wavelength, and every mode change switches all LEDs off first, so two modes are never active together. | Hardware | UT-HW |
| SRS-7-79 | The LED_SWITCH relay (TCA6424A P05 → Q28 → K4, selecting LED_OUT1 / LED_OUT2 at J21) is 1 for 405 nm, 0 for 450 nm, and 0 at rest. | Hardware | UT-HW, Bench |
| SRS-7-80 | SSR 405 nm is GPIO20 through interlock relay K2: ON at 405, OFF at 450, OFF at rest. | Hardware | UT-HW, Bench |
| SRS-7-81 | SSR 450 nm is GPIO16 through interlock relay K1: ON at 405, ON at 450, OFF at rest. | Hardware | UT-HW, Bench |
| SRS-7-82 | GPIO17 (voltage-routing line) is LOW in 405, 450 and rest. The earlier assumption "HIGH = 450 nm" is wrong: with GPIO17 HIGH the door LED driver's 12 V DIM rail measured 0 V (bench 2026-09-07). | Hardware | UT-HW, Bench |
| SRS-7-83 | Panels allowed (`leds.*.modes`): Left, Right, Back and Door at 405 nm; Door only at 450 nm. | Hardware | UT-HW, Review (components.json) |
| SRS-7-84 | The LED fan of a lit panel runs at 100 % (`leds.*.fan_speed`) at 405 nm and 30 % (`led_power.modes.450nm.led_fan_pwm`) at 450 nm, and is off at rest. | Application-Process | UT-App |
| SRS-7-85 | UV turn-on order. (1) All LEDs off, GPIO17 written and verified by read-back, the relay driven to the mode position and verified by read-back. (2) LED-fan pre-flight. (3) For each allowed panel: wait `switch_settle_sec` (0.1 s) from the relay's last move (only if it moved), then SSR enables plus GPIO17 with GPIO17 read back, then DIM PWM and the panel's LED fan on. | Hardware | UT-HW |
| SRS-7-86 | A failed read-back refuses the UV command and no LED is lit. An LED is never lit while the door does not read closed: the hardware layer refuses. | Hardware | UT-HW |
| SRS-7-87 | Brightness: the step intensity (10-100 %) is multiplied per panel by its Developer-Mode calibration factor (0-1.5), clamped to 0-100 %, and driven as PWM duty × 60 % (`led_max_duty`: 100 % brightness = 60 % duty). | Hardware | UT-HW, UT-App |
| SRS-7-88 | A panel below `min_intensity` (10 %) counts as off. With no panel on, both SSRs and GPIO17 go LOW and the relay parks at 0. | Hardware | UT-HW |
| SRS-7-89 | At firmware start every output is put in its safe state and verified: LEDs and SSRs off, N2 closed, GPIO17 LOW, relay at 0. | Hardware | UT-HW |
| SRS-7-90 | Before the firmware runs, boot config `gpio=16,17,20=op,dl` and the early-boot service `scurebox-io-safe` (`deploy/io-safe-boot.sh`: GPIO16/17/20 LOW, TCA6424A P05 = 0) close the window in which the relay net would float HIGH. A hardware pull-down on LED_SWITCH_SIGNAL remains open. | Deploy-Ops | Bench, Review |
| SRS-7-91 | Every NTC is read through a 10 kΩ pull-up divider. A disconnected sensor yields no temperature, and any reading outside −20…120 °C counts as not reading. | Hardware | UT-HW |
| SRS-7-92 | A bad reading is bridged by holding the last good value for up to 15 s (`sensor_filter.glitch_hold_sec`), during which the heater controls on the held value. Only then does it count as open. | Hardware | UT-Dom (SensorGlitchHold), UT-HW |
| SRS-7-93 | Each supervised sensor has its own code. Its alert names only that sensor and clears by itself once it reads again. | Application-Process | UT-App |
| SRS-7-94 | Required sensors TEMP_CHAMBER (9010), TEMP_LEFT_UV (9011) and TEMP_RIGHT_UV (9012) are critical. Open for at least one full minute raises the alert, checked every second from start-up. While a required sensor is open no step can start. | Application-Process | UT-App |
| SRS-7-95 | Heater sensor rule: the heater is never on while TEMP_CHAMBER does not read. If it stops reading while heating, the heater is switched off and 9010 is raised at once (not after a minute), and the Cure screen pauses the run. | Application-Process | UT-App |
| SRS-7-96 | Diagnostic sensors TEMP_BACK (9013) and TEMP_DOOR (9014): open for one minute raises a warning, and processes run as usual. | Application-Process | UT-App |
| SRS-7-97 | 9006 Frozen reading: while heating with the heater ≥ 50 % output for 90 s continuously, TEMP_CHAMBER must move ≥ 0.01 °C (`frozen_reading`). Otherwise critical 9006 is raised, the element switches off at once (fan runs on), the alert names the reading and the stuck value, and every heating start is refused with 9006. | Application-Process | UT-App |
| SRS-7-98 | 9006 consequences: the machine restarts itself 60 s after the alert (`reboot_after_sec`), but not before the heater-fan run-on ends. The latch is kept on disk and read at start-up, so heating stays refused after the restart. A chamber holding setpoint (output < 50 %) is not judged. The latch clears when the reading moves ≥ 1 °C or goes open (then 9010). | Application-Process | UT-App |
| SRS-7-99 | 9007 Heater not heating: while the heater loop drives ≥ 99 % for 600 s continuously and the chamber rose < 0.5 °C above the window's lowest reading (`no_heat`), judged on the ramp up only. Once within `heating.at_temp_band` (1.5 °C) of target the rule is off until the next heating start or a new target. Then critical 9007 "Heater Not Heating - Check Voltage Selector / Fuse" is raised, the element switches off (fan runs on), the alert names both causes (110/230 V selector not fully in position, blown heater fuse), and the run ends error with 9007. The latch clears when heating is started again. | Application-Process | UT-App, Bench |
| SRS-7-100 | Other heater faults without their own code (e.g. heater fan < 100 RPM at the 10 s check) end the run error with 6015 and "Heater stopped: <fault>". 9010 and 9006 do not end the run by themselves: the Cure screen pauses and asks. | Application-Process | UT-App |
| SRS-7-101 | Fan health: every tach fan (heater, chamber cooling, four LED) is compared once per second with nominal RPM at the commanded duty (`fan_health.nominal_rpm`, linear interpolation). Heater 5,925 RPM at 100 %. Chamber cooling 4,790 / 2,690 / 1,235 RPM at 100 / 60 / 30 %. LED fans 3,560 / 1,135 RPM at 100 / 30 %. With the damper open, chamber cooling uses `nominal_rpm_damper_open` 4,075 / 2,470 RPM at 100 / 60 %. | Application-Process | UT-Dom (FanHealthEvaluator), Bench |
| SRS-7-102 | A fan reading counts only while commanded ≥ 30 % and from 5 s after a duty change, and a condition must persist one full minute. | Domain | UT-Dom |
| SRS-7-103 | ≥ 10 % below nominal for one minute raises a warning "replace the fan", per fan: 9060 heater, 9061 chamber cooling, 9062-9065 Left / Right / Back / Door LED fan. The machine keeps working. | Domain | UT-Dom |
| SRS-7-104 | ≥ 20 % below nominal (heater fan ≥ 11.8 %, `critical_below_pct_by_fan`) for one minute, or ≤ 5 % of nominal (stopped) for 5 s, is critical, per fan: 9020 heater, 9021 chamber cooling, 9022-9025 Left / Right / Back / Door. Every cure output stops at once and no step can start (refused with that code). | Application-Process | UT-Dom, UT-App |
| SRS-7-105 | The critical fan latch holds until the fan runs at nominal for a full minute, the operator dismisses the fan alert on Alerts (acknowledge), or the fan is overridden (Continue anyway). | Application-Process | UT-App |
| SRS-7-106 | The fan alert names the exact fan with measured and expected RPM, duty and deficit. The machine state publishes per fan duty, measured and expected RPM, deficit and status (ok / warn / critical / pending / idle). | Api | IT-API, UT-App |
| SRS-7-107 | LED connection supervision (9040-9043) exists but is off when shipped (`led_heating.enabled = false`, decision 2026-09-16; OI-63). When enabled, Left / Right are judged by TEMP_LEFT / TEMP_RIGHT: lit at ≥ 30 % system power, after 90 s of accumulated light the panel must have risen ≥ 1.0 °C above the baseline taken when lit (re-lit within 120 s keeps the old baseline), else critical 9040 / 9041. | Application-Process | UT-App |
| SRS-7-108 | Once proven, a fall ≥ 1.0 °C below peak at the current power level (corrected for a falling chamber) lasting 30 s raises 9042 / 9043 "LED Panel Temperature Dropped During Cure", with 120 s settle after a power change. The run is not aborted. Each alert clears when the panel heats again (within 0.5 °C of peak for a drop). | Application-Process | UT-App |
| SRS-7-109 | The nitrogen line is judged once per second from the line-pressure sensor against `pressure_sensor` (min_bar 0.5, max_bar 3.0). Only a real bar value counts: a read error, a saturated input or a pressure-switch configuration never blocks, never closes the valve, and never alerts. | Application-Process | UT-App |
| SRS-7-110 | 9008 over pressure (critical): above 3 bar, opening is refused ("N2 supply pressure too high (X.X bar > 3.0 bar) - nitrogen not opened. Lower the regulator below 3 bar."). Rising above the limit while open closes the valve at once. The alert self-clears when back within the limit, and the valve is not reopened by itself. | Application-Process | UT-App |
| SRS-7-111 | 9009 no supply (warning): below 0.5 bar, opening is refused ("No nitrogen supply - line pressure X.X bar is below 0.5 bar. Check the nitrogen line and regulator."). It is judged only with the valve closed and settled (3 s after it last closed). An open valve reading near zero is normal and never closes it or alerts. | Application-Process | UT-App |
| SRS-7-112 | 9015 not flowing (critical): when the valve opens, the pressure must drop by `flow_check_min_drop_bar` (0.3 bar) from the closed baseline within `flow_check_window_sec` (5 s). Otherwise the valve closes, 9015 is raised ("Nitrogen is not flowing into the chamber … Check the nitrogen valve and the tube to the chamber."), and a running program fails. | Application-Process | UT-App |
| SRS-7-113 | 9015 gives no verdict without real readings before and after opening, when the valve closes before the window ends, or when it reopens within 3 s of closing. It clears at the next opening. `flow_check_enabled` switches it off. | Application-Process | UT-App |
| SRS-7-114 | 9016 sensor not reading (warning): after `not_reading_after_sec` (20 s) without a valid reading (failed read past the glitch hold, saturated input, or output below 90 % of the sensor minimum or above 110 % of its maximum; an unplugged 1-5 V sensor reads about 0 V). It clears at the first valid reading. While active, opening N2 is refused. An open valve is not closed when the reading vanishes. With `pressure_sensor.required = false` the sensor is never judged. | Application-Process | UT-App |
| SRS-7-115 | BOFA: the Settings switch states an extractor is connected and is not a manual on/off. On a declaring machine the extractor runs whenever the air-intake fan runs and stops with it. A non-declaring machine never drives the output. Declaring while air moves starts it at once, undeclaring stops it at once, and a door abort kills it. | Application-Process | UT-App |
| SRS-7-116 | BOFA speed is driven on the 0-10 V reference: PCA9685 channel 10, two RC stages, amplified ×3.3 into 4DA_ANALOG, scaled by `bofa.max_duty` (60 %) so 100 % = 10 V. The speed is fixed at 10 % for now, tunable from Settings or `POST /api/bofa/policy` without a rebuild, and a re-tune while the intake runs applies at once. | Hardware | UT-HW, Bench (OI-72) |
| SRS-7-117 | BOFA supply: 24 V on 4DA_BOFA_EN (GPIO6), opened and closed with the extraction (supply first then speed on the way up, speed to zero then supply on the way down). A machine at rest leaves the connector dead. | Hardware | UT-HW, Bench |
| SRS-7-118 | BOFA presence: 4DA_BOFA_PRESENT (GPIO18) reports a plug-in. A switch claiming a unit the connector does not see raises warning 9048 BOFA Unit Not Detected, which stops nothing. An unreadable line never raises it. Polarity has not been measured (OI-72). | Application-Process | UT-App, Bench |
| SRS-7-119 | UV light confirmation: the Left and Right photoresistors (about 55 kΩ dark, never converted to temperature). While a panel is lit ≥ `uv_light_check.min_intensity` (10 %) for `confirm_sec` (5 s), it must read below dark baseline × `lit_ratio` (0.6), else warning 9046 (Left) / 9047 (Right). Nothing stops. Not calibrated (OI-73). | Application-Process | UT-App, Bench |
| SRS-7-120 | Panel temperatures used by the heater, the sensor supervision and the LED checks are the real thermistors TEMP_LEFT / TEMP_RIGHT. | Application-Process | Review |
| SRS-7-121 | Door watchdog: once per second, if the door reads open while any output is live (heater control, cooling, UV, N2 valve, extraction, or a controller-commanded fan group) for `door_sensor.abort_after_sec` (10 s), the door abort runs and the program ends error with 6016. Closing within 10 s cancels it. | Application-Process | UT-App |
| SRS-7-122 | An unreadable door sensor blocks heater and LED starts like an open door. The watchdog acts only on a door that reads open. | Application-Process | UT-App |
| SRS-7-123 | Output watchdog: the firmware writes a heartbeat once per second. A separate process checks it every 500 ms and, when it is older than 20 s, cuts the heater element, the four UV dimming channels and both UV SSRs, repeating every 5 s while silent. Fans, damper and valves keep running. A clean shutdown removes the heartbeat (disarming the watchdog), and on shutdown the firmware switches every output off. | Hardware | UT-HW, UT-Dom (WatchdogMonitor), Bench |
| SRS-7-124 | 9017: the watchdog writes a trip record beside the heartbeat whenever it cuts. On return the firmware reads it and raises critical 9017 Firmware Stopped Responding, latched until acknowledged (Alerts, or `POST /api/watchdog/ack`). A run in progress ends failed with 9017. | Application-Process | UT-App, IT-API |
| SRS-7-125 | After any such silence the firmware comes back safe: output writes issued while unresponsive are dropped rather than landing late, every output is switched off, and nothing resumes by itself. | Application-Process | UT-App |
| SRS-7-126 | The Cure Process flow is the swimlane `docs/diagrams/cure-process-flow.drawio` (UI sCure, FW, Storage). The per-mode flow is an inline Mermaid with unique node-id prefixes D·/H·/U·/C·/N·. | Deploy-Ops | Review |
| SRS-7-127 | Drying: time, target 30-50 °C (the runner refuses > 50 °C), Timer Start. Pre-flight includes 9034. Damper closed, heat to target. The first time at target ±1.5 °C, the damper opens and the chamber fan runs 30 % for the rest while the heater holds. The step ends at ramp done (≥ target − 0.5) and time elapsed. The next command (or Stop all) sets fan and damper. | Application-Process | UT-App |
| SRS-7-128 | Heating: with Timer Start at temperature, the time counts from target − 0.5 °C reached. With on ramp start it counts from step start, but the step never ends before target. At end the heater keeps its fan at run duty and the next command takes over (last step: Stop all). | Application-Process | UT-App |
| SRS-7-129 | Cure lights every panel allowed at 405 nm (Left, Right, Back, Door). Bleaching lights those allowed at 450 nm (Door only). With UV Start at temperature, the UV is lit at target − 0.5 °C by a new step command with its own pre-flight and LED-fan test. Target and intensity are held until time elapses. | Application-Process | UT-App |
| SRS-7-130 | UV only: the element stays off while the heater fan keeps run duty. UV is lit at once and time starts immediately. With ventilation the damper opens and the chamber fan runs at `ventilation.fan_pwm` (60 %). | Application-Process | UT-App |
| SRS-7-131 | There is no LED self-test at step start: only the LED-fan spin test (9030-9033). The lit-panel LED test runs only in the power-on self-test. | Application-Process | UT-App |
| SRS-7-132 | Cooling has no closed-loop rate control, and the rate is measured for status only (OI-44). The loop stops at target (fans off, damper closed) if the next step has not taken over. | Application-Process | UT-App |
| SRS-7-133 | N2 Purge runs only with Nitrogen Mode on, otherwise it is dropped, and an N2-only program cannot start. The valve is open for a fixed 120 s, then closed. No other output is touched, and no pre-flight / availability check runs at the step (OI-43). The following Cooling vents through the open damper. Max two purges. | Application-Process | UT-App |
| SRS-7-134 | Actuator signals. Damper: closed in Heating and heated Cure; in Drying open only from target; open for the whole of Cooling and in a ventilated UV-only step; closed by Stop all. | Application-Process | UT-App |
| SRS-7-135 | Chamber cooling (air-in) fan: off in Heating and heated Cure; 30 % in Drying from target; Fast 100 / Medium 60 / Slow 30 % fixed in Cooling; `ventilation.fan_pwm` 60 % in a ventilated UV-only step. | Application-Process | UT-App |
| SRS-7-136 | N2 valve: open for the fixed 120 s of a purge, otherwise closed. A purge is never the last step. | Application-Process | UT-App |
| SRS-7-137 | Temperature control: on through Drying, Heating and heated Cure (ramp and hold); off in Cooling, UV-only and N2. The Cooling target is a stop threshold, not a tracked setpoint. | Application-Process | UT-App |
| SRS-7-138 | Heater fan: 100 % for the whole program in every step; after the run and while paused, 30 % run-on for 15 min, then off. | Application-Process | UT-App |
| SRS-7-139 | UV 405 (Cure) and 450 (Bleaching): each step is one or the other, never both. The rising edge follows UV Start (target − 0.5 °C, or step start), and UV-only lights at step start. 450 nm is Door panel only. | Application-Process | UT-App |
| SRS-7-140 | LED cooling fans: each lit panel's fan runs with its panel (405: 100 %, 450: 30 %), preceded by the spin test (100 % for 1.5 s). In Fast cooling all four run at 100 % while no LED is lit. | Application-Process | UT-App |
| SRS-7-141 | The signal list is normative over the inline timing figure. The figure predates sCure CS, is regenerated with `node tools/gen-timing.mjs docs/screenshots/timing.svg` (OI-45). | Deploy-Ops | Review |

### P §8 Cure History Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-8-1 | Cure History is the log of the runs recorded on the device, opened from the top-bar History icon. It lists past runs (and a run in progress) with outcome, timing, step progress, and sensor / fan problems, plus a detail panel. From the panel the operator exports the report to USB and deletes one run or all. | Native UI | UT-UI |
| SRS-8-2 | The History icon does nothing while Cure Process is open. Top-level moves replace the history entry, so Back (panel or top bar) returns to the previous screen, else Home. | Native UI | UT-UI |
| SRS-8-3 | Every visit reads the history from the device store: the DB when configured and reachable at start-up, else the local files. The history is device-local, not organization-scoped. If the store cannot be read, the list is shown empty and the failure is logged. | Native UI | UT-UI |
| SRS-8-4 | Retention is the newest 25 runs. When a new run starts, older runs are removed with their telemetry and saved report. The header shows "last 25 kept". | Application-Process | UT-App |
| SRS-8-5 | Runs are listed newest first by start time, and the header shows the total count (N). | Native UI | UT-UI |
| SRS-8-6 | Empty state: "No cure sessions yet." with Delete all hidden. | Native UI | UT-UI |
| SRS-8-7 | On open, the run passed in is selected, else the newest. A tap selects and highlights. With no selection the panel shows "Select a run to see its telemetry." | Native UI | UT-UI |
| SRS-8-8 | Each run writes its own entry: Running at start, a telemetry sample every 2 s, and at end the final status, end time, duration, steps completed, sensor and fan issues at end, and run alerts. | Application-Process | UT-App |
| SRS-8-9 | With the device-file store, a run left Running by power loss becomes Error at the next start. The DB store does not do this (OI-69). | Application-Process | UT-App |
| SRS-8-10 | On completion the report is built, saved with the run and exported to USB once automatically. Cure History re-exports on request. | Application-Platform | UT-App |
| SRS-8-11 | Row status icon: Completed is a green ✓, Stopped an orange ⚠, Error a red ✕, Running a pulsing ▶. The status pill is Completed / Stopped / Error / Running, and an operator abort is labelled Stopped. | Native UI | UT-UI |
| SRS-8-12 | Row: material name; start "dd MMM yyyy HH:mm:ss" and, once finished, "to HH:mm". | Native UI | UT-UI |
| SRS-8-13 | Row sensor issues are shown only when a sensor was not reading at the end: "Sensor disconnected during run: <list>" (Chamber, Left LED, Right LED, Back LED, Door LED). Orange, or red if any is critical. | Native UI | UT-UI |
| SRS-8-14 | Row fan issues are shown only when a fan was below nominal at the end: "Fan below nominal during run: <fan> (-N %)" (heater, chamber cooling, left / right / back / door LED fan). Orange, or red if critical. | Native UI | UT-UI |
| SRS-8-15 | Duration format: "Ns" under a minute, "Mm Ss" under an hour, else "Hh Mm"; "--:--" when unknown. | Native UI | UT-UI |
| SRS-8-16 | "X/Y steps" (completed / total) is shown orange when fewer steps were completed than the program has. | Native UI | UT-UI |
| SRS-8-17 | The detail panel shows material, status pill, start date and time, duration, steps, "Max N.N°C" chamber, telemetry sample count, and "Phases: A → B → …". | Native UI | UT-UI |
| SRS-8-18 | The panel has no graphs and notes "Temperature, UV and fan graphs are in the exported report." Buttons Back, Delete and Export report; Delete and Export are shown only with a selection. | Native UI | UT-UI |
| SRS-8-19 | Export report is enabled only when the run has telemetry and no export is running. While running it reads "Exporting…" and Delete / Delete all are disabled. | Native UI | UT-UI |
| SRS-8-20 | A report already saved with the run is exported unchanged. Otherwise one is built from telemetry, saved, then exported. | Application-Platform | UT-App |
| SRS-8-21 | The file goes to the root of the first USB drive found, and a same-name file is overwritten. Names: `cure-report-<Material>-<yyyy-MM-dd>.html` for a re-exported saved report, `scure-report-<Material>-<yyyyMMdd-HHmm>.html` for a newly built one (OI-49). | Application-Platform | UT-App |
| SRS-8-22 | Export results, cleared after 3 s: "Saved to USB" (green), "No USB drive found" (9081), "Could not write to the USB drive" (9082), "No telemetry recorded", "Report export failed" or the machine text. These failures raise no Alerts-screen alert. | Native UI | UT-UI |
| SRS-8-23 | Report content (self-contained, printable HTML): System Name, SN, report ID, date; status, duration, steps, max chamber temperature, 405 nm and 450 nm UV times, sensor / fan summary; program phases; Program steps table (program values plus measured phase timings); Timing diagram (all signals on one axis: steps, every thermistor and target, heater output, each fan's PWM duty with measured RPM, each LED zone's output by wavelength, damper, N2, door); Alerts during the run; chamber temperature plus UV activity chart; LED module temperature chart; Fan speeds chart with avg / min / max RPM and running share per fan; sensor and fan notes. Runs from older firmware show only the sections they have data for. | Application-Platform | UT-App (CureReportBuilder) |
| SRS-8-24 | Delete removes the selected run, only a finished one. It confirms with "Delete this run?" / "<Material> (<date>) and its report are deleted from the machine and from sCure Cloud. This cannot be undone." Then the next run is selected, and "Run deleted" or "Delete failed" shows for 3 s. | Native UI | UT-UI |
| SRS-8-25 | Delete all (list header) removes every finished run after "Delete the whole cure history?" / "All N runs and their reports are deleted from the machine and from sCure Cloud. This cannot be undone." A run in progress is kept. | Native UI | UT-UI |
| SRS-8-26 | Any operator can delete, with no PIN or role. A delete removes telemetry and saved report too. | Native UI | UT-UI |
| SRS-8-27 | Deleted run ids are queued for cloud deletion, sent on the next successful sync, and kept until the portal confirms. Offline deletes reach the cloud later. | Application-Platform | UT-App (CloudReportDeletions) |
| SRS-8-28 | Runs cannot be edited, and the screen has no filter or search. | Native UI | UT-UI |
| SRS-8-29 | Cure-run data model: id (string); materialName; steps; stepsCompleted; startedAt (device local); endedAt (null while running); duration (seconds, at finish); status running / completed / aborted / error (aborted shown as Stopped); phases string[]; targetTemp; serialNumber (optional); telemetry sample[]; sensorIssues {sensor, critical}[]; fanIssues {fan, deficitPct, critical}[]; alerts {t, code, message}[] (time in s from start, also when cleared before the end). | Domain | UT-Dom, IT-API |
| SRS-8-30 | Telemetry sample: elapsed time, chamber temperature, UV on and wavelength (405 / 450), LED panel temperatures, every fan RPM; and for the timing diagram, target temperature, heater output % and state, each fan PWM duty, every thermistor, each LED zone output %, UV intensity, damper open, N2 active, door closed. Fields absent in older runs are omitted. | Domain | UT-App |
| SRS-8-31 | A saved report (HTML plus summary) is stored with its run and removed with it. | Application-Platform | UT-App |
| SRS-8-32 | The flow is `docs/diagrams/cure-history-flow.drawio` (lanes UI sCure, Machine, Storage, Cloud). | Deploy-Ops | Review |

### P §9 Error Management, Alerts Screen & Registry

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-9-1 | Every error and warning is defined once in the central registry `config/errors.json` (`_meta.version` 4.0.0). Text (message, description, troubleshooting, support and video links) is resolved by code. The firmware reads it once at start, with a built-in minimal registry as fallback. Note: §9 intro says 76 records, §9.11 says 84 (see Conflicts). | Domain | UT-Dom (ErrorRegistry) |
| SRS-9-2 | Every thermistor, fan and LED panel that can fail has its own code (title, troubleshooting, repair video). The grouped codes 9001-9005, 9050 and 9051 are no longer raised and remain as family titles, so older reports and logs still resolve. Rules reacting to a fault kind match the whole family. | Domain | UT-Dom |
| SRS-9-3 | The record shape is uniform: code (number, system), key (UPPER_SNAKE slug used in logs, system), message (editable), severity critical / warning (system; an unknown code is treated as warning), category (provisioning, network, validation, storage, io, selection, safety, process, maintenance, update, security, system; system field), layer daemon / backend / ui (system, kept from the earlier stack; OI-62), description (editable), troubleshooting string[] (editable), supportUrl (editable, default `support.docsBase/<code>`), videoUrl (optional, set by the service team, not yet in editableFields; OI-62). | Domain | UT-Dom, Review |
| SRS-9-4 | The registry carries a support block (email, phone, chat, docsBase) shown on every alert detail, and a `_meta` block (version, lastUpdated, ranges, editableFields, systemFields). | Domain | Review |
| SRS-9-5 | Ranges by SRS section: 3000-3999 Setup (SN provisioning), 4000-4999 Setup Name (name validation, config / SD persistence), 5000-5999 Connect Organization (org CSV / ID), 6000-6999 Home (editor, CSV import, view-all / Cure Together, start-cure, pre-cure refusal, door abort), 7000-7999 Cure Process (parameter validation, stall / abort), 8000-8999 Cure History (reserved), 9000-9999 Error Management (device / hardware 9001-9079, system faults 9080-9099). A range is fixed for the life of a code. `_meta.ranges` mirrors this table and must stay in sync. | Domain | Review, Build-gate |
| SRS-9-6 | 9xxx sub-ranges: 9001-9005 families; 9006-9007 heater supervision; 9010-9014 sensors; 9020-9025 fan stop; 9030-9034 fan not spinning; 9040-9045 LED panel; 9050-9052 grouped LED-sensor / fan-wear families plus NFC; 9060-9065 fan wear; 9080-9099 system / service. Severity is per record, not implied by sub-range. | Domain | Review |
| SRS-9-7 | A machine refusal returns `{ok:false, code, message}`. A refusal with its own code (e.g. 9010, 9020-9025, 9030-9034, 9006) keeps it; one without is reported as 6015. Request validation returns 7001 / 7002 / 7003. | Api | IT-API |
| SRS-9-8 | The machine state carries the list of active supervision codes, each with one detail line naming the component and measured value (e.g. "Heater fan (FAN_HEATER): 4,900 RPM measured, 5,925 RPM expected …"). The screen mirrors the list. | Api | IT-API, UT-UI |
| SRS-9-9 | Service operations (network diagnostics, USB export, log export, update) return their own 908x code with the message. | Application-Platform | UT-App, IT-API |
| SRS-9-10 | Critical: red alert-octagon, red bell, grouped under Critical Errors, status strip in fault colour. While any critical alert is active on Alerts, no cure can start from Home. | Native UI | UT-UI |
| SRS-9-11 | Warning: orange alert-triangle, orange bell, grouped under Warnings, strip in warning colour. Never blocks a start or stops a run by itself. | Native UI | UT-UI |
| SRS-9-12 | Blocking uses two independent gates: the screen gate on Start Cure, and the machine checks before every process step. The machine gate does not depend on the screen. | Application-Process | UT-App, UT-UI |
| SRS-9-13 | Machine gate on every step (heat, dry, cure UV, UV only, cool). A latched 9020-9025 fan not overridden refuses with that fan's code, naming every blocking fan. A latched 9006 refuses with 9006. An open required thermistor (three reads 0.5 s apart) refuses with the first open code and raises each at once. A UV step with an LED fan not spinning (9030-9033) is refused without lighting UV. A Dry / Cool step with the chamber fan not spinning (9034) is refused. | Application-Process | UT-App |
| SRS-9-14 | Nitrogen step: a line outside 0.5-3 bar or a sensor not reading (9008 / 9009 / 9016) means the valve is not opened and the refusal carries that code. Only the nitrogen step is gated. | Application-Process | UT-App |
| SRS-9-15 | During a run: a fan stop (9020-9025) switches every output off, and the Cure screen offers override or stop. 9010 while heating switches the heater off at once, and the screen pauses with Retry / Stop. 9006 switches the heater off, stops the run (no Retry) and restarts the machine. 9007 or another heater fault switches the heater off and ends the run error. | Application-Process | UT-App |
| SRS-9-16 | During a run: 6016 (door open with outputs live for 10 s) switches every output off, aborts, and latches until acknowledged. 9008 while open closes the valve, does not reopen it, and the run continues. 9015 closes the valve and fails the run. 9017 means heater and UV were cut, and on recovery all outputs are off, the run fails, and 9017 is latched until acknowledged. | Application-Process | UT-App |
| SRS-9-17 | Warnings 9013, 9014, 9060-9065, 9052, the 908x service warnings and 7004 never block. | Application-Process | UT-App |
| SRS-9-18 | Machine-level lifecycle: detect (supervision 1 Hz; pre-flights and door watchdog on their own triggers), raise (enters the machine list with detail), clear (most self-clear). Latched release rules: fan stop by 60 s at nominal or an operator acknowledge while not failing; 9006 by a move ≥ 1 °C or reading open; 9007 by the next heating start; 6016 by acknowledge or the next process start. | Application-Process | UT-App |
| SRS-9-19 | Screen level: every machine code is raised with its detail. Screens also raise codes for refused or failed operations (cure-start refusal, USB export, enabling NFC). A new alert gets a unique instance id, code, timestamp, detail and dismissed:false. | Native UI | UT-UI (AlertService) |
| SRS-9-20 | The bell shows the active count and highest severity. Critical and warning counts are reported to the machine status strip. | Native UI | UT-UI |
| SRS-9-21 | Dismiss is one alert at a time, with no "clear all". Dismissing 6016 acknowledges the door abort on the machine. Dismissing any fan code (9020-9025, 9030-9034, 9060-9065, or grouped 9002 / 9003 / 9051) acknowledges the fan alarms. The machine logs each fan acknowledge with its time and what it released. | Native UI | UT-UI, UT-App |
| SRS-9-22 | An alert stays in the screen's active set until dismissed, even after the machine cleared it (OI-61). | Native UI | UT-UI |
| SRS-9-23 | sCure Cloud: the machine samples its alert list every second and keeps a 48 h alert log (code, detail, raised and cleared time; max 300 entries), uploaded with each sync for the portal's "Errors today". | Application-Platform | UT-App |
| SRS-9-24 | Status strip: the screen reports counts on every change and every 30 s, and a report is honoured for 90 s. A critical count drives the fault state, a warning count the warning state. | Application-Platform | UT-App, UT-UI |
| SRS-9-25 | The bell badge counts active (undismissed) alerts that resolve to a registry record: red with any critical, orange with only warnings. The bell is inert during a cure while the badge keeps counting. Tapping it opens Alerts, and Back returns to Home. | Native UI | UT-UI |
| SRS-9-26 | Alerts list: newest first, grouped Critical Errors / Warnings. Each row has a severity-coloured code chip, registry message, time raised "dd MMM yyyy HH:mm" (local) and a support-URL QR. Codes not in the registry are neither listed nor counted. | Native UI | UT-UI |
| SRS-9-27 | Alerts empty state: "All Clear" / "No active alerts." | Native UI | UT-UI |
| SRS-9-28 | Alert detail: "code: message" with Dismiss Alert at the top; Status Critical / Warning; Problem Description (machine detail line, then registry description); numbered Troubleshooting Steps; documentation QR plus URL (supportUrl or docsBase/<code>); a second QR for videoUrl when present; Need Help? with support email, phone and Live Chat; Back. | Native UI | UT-UI |
| SRS-9-29 | Dismiss removes the alert (with the machine acknowledges) and returns to the list, and counts, bell and groups update live. If the shown alert leaves the active set, the screen returns to the list. | Native UI | UT-UI |
| SRS-9-30 | The Alerts flow is `docs/diagrams/alerts-flow.drawio` (Machine, UI sCure, Storage). | Deploy-Ops | Review |
| SRS-9-31 | Screen alerts (active and dismissed) are stored in `data/ui-alerts.json` and survive restart and reboot. | Native UI | UT-UI |
| SRS-9-32 | On load, stored alerts whose code is no longer in the registry are dropped, and an undismissed 9052 is dropped (the machine re-raises it if it still applies). | Native UI | UT-UI |
| SRS-9-33 | The fallback registry (missing or malformed file) covers only the codes the firmware raises, with short messages and no troubleshooting. It differs from errors.json in some keys, messages and severities (OI-60). | Domain | UT-Dom |
| SRS-9-34 | No demo alerts are seeded. | Native UI | UT-UI |
| SRS-9-35 | Governance: CS / support may edit message, description, troubleshooting and supportUrl. The service team sets videoUrl with the registry editor. Engineering owns code, key, severity, category and layer, and allocates codes. An edit takes effect at the next application start. Delivery to installed machines is not defined (OI-62). | Domain | Review |
| SRS-9-36 | Adding an error: allocate the next free number in its section range (component faults in the family's per-component sub-range), never reuse or renumber, and add it to the registry, the §9.11 catalog and the diagram node. | Domain | Review, Build-gate |
| SRS-9-37 | The build fails unless every code the firmware declares has a registry record, every registry code is implemented or listed as a known gap with its reason, a closed gap has left that list, and every declared code is used somewhere (`tests/SCureBox.Domain.Tests/Programs/ErrorCoverageTests.cs`). | Domain | Build-gate |
| ERR-01 | All operator-facing error / warning text shall be defined in the central registry. No error message is hard-coded in application logic (OI-59). | Domain | Review, Build-gate |
| ERR-02 | Each error shall have a unique, stable numeric code that never changes once assigned and is never reused. | Domain | Build-gate, Review |
| ERR-03 | The first digit of the code shall identify the SRS section where the error is documented. | Domain | UT-Dom |
| ERR-04 | Each error shall record its originating layer, independent of its number. | Domain | UT-Dom |
| ERR-05 | A code raised by the machine shall reach the screen, the cure report and sCure Cloud unchanged; no consumer re-words or re-maps it. | Application-Platform | UT-App, IT-API |
| ERR-06 | The screen shall resolve a code to message / description / troubleshooting / support and video links via the registry at display time. | Native UI | UT-UI |
| ERR-07 | Editing a registry message shall change the displayed text with no code change, effective at the next application start. | Domain | UT-Dom |
| ERR-08 | Only editableFields may be modified through the CS path; systemFields are immutable through it. | Domain | Review |
| ERR-09 | Each active alert shall carry a unique instance id, its code, a timestamp and, when provided, a detail line naming the failed component. | Native UI | UT-UI |
| ERR-10 | Raising an already-active code shall not create a duplicate; it only refreshes the detail line. | Native UI | UT-UI |
| ERR-11 | Active alerts shall persist on the device across restart or reboot. | Native UI | UT-UI |
| ERR-12 | The bell badge shall count only alerts that resolve to a registry definition and reflect the highest active severity (red critical, orange warning). | Native UI | UT-UI |
| ERR-13 | The Alerts screen shall group by severity and provide per error its detail line, description, ordered troubleshooting, documentation QR, video QR when defined, support contacts, and dismiss. | Native UI | UT-UI |
| ERR-14 | If the registry cannot be loaded, the system shall fall back to a built-in registry. | Domain | UT-Dom |
| ERR-15 | Every failure state in the flow diagrams shall be annotated with the registry code it raises ("Err <code>", bidirectional traceability). | Deploy-Ops | Review |
| ERR-16 | Every supervised thermistor, fan and LED panel shall raise its own per-component code. 9001-9005, 9050 and 9051 shall not be raised, and fault-kind rules match the whole family. | Domain | UT-Dom, Build-gate |
| ERR-17 | A cure shall not start from Home while any critical alert is active on Alerts. The operator is shown up to four active criticals with a path to Alerts. | Native UI | UT-UI |
| ERR-18 | The machine shall refuse every process step while a fan is latched below its stop threshold (not overridden), the chamber reading is latched frozen, or a required thermistor (chamber, Left LED, Right LED) does not read. The refusal carries the cause's code. | Application-Process | UT-App |
| ERR-19 | Machine alerts shall self-clear when the condition clears, except latched codes, which follow their release rule. | Application-Process | UT-App |
| ERR-20 | Dismissing 6016 shall acknowledge the door abort on the machine. Dismissing a fan code shall acknowledge the fan alarms, releasing only fans not failing at that moment. | Application-Process | UT-App, UT-UI |
| ERR-21 | A machine alarm the operator dismissed shall not be shown again until the machine clears it or its detail changes. | Native UI | UT-UI |
| ERR-22 | The Alerts screen shall not be opened while the Cure screen is open. | Native UI | UT-UI |
| ERR-23 | The screen shall raise 9089 when it can no longer read the machine state (once per loss). | Native UI | UT-UI |
| ERR-24 | Every alert raised during a run shall be recorded in that run's cure report with its time and detail. | Application-Process | UT-App |
| ERR-25 | The machine shall keep a 48-hour alert log (code, detail, raised and cleared time) and upload it with each sCure Cloud sync. | Application-Platform | UT-App |
| ERR-26 | The screen shall report its critical and warning counts to the machine on every change and at least every 30 s. | Native UI | UT-UI |
| SRS-9-38 | Diagram traceability: every failure node in the §3-§8 diagrams carries "Err <code>". The mapping: Setup 3001 (restore SN failed), 3003 (no internet), 3002 (cloud). Setup Name 4002 (config save), 4003 (SD backup). Connect Org 5001. View All 6012. Start Cure 6014, 6015. Recipe Builder 6001, 6002, 6003. CSV Import 6006, 6007, 6008, 6009, 6010, 6003, 6004. Cure Process 7004, 7005. | Deploy-Ops | Review |
| SRS-9-39 | Numbering history: v1 E-1xx / W-3xx became numeric; v2 → v3 the first digit was re-based from subsystem to SRS section; v3 → v4 (registry 4.0.0, fw 1.0.106) split grouped codes into per-component codes. Within v4, 9008, 9009, 9015, 9016, 9017, 9046, 9047 and 9048 were added (76 → 84). Keys of surviving errors stay constant. | Domain | Review |
| SRS-9-40 | 9052 NFC: raised when NFC is switched on with no reader (the switch stays off), and when a reader detected since boot is disconnected while NFC is enabled. A machine booting without a reader raises nothing. | Application-Platform | UT-App |
| SRS-9-41 | 908x service faults are raised by the screen that ran the operation: network diagnostics 9080 / 9084 / 9085, USB / log export 9081 / 9082 / 9083, software update 9081 / 9086 / 9087. | Native UI | UT-UI |
| SRS-9-42 | Nitrogen known limit: on a unit whose analog input has no 2:1 divider, the reading saturates, so there is no bar value and the over-pressure interlock cannot see the pressure until the divider is fitted. | Hardware | Bench |
| SRS-9-43 | Thresholds are configuration values in `config/components.json` (sections fan_health, frozen_reading, no_heat, led_heating, door_sensor, pressure_sensor, uv_light_check, bofa). The values stated are the shipped ones. Supervision runs at 1 Hz. | Application-Process | Review, UT-App |
| SRS-9-44 | Fan wear (9060-9065) clears when the fan is back within 10 %. A fan override keeps the fan reported but stops it from stopping outputs or blocking starts, and overrides clear when the run ends. The alert detail adds duration to RPM, duty and deficit. | Application-Process | UT-App |
| SRS-9-45 | A spin-test code (9030-9034) clears when the next test of that fan passes, or on operator acknowledge / override. When the LED fan test fails, the fans are switched off and UV stays off. | Application-Process | UT-App |
| SRS-9-46 | 9007 does not block a start. 9006 also refuses every process step, not only heating (§9.14.4). A drop of the output below 50 % restarts the 9006 window. | Application-Process | UT-App |
| SRS-9-47 | Door watchdog (§9.14.6): the live outputs counted include a manual fan duty, and on a trip the status strip is in fault state. | Application-Process | UT-App |
| SRS-9-48 | 9016 is also a boot self-test check. 9009 and 9016 refuse an opening but never close one. | Application-Process | UT-App |

### P §10 Data Architecture & Persistence

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-10-1 | All application data (materials, user programs, print history, cure runs with telemetry, reports, phase timings, settings, alerts, counters) is stored on the unit in its data directory. JSON files written atomically are the default. The shipped configuration configures no database. | Application-Platform | UT-App, Review |
| SRS-10-2 | Data directory: `/var/lib/scurebox` on an image or installer unit, `/opt/data/scurebox/data` as an Origin application package. It is outside the application folder, so updates never replace it (`deploy/scurebox-ui.service`, `deploy/origin-app/run.sh`, `deploy/install.sh`). | Deploy-Ops | Review, Bench |
| SRS-10-3 | PostgreSQL is used only when `DATABASE_URL` is set and the DB answers and accepts the schema at start-up. It then replaces the JSON stores for materials / user programs, print history and cure runs (with telemetry and reports). Phase timings, settings, alerts, counters, calibration, cloud state and safety markers always stay in JSON. | Application-Platform | UT-App (StoreSelector) |
| SRS-10-4 | The backend is chosen once per firmware start and never re-evaluated or retried while running. Data is not copied or migrated between backends (OI-65). | Application-Platform | UT-App |
| SRS-10-5 | There is no "database unavailable" state and no 503 path, because JSON is always available. | Api | IT-API |
| SRS-10-6 | Presets: `config/presets.json`, read-only, part of the release, never written by the unit, replaced by each release. | Deploy-Ops | Review |
| SRS-10-7 | User programs: `user_materials.json`, replaced whole on every save or delete and on cloud `upsert_program` / `delete_program`. Kept until deleted, and nothing is lost after a completed save. | Application-Platform | UT-App |
| SRS-10-8 | Print history: `print_history.json`, written on `POST /api/print-history` or cloud `send_print`. Cure Together prints are removed on completion, and the unit creates no print after a cure. No limit. | Application-Platform | UT-App, IT-API |
| SRS-10-9 | Cure runs: `cure_history.json` (newest first, telemetry embedded), written at run start, on telemetry (see SRS-10-15), at finish and on deletion. Newest 25 kept. A power loss loses at most the last 15 telemetry samples of a running run, and the run itself is kept. | Application-Platform | UT-App |
| SRS-10-10 | Cure reports: `cure_reports.json` by run id, written when generated (completion overlay or Cure History) and also exported to USB. Removed with the run. | Application-Platform | UT-App |
| SRS-10-11 | Phase timings: `phase_timings.json`, always JSON (also with PostgreSQL), appended at the end of every phase, with no limit or pruning (OI-66). | Application-Platform | UT-App |
| SRS-10-12 | UI settings (system name, favorites, organization, setup complete, Developer mode, Nitrogen Mode, SN) live in `ui-settings.json` over the `config/system.json` defaults, written on each change. Unlink / setup reset clears only organization and setup state. | Native UI | UT-UI |
| SRS-10-13 | Alerts: `ui-alerts.json`, written on raise, refresh and dismiss. Dismissed alerts are kept, with no pruning (OI-66). Codes no longer in the registry and an undismissed 9052 are dropped at start-up. | Native UI | UT-UI |
| SRS-10-14 | Component ON-time counters (UV LEDs per wavelength, heater, heater fan, cooling fan): `component_counters.json`, written every 60 s while a counted component is on and at shutdown. Cumulative. A power loss loses at most one minute. | Application-Platform | UT-App |
| SRS-10-15 | UV LED calibration factors: `led_calibration.json` on save. NFC flag: `nfc.json`. Cloud: `cloud.json` (config), `cloud_reports.json` (uploaded list), `cloud_deletes.json` (pending deletions until confirmed). Developer trail: `dev_events.jsonl`, append-only with no pruning (OI-66). | Application-Platform | UT-App |
| SRS-10-16 | Safety / restart state: `frozen_reading.json` (9006 latch, held until the reading moves or goes open), `heater_runon` (remaining run-on, consumed at the next start), `planned_restart` (marker valid 10 min, consumed at the next start). A power loss leaves no planned-restart marker, so the next start runs the full self-test. | Application-Process | UT-App |
| SRS-10-17 | Telemetry sample contents: elapsed time, chamber temperature, all temperature sensors, four LED-zone temperatures, UV on / wavelength / intensity / per-output levels, heater on and PWM, target temperature, per-fan RPM and duty, damper position, nitrogen state, door state. | Application-Process | UT-App |
| SRS-10-18 | Run lifecycle, start: the record (status running, run id, material name, step count, phase list, first target temperature, SN, start time) is created, and runs beyond 25 are removed with their telemetry and reports. | Application-Process | UT-App |
| SRS-10-19 | Run lifecycle, telemetry: one sample every 2 s. The JSON history file is rewritten every 15 samples (about 30 s), not every second. | Application-Platform | UT-App |
| SRS-10-20 | Run lifecycle, finish: on completion, abort or error the record is closed immediately with status, end time, duration, steps completed, sensorIssues, fanIssues and run alerts. | Application-Process | UT-App |
| SRS-10-21 | A run without telemetry gets no report. | Application-Platform | UT-App |
| SRS-10-22 | A run in progress is never deleted. | Application-Platform | UT-App, IT-API |
| SRS-10-23 | `errors.json`, `presets.json`, `versions.json` and `system.json` are in the application config folder and replaced by each release, so the SN and organization live in `ui-settings.json`. `components.json` is at `/etc/scurebox/components.json` (Origin package: next to the data dir), seeded once from the release and never replaced by an update. | Deploy-Ops | Review |
| SRS-10-24 | A missing or unreadable file is treated as empty (empty list or defaults), the unit keeps running, and the file is not repaired. | Application-Platform | UT-App |
| SRS-10-25 | On update or re-install the data directory and `components.json` are kept, and the app and config folder are replaced. Thresholds added in a new version fall back to code defaults on a unit whose `components.json` predates them. | Deploy-Ops | UT-App, Review |
| SRS-10-26 | An eMMC reflash loses all data except the SN, which is restored from the removable card. There is no backup or export of the rest, and only cloud data and USB-exported reports remain (OI-67). | Deploy-Ops | Review |
| SRS-10-27 | Cloud sync is off until configured (portal URL plus machine key). It is outbound only, at the configured interval (minimum 3 s, default 10 s). | Application-Platform | UT-App |
| SRS-10-28 | Each sync sends machine state (temperatures, door, heating / cooling / UV, internet) with counters, user programs, the last 20 print-history entries, the last 10 cure runs without telemetry, 48 h alerts (max 300), and the ids of commands applied since the previous sync. | Application-Platform | UT-App |
| SRS-10-29 | When the portal declares that it keeps reports, one report per sync is uploaded: the newest finished run of the last 10 that the portal lacks (stored report or one built from telemetry). Each report is uploaded once. | Application-Platform | UT-App |
| SRS-10-30 | Commands received (create / replace user program, delete user program, add print entry) are data only and each is applied once (acknowledged next sync). Cloud sync is not a backup, and the unit never restores from the cloud. | Application-Platform | UT-App |
| SRS-10-31 | PostgreSQL: on start-up `deploy/db/schema.sql` and `deploy/db/seed_presets.sql` are applied, both idempotent. Screens read views `v_materials`, `v_print_history` and `v_cure_history`. The same 25-run retention applies, and telemetry and reports are deleted with the run. | Application-Platform | UT-App |
| SRS-10-32 | PostgreSQL ER model: RESINS, MATERIALS (ext_id UK, is_preset), CURE_PROFILES (jsonb parameters), PRINTERS, JOBS, PRINTS (ext_id UK), BUILD_HEADS, TRAY_MEMBRANES, PRINT_HARDWARE, CURE_BOXES (serial_number UK), CURE_SESSIONS, CURE_RUNS (ext_id UK; steps, steps_completed, target_temp, phases / sensor_issues / fan_issues / run_alerts jsonb; started_at, ended_at, status), CURE_RUN_TELEMETRY (t, chamber_temp, uv_on, uv_type, led_right / left / door / back, fan_rpm jsonb, recorded_at), CURE_REPORTS (format, content, summary, generated_at). The authoritative DDL is `deploy/db/schema.sql`, kept in sync with the diagram. | Application-Platform | Review |
| SRS-10-33 | PostgreSQL mapping: presets and user programs are `materials` plus `cure_profiles.parameters`; prints are `prints` (plus jobs, printers, materials); runs are `cure_runs` (plus cure_boxes by SN); telemetry is `cure_run_telemetry`, a subset (OI-68); reports are `cure_reports`. resins, build_heads, tray_membranes, print_hardware and cure_sessions are not populated. ext_id carries the app's record id, so a full-list replace maps idempotently. | Application-Platform | UT-App |
| SRS-10-34 | Data API on port 3001, same on both backends: `GET /api/materials/presets`; `GET`/`POST /api/materials/user` (replace); `GET`/`POST /api/print-history` (replace); `GET /api/cure-history`; `DELETE /api/cure-history/<id>` (one finished run, queued for cloud; 404 when unknown or running); `DELETE /api/cure-history` (all finished; returns deleted ids). | Api | IT-API, QA-live |
| SRS-10-35 | Cure-run API: `POST /api/cure-runs/<id>/start`; `POST .../telemetry` (append; notes the open sensors and slow fans seen at that moment); `POST .../finish` (writes and returns sensorIssues and fanIssues); `POST .../phase` (process and seconds required); `GET /api/phase-timings`; `POST .../report`; `GET .../report` (404 when none). The on-screen flow records by itself, and these serve external clients and the browser UI. | Api | IT-API, QA-live |
| DB-01 | Materials / user programs, print history, cure runs with telemetry, reports, phase timings, settings, alerts and counters shall be persisted on the unit in its data directory per §10.2. | Application-Platform | UT-App |
| DB-02 | JSON backend by default. PostgreSQL for materials, print history and cure runs only when a connection string is configured and the DB opens and accepts the idempotent schema and seed at start-up, else fall back to JSON without failing. Chosen once per start. | Application-Platform | UT-App |
| DB-03 | Screens and API shall present the same data shapes on both backends. | Api | IT-API |
| DB-04 | A full-list replace of user programs or print history shall reconcile the stored list (keep / update present, remove absent). System presets are never removed by it. | Application-Platform | UT-App, IT-API |
| DB-05 | A generated report shall be stored with its run, retrievable by run id, and removed with the run. | Application-Platform | UT-App, IT-API |
| DB-06 | Every data file shall be written atomically (temp plus rename). A missing or unreadable file reads as empty / defaults without stopping the unit. | Application-Platform | UT-App |
| DB-07 | System presets shall ship read-only with the release (seeded into the DB on PostgreSQL) and be served via `GET /api/materials/presets`. | Api | IT-API |
| DB-08 | The cure history shall keep the newest 25 runs. When a new run starts, older runs are removed with telemetry and reports. | Application-Platform | UT-App |
| DB-09 | A run record shall be created at start, receive telemetry every 2 s, and be closed with status, end time, duration, steps completed, sensor issues, fan issues and run alerts. JSON: at most the last 15 samples may be lost on power loss. Start, finish, report and deletion are written immediately. | Application-Platform | UT-App |
| DB-10 | A run found running at firmware start shall be recorded as error (OI-69). | Application-Platform | UT-App |
| DB-11 | Deleting a run (one or all finished) shall remove its telemetry and report and queue the cloud deletion until confirmed. A run in progress is not deletable. | Application-Platform | UT-App, IT-API |
| DB-12 | An update shall keep the data directory and `components.json`. Values the unit must keep (SN, organization, setup state) are stored in the data directory, not the release configuration. | Deploy-Ops | Review, Bench |
| DB-13 | Component ON-time counters shall be written at least every 60 s while a counted component is on, and at shutdown. | Application-Platform | UT-App |
| DB-14 | Cloud sync shall be outbound only, send the §10.6 data, upload each finished run's report once when the portal accepts reports, and apply only data commands (program create / replace / delete, print entry), never a hardware action, each exactly once. | Application-Platform | UT-App |

### P §11 Settings Screen

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-11-1 | Settings is the control and maintenance panel, opened by the gear and inert during a cure. It is a two-column panel: left holds name, power, damper, fans, chamber heating, LED test, counters and the N2 / Nitrogen Mode / NFC / BOFA grid; right holds date and time, SN, logs, update, compliance, organization and versions. | Native UI | UT-UI |
| SRS-11-2 | Each card is independent. Each visit reloads stored settings, then follows the machine state (about 1 Hz) for damper, counters, N2 pressure, NFC, BOFA, heating target and clock. | Native UI | UT-UI |
| SRS-11-3 | System Name (✎): the keyboard opens with the current name, and the result is trimmed and saved. Empty restores "sCure". The name shows in the top bar and reports. | Native UI | UT-UI |
| SRS-11-4 | REBOOT: confirmation "Reboot device?". On confirm the full-screen "Restarting…" screen appears, then an OS reboot is requested. A refused reboot is shown with its reason on that screen. | Native UI | UT-UI |
| SRS-11-5 | SLEEP: a black sleep screen. The first tap shows the logo and "Tap again", the second returns to Home. Hardware is unchanged. | Native UI | UT-UI |
| SRS-11-6 | Damper OPEN / CLOSE: sends the position to the servo, and the selected button follows the reported position. A refusal is only logged (OI-50). | Native UI | UT-UI, QA-live |
| SRS-11-7 | Fan sliders 0-100 % for three groups: LED Cooling Airflow (four LED fans), Chamber Intake Fan (chamber cooling), Chamber Heating Fan (heater). The value is sent 400 ms after the slider stops, and a pending value is sent on leaving. | Native UI | UT-UI |
| SRS-11-8 | The machine refuses the heater fan while the heating loop is active, the intake while the cooling loop is active, and the LED fans while fast cooling uses them. Refusals are not shown. Sliders start at 0 % every visit, and a manual duty is not reset on leaving (OI-50, OI-51). | Application-Process | UT-App, UT-UI |
| SRS-11-9 | Fan Test per group: fans that are off run at 100 % for 2 s spin-up, are measured 1 s, then switched off. Running fans are measured at their current duty. Each is judged against nominal with the supervision thresholds: FAIL when not turning or at / below the stop threshold, WARN from the warning threshold, else OK. | Application-Process | UT-App (RunFanTest) |
| SRS-11-10 | Fan Test row: "<rpm> RPM" (lowest in the group) with OK / WARN / FAIL. For WARN / FAIL a line names each fan, reading against expected. No answer in 20 s gives FAIL "no answer from the machine". At 0 RPM the row shows fixed nominal 2850 / 3050 / 2780 RPM instead of 0 (OI-52). | Native UI | UT-UI |
| SRS-11-11 | Chamber Heating: the slider runs OFF / 30-80 °C. Its lowest position (25 °C) and anything below 30 mean OFF. The value button opens a pad limited to 30-80 in 1 °C steps. The OFF button is shown while heating is set. | Native UI | UT-UI |
| SRS-11-12 | Heating is sent 400 ms after the last change: OFF stops heating, otherwise the target is set (starting heating if inactive). Each visit shows the machine's current target (OFF when not heating), except within 3 s of the operator's own change. | Native UI | UT-UI |
| SRS-11-13 | A heating refusal raises the alert with the returned code and returns the slider to OFF. A 9010-family or 9006 refusal also opens an explanation dialog. | Native UI | UT-UI |
| SRS-11-14 | LED Test 405 / 450 nm: a heating test of the four panels at full intensity, 15 s at 405 or 30 s at 450. A panel passes at ≥ 0.8 °C rise. It is refused while UV, heating or cooling is active. | Application-Process | UT-App, Bench |
| SRS-11-15 | LED Test: when a panel reads ≥ 30 °C, the LED fans first cool at 100 % for 20 s. Every panel sensor must read < 80 °C before switching on. Switching on applies the door interlock and the LED-fan pre-flight. At 450 nm the door panel is reported but not judged. | Application-Process | UT-App |
| SRS-11-16 | LED Test UI: both buttons are disabled while a test runs. Result per wavelength: "<wl> nm PASS", "<wl> nm — <panels> FAIL", or "no answer" after 120 s, and a new result replaces the previous one. A test that cannot run shows plain FAIL with no reason (OI-50). | Native UI | UT-UI |
| SRS-11-17 | Counters (read-only, one decimal hours): LED 405 nm, LED 450 nm, Cooling Fan, Heater, Heater Fan. The machine samples every 2 s which components are on (UV per wavelength, heater energized, fan turning or commanded) and keeps totals across reboots. | Application-Platform | UT-App (ComponentCounters) |
| SRS-11-18 | N2 Pressure: the live line pressure "N.N bar", or "N/A" with no reading. | Native UI | UT-UI |
| SRS-11-19 | Nitrogen Mode switch: saved. It can be switched on only while pressure reads inside the window, `n2Pressure.minBar` (0.5) to `maxBar` (3). Outside it the switch is disabled with a red "(min 0.5 bar)" or "(max 3 bar)". It can always be switched off. Low is not shown while the valve is open. With no reading at all the limits are not checked (OI-53). | Native UI | UT-UI |
| SRS-11-20 | While Nitrogen Mode is on, the top bar shows N2, nitrogen steps run, and their time is counted. While off, nitrogen steps are skipped and an N2-only program cannot start. | Native UI | UT-UI |
| SRS-11-21 | NFC switch: kept across reboots, and the reader is detected by its USB identity. It cannot be switched on without a detected reader: switching on raises 9052 and the switch returns to off. With no reader the switch is disabled with "(no reader)", unless NFC is already on, when it can still be switched off. A reader unplugged while on keeps 9052 active until the reader returns or NFC is switched off. Booting without a reader raises nothing. | Application-Platform | UT-App (NfcReaderDetector), UT-UI |
| SRS-11-22 | BOFA Connected: a saved statement that an extractor is fitted, not a manual on/off. The machine drives it with the intake fan at the configured speed. When the connector reports nothing plugged in it warns with 9048 rather than overriding the switch. A refusal is only logged (OI-50). | Native UI | UT-UI, UT-App |
| SRS-11-23 | Work Without Network: saved. Unset, the unit follows its cloud enrolment (never enrolled means offline on purpose, enrolled expects an uplink). Offline on purpose: the status strip stays green (not blue), the globe stays white (not red), the internet watcher drops to a 60 s heartbeat and stops logging unreachability, and no sync error is shown. An enrolled unit still shows a dead uplink. | Application-Platform | UT-App, UT-UI |
| SRS-11-24 | Auto Sync is network time itself, showing the real `timedatectl` NTP state every visit. On, the OS keeps the clock synced, and date (dd MMM yyyy), time (HH:mm) and time zone are read-only. Off releases the clock, and Day / Month / Year / Hour / Minute fields appear filled with the current time, each with a pad (Day 1-31, Month 1-12, Year 2020-2099, Hour 0-23, Minute 0-59). Setting by hand leaves sync off, and this switch turns it back on. The time zone cannot be changed (OI-54). | Application-Platform | UT-App, UT-UI |
| SRS-11-25 | Apply (manual) checks the date exists, then sets the OS clock (which turns network sync off). It shows "✓ Applied" or "✗ Failed" for 3 s, and an invalid date (e.g. 31 Feb) gives "✗ Failed" and changes nothing. | Native UI | UT-UI |
| SRS-11-26 | S/N is read-only: the scanned SN, else the factory value. | Native UI | UT-UI |
| SRS-11-27 | Export Logs (USB) copies the system log folder to the first USB drive as `scure-logs-<yyyyMMdd-HHmmss>`. Without a log folder the service journal is written as a text file. The button shows "Exporting...", then "✓ Done!" or "✗ No USB drive found" for 3 s. Any failure raises 9083. The failure label reads "No USB drive found" even when the copy failed on a present drive (OI-50). | Application-Platform | UT-App, UT-UI |
| SRS-11-28 | Software Update (USB) opens the Software Update modal. Compliance (CRA / EN 18031) shows the count of active controls and opens the Compliance modal. | Native UI | UT-UI |
| SRS-11-29 | Link Organization / Change: a USB file browser (every removable drive, root plus 2 levels, max 200). The first UUID becomes the Organization ID, and no UUID gives "No valid ID found" with nothing changed. | Native UI | UT-UI |
| SRS-11-30 | Sign in with Origin is always shown. It opens the Origin sign-in, and on success the signed-in account's organization becomes the ID. No password is kept. | Native UI | UT-UI |
| SRS-11-31 | Remote organization link: `GET`/`POST /api/ui/organization` with a UUID (empty unlinks), with no one at the machine. A malformed id is refused and the stored one left untouched. | Api | IT-API, QA-live |
| SRS-11-32 | Unlink (shown when linked) clears the ID, marks Setup not complete, and goes to Setup at once, with no confirmation (OI-55). | Native UI | UT-UI |
| SRS-11-33 | Versions card (read-only): Software Version (installed, else factory), Last Boot (OS boot date dd MMM yyyy), Device (eMMC serial, else factory device name). Tapping the version row opens the Versions modal. Ten taps elsewhere on the card open the Developer PIN pad. The old hidden factory reset no longer exists. In Developer Mode the card also shows Dev Menu and Exit Developer Mode. | Native UI | UT-UI |
| SRS-11-34 | No Lead On Time field and no W/1053 maintenance warning exist (OI-56). | Native UI | Review |
| SRS-11-35 | Software Update modal: an idle page explains the update, then four steps run with progress marks: find USB, find package, verify (the SHA-256 must be present; the signature is checked during installation), install. The modal cannot be closed while running. Success shows the new version and Restart Now, which opens the "Updating" restart screen and reboots. Failure shows the failed step and reason (no package, checksum mismatch, signature refused, version already installed) with Retry. | Native UI | UT-UI, UT-App (UpdateService) |
| SRS-11-36 | On a managed (Origin) device the package is installed through the device supervisor, otherwise a signed `.scu` from USB is installed. Codes: 9081 (no USB), 9087 (no package), 9086 (failed). | Application-Platform | UT-App, Bench |
| SRS-11-37 | Compliance modal: the applicable standards (CRA / EN 18031 / EN 40000), the code-level security controls with ACTIVE / PLANNED status, and the requirements they cover. | Native UI | UT-UI |
| SRS-11-38 | Versions modal: software version, build (git commit and date), OS, kernel, runtime, last boot, then VERSION HISTORY from the version registry, newest first ("No version history available." when empty). | Native UI | UT-UI |
| SRS-11-39 | The on-screen keyboard edits the System Name. The number pad serves the heating target and the manual date and time. The USB file browser picks the organization CSV. | Native UI | UT-UI |
| SRS-11-40 | Developer Mode entry: the tenth press of the top-bar gear (count kept for the session; that press opens the PIN pad instead of Settings), or ten taps on the Versions card. Both are ignored while already in Developer Mode. | Native UI | UT-UI |
| SRS-11-41 | PIN: a four-digit pad. A correct PIN enters Developer Mode and opens Developer Tools. A wrong PIN shows "Incorrect password" and clears. Request, success, failure and exit are written to the developer event log. One fixed PIN, the same on every unit (OI-57). | Native UI | UT-UI |
| SRS-11-42 | Developer Mode lasts the session only (Exit or restart). While on, the DEV badge opens Developer Tools: LED Intensity Calibration and Material HDT Calibration. Opening a developer screen outside Developer Mode returns to Home. These screens are unspecified (OI-58). | Dvt-Hdt | UT-UI |
| SRS-11-43 | Settings error handling: a refused reboot is reported on the Restarting screen. With no USB drive, Export Logs shows "✗ No USB drive found" plus 9083, and the update stops at the USB or package step with the reason. Diagnostics time-outs: fan 20 s, LED 120 s. The organization CSV without a UUID changes nothing. An invalid manual date is rejected. Settings is inert during a cure. | Native UI | UT-UI |
| SRS-11-44 | §11.7 states that Nitrogen Mode cannot be switched on below 1 bar, and the §11.6 diagram says "min 1 bar". This conflicts with SRS-11-19 (0.5 bar); see Conflicts. | Native UI | Review |

---

## Part E - Engineering SRS (`docs/06-srs.md`, rev A)

Rows already covered by Part P are not repeated unless E adds a number, an interface or a different value.

### E §1-§2 Purpose, scope, system context

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E1-1 | The software heats a chamber, exposes the part to 405 nm or 450 nm UV, optionally purges with N2, cools down, records what happened, and refuses or stops anything unsafe or out of specification. | Domain | Review |
| SRS-E1-2 | In scope: multi-step program execution on the hardware; touchscreen UI with program building and history; local HTTP API on port 3001 for QA tooling, the legacy browser UI and remote support; supervision of sensors, fans, door, LED panels plus an out-of-process output watchdog; persistence of programs, runs, phase timings, print history, calibration and counters; imaging, installation, update and remote-access tooling. | Deploy-Ops | Review |
| SRS-E1-3 | Out of scope: mechanical design, IO board schematic, certification test plan, and the DVT campaign tooling in the sibling repository. | Deploy-Ops | Review |
| SRS-E1-4 | `hwSource` reports `io_controller` for a real board and `simulation` otherwise. | Api | IT-API |
| SRS-E2-1 | Firmware and UI are one process, and the API is hosted inside it. The watchdog is a second independent process (`scurebox --watchdog`) that reads the heartbeat and cuts heater and UV on silence, so it survives a firmware crash. Remote support reaches the API over NetBird, and a Windows installer reaches the unit over SSH / USB. | Deploy-Ops | Review, Bench |

### E §3 Operating environment and modes

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E3-1 | Target: Raspberry Pi CM5 with eMMC; Raspberry Pi OS Debian 13 "trixie" 64-bit; self-contained `linux-arm64` publish with no SDK on the unit (E says .NET 8, the repo is now .NET 10); 10.1" DSI Touch Display 2, a portrait panel driven rotated; wired Ethernet plus NetBird when enrolled; install path `/opt/scurebox`. | Deploy-Ops | Review, Bench |
| SRS-E3-2 | Modes. Normal: `scurebox-ui.service`, UI plus firmware plus API in one process. Headless: `scurebox.service`, API plus bundled browser UI, no Avalonia. Watchdog: `scurebox-watchdog.service`, only the output watchdog, owning only the cut path. Simulation: `SCURE_SIMULATE=1` or no IO board, hardware emulated, `hwSource=simulation`. QA: any of these plus `qa/` tooling, adding UI automation endpoints. | Deploy-Ops | IT-API, Review |
| SRS-E3-3 | Users. Operator: touchscreen (pick or build, run, read report). Service technician: Settings, diagnostics, LED / fan tests, calibration, update. QA / engineering: API, QA tool, headless runner, simulation on a PC. Manufacturing: imaging and installer tooling on a Windows PC. | Native UI | Review |

### E §4 Software architecture

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E4-1 | Layers, with dependencies pointing downward only: `SCureBox.Ui` → `SCureBox.Api` and `SCureBox.Application`; `Api` → `Application`; `Application` → `Hardware` and `Domain`; `Hardware` → `Domain`. Domain is pure: no I/O, no timers, no hardware. | Domain | Review, Build |
| SRS-E4-2 | Ownership. Domain: recipe state machine, validators, estimator, sensor and fan rules, error codes. Application: cure controller, recipe runner, supervision, device loops, stores, platform services. Hardware: board drivers, sensor conversion, simulation, safety cut, watchdog. Api: host, DI composition, endpoints, heartbeat, systemd. Ui: shell, pages, dialogs, editor, boot screen, report rendering. | Domain | Review |
| SRS-E4-3 | `SCureBox.Ui/Program.cs` builds the firmware host via `ScureApiHost.Build(...)`, starts it on a background thread, and runs Avalonia on the main thread. Stopping either side stops the other. | Native UI | UT-UI, Bench |
| SRS-E4-4 | View models resolve the same singleton services as the API, so screen and HTTP commands share one code path and one `CureController`. The process-layer composition root is `Application/ProcessServiceCollectionExtensions.cs`. | Application-Process | Review, IT-API |
| SRS-E4-5 | Loops. Recipe tick 1 s (`RecipeRunner`). Supervision tick 1 s (`SupervisionService`). Telemetry sample 2 s (`RecipeRunner`). Heartbeat write 1 s (`HeartbeatService`). Watchdog poll 500 ms (`OutputWatchdog`, separate process). UI state poll 1 s (`MachineStateStore`). systemd notify at half of `WATCHDOG_USEC` (`SystemdWatchdogService`). | Application-Process | UT-App |
| SRS-E4-6 | Key components: `RecipeStateMachine` (pure sequencer), `RecipeRunner` (hosted 1 Hz loop), `CureController` (machine command surface: heat, dry, cure, cool, nitrogen, stop, door, tests), `HeatingLoop` / `CoolingLoop` (PI delta-sigma heating, cooling-mode logic), `SupervisionService` (1 Hz safety plus door watchdog), `IoBoardHardwareSystem` (board, sensor reads, glitch hold, UV routing, interlocks), `OutputWatchdog` plus `SafetyCut` (out-of-process cut), `ProgramValidator` / `EditorRules`, `ProgramEstimator`, `ErrorRegistry`. | Domain | Review |

### E §5 Process flows

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E5-1 | Power-on order: the io-safe service drives the LED supply relays and routing pins low before the firmware starts. The firmware opens the board or falls back to simulation. Then the boot screen (logo plus self-test list), then Setup or Home. | Deploy-Ops | Bench |
| SRS-E5-2 | E lists six boot checks (Door, Temperature sensors, UV 405, UV 450, Chamber fans, API server). P (1.0.141) adds the N2 Pressure Sensor as check 6 of 7. Build the P list. Chamber fans pass at ≥ 100 RPM per fan, damper open, closed after. Temperature sensors are the chamber plus Left / Right / Back / Door LED thermistors; UV photoresistors are not checked. | Native UI | UT-UI |
| SRS-E5-3 | A failed self-test shows how many checks failed and offers Retry or Continue anyway. LED checks are failed when the door check did not pass. The machine is not locked. | Native UI | UT-UI |
| SRS-E5-4 | The server sequences a run: `RecipeRunner` ticks at 1 Hz, asks `RecipeStateMachine`, and calls `CureController`. The UI starts, renders, and sends Pause / Resume / Abort / Skip. The same surface is `/api/recipe/{status,start,pause,resume,abort,skip}`. | Application-Process | UT-App, IT-API |
| SRS-E5-5 | Run lifecycle (E): Idle → Preflight on Start; Preflight → Completed when the program has no steps; Preflight → Running; Running → Running on step change; Running → Completed; Running ↔ Paused; Running / Paused / Preflight → Aborted; Running → Error on a refused command, door abort or supervision stop. Inside Running the phases are Ramping, Holding, Cooling, Nitrogen. Paused reports pseudo-phase `paused` with every progress clock frozen. | Domain | UT-Dom |
| SRS-E5-6 | Start is refused with 6015 when a run is preflight, running or paused, or any process is active. An invalid program is refused with the validator's code. Pause needs running, Resume needs paused, Abort needs preflight / running / paused, Skip needs running. | Domain | UT-Dom, IT-API |
| SRS-E5-7 | Per-type outputs. Heating: UV off, cooling stopped, damper closed, heater PI to target, heater fan 100 %. Drying: as Heating, and once at temperature damper open plus intake 30 %. Cure 405: heater to target, UV mode 405, LED-fan pre-flight, panels at intensity × calibration factor, panel fans 100 %. Bleacher 450: as Cure with mode 450, lit panel fan 30 %, only the door panel allowed. UV without temperature: heater stopped, UV on at once, ventilation if asked. Cooling: UV off, heater shut down, damper open, heater fan 100 %, intake fast 100 / medium 60 / slow 30 %, fast boosts the four LED fans. Nitrogen: valve only, fixed 120 s. | Application-Process | UT-App |
| SRS-E5-8 | Thresholds: ramp complete at target − 0.5 °C; cooling complete at target + 0.5 °C; N2 purge 120 s; ambient 25 °C when no reading exists; heater "at temperature" band 1.5 °C (drying damper trigger); ramp fallback with no reading = estimated ramp seconds elapsed. | Domain | UT-Dom |
| SRS-E5-9 | Pause: all cure outputs stop, the heater fan may run on, clocks freeze, phase `paused`, and the UI pulses the door magnet. Resume: every clock anchor shifts by the pause duration and the phase command is re-issued. Abort: state `aborted`, outputs stop immediately, run closed `aborted`. Skip: end the current step, begin the next, or complete if last. Finish: on the last step all outputs stop, fans and damper close down, the run closes `completed`, and the UI offers the report. | Application-Process | UT-Dom, UT-App |
| SRS-E5-10 | Heater fan run-on: a normal stop switches the element off at once and keeps the heater fan at 30 % for up to 15 min. Only a door abort skips the run-on. | Application-Process | UT-App |
| SRS-E5-11 | Pre-flight flow: on Start, a critical alert or door open refuses. Then the system pre-check runs all chamber fans; under 100 RPM the operator chooses Continue anyway or Cancel. Then the cure screen. Per step: sensor pre-flight (critical fan latched or required sensor unreadable refuses with 9002 / 9001 in E; per-component codes in P). A UV step adds the LED-fan pre-flight (fans 100 %, wait 1.5 s, measure, ≥ 100 RPM, else 9003 in E / 9030-9033 in P). | Application-Process | UT-App, UT-UI |
| SRS-E5-12 | The operator pre-check drives every chamber fan to 100 %, waits 2 s, and measures over 1 s. The sensor pre-flight retries a failed thermistor read three times, 0.5 s apart. The LED-fan pre-flight is skipped if UV is already lit or it passed within the last 30 s. | Application-Process | UT-App |
| SRS-E5-13 | Supervision, three independent levels: (1) the 1 Hz tick (door abort 6016 after 10 s; fan > 20 % below nominal for 60 s stops outputs and blocks starts; chamber sensor open while heating shuts the heater; another critical sensor open 60 s alerts); (2) the watchdog process (heartbeat polled every 500 ms, > 20 s stale cuts heater SSR, four UV dimming channels and both LED supply relays, repeated every 5 s); (3) board level (any UV command with the door open is refused). | Application-Process | UT-App, UT-HW |
| SRS-E5-14 | The door interlock exists at three levels: the hardware layer refuses LEDs with the door open, the heating loop refuses to start with the door open, and supervision aborts after 10 s open. Closing within 10 s cancels. | Application-Process | UT-HW, UT-App |
| SRS-E5-15 | UV-on confirmation: UV_LEFT on U6 AIN2 and UV_RIGHT on U6 AIN0 are read as volts, never temperature. Once lit 5 s at ≥ 10 %, the reading must fall to 0.6 × the dark baseline, else 9046 / 9047. The process continues, and the warning clears when light is seen or the panel goes off (`uv_light_check`). | Hardware | UT-HW, Bench |
| SRS-E5-16 | Sensor glitch hold: −20…120 °C validity, the last good value held up to 15 s, which does not start the 60 s open-sensor timer. Still bad after the hold ends heating or cooling mode with 9001 (E) / 9010 (P). | Hardware | UT-Dom |
| SRS-E5-17 | Fan policy: expected RPM per duty from a per-fan table. > 10 % below for 60 s is a maintenance warning (9051 in E / 9060-9065 in P). > 20 % below, or effectively stopped 5 s, is critical (9002 / 9020-9025): all cure outputs stop, and starts are blocked until recovery or operator override. | Domain | UT-Dom |
| SRS-E5-18 | Temperature stall: under 1 °C in 5 min, five windows in a row, the UI pauses the run and asks, alert 7004, UI only. (P says the run is not paused; see Conflicts.) | Native UI | UT-UI |
| SRS-E5-19 | Records: telemetry every 2 s (chamber and panel temperatures, fan speed and duty, heater PWM, UV outputs, damper, nitrogen, door); phase timing at every step end; run record at end (status, steps completed, sensor and fan issues); HTML report on request, exportable to USB. | Application-Process | UT-App |

### E §6 Building and validating a program

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E6-1 | Editor flow: Add step offers only legal process types, values are clamped on every change, Save normalises (renumber, clamp, per-type fixed fields), then the validator runs. Errors refuse the save with the first error in editor wording. OK stores the program in the user list with an estimated duration. | Native UI | UT-UI |
| SRS-E6-2 | Validation codes (E §6.2): no steps → 6015; target temperature out of range, cooling not ≥ 5 °C below, or a temperature drop without cooling → 7001; hold time out of range → 6015; UV out of 10-100 → 7002; more than 2 purges, or a purge not followed by Cure/Bleaching → 6015; that UV step not followed by Cooling → 7003. | Domain | UT-Dom |
| SRS-E6-3 | A nitrogen step carries no temperature and no time. A cooling step carries no hold time. A UV step without a temperature is legal (UV only). | Domain | UT-Dom |
| SRS-E6-4 | The estimate is shown per step in the editor, as the program total on Home, and as the remaining-time prediction during a run. | Native UI | UT-UI |

### E §7 External interfaces

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E7-1 | The API is mounted under `/api` on port 3001, bound to every interface over IPv4 and IPv6, with no authentication, no TLS and CORS open to any origin. | Api | IT-API |
| SRS-E7-2 | State: `GET /api/state`, the full machine snapshot polled once per second. | Api | IT-API, QA-live |
| SRS-E7-3 | Cure commands: `POST /api/cure/{heat,dry,cure-405,cure-450,uv-only,cool,nitrogen,stop}`. | Api | IT-API, QA-live |
| SRS-E7-4 | Recipe runner: `GET /api/recipe/status`, `POST /api/recipe/{start,pause,resume,abort,skip}`. | Api | IT-API |
| SRS-E7-5 | Hardware: `POST /api/{door/open,door-abort/ack,chamber/temperature,chamber/stop,fans/*,damper/*,uv,bofa,rgb,rgb/alerts}`. Fume extraction: `GET`/`POST /api/bofa/policy`. Watchdog ack: `POST /api/watchdog/ack` (P). | Api | IT-API, QA-live |
| SRS-E7-6 | Diagnostics: `POST /api/diagnostics/{fan-test,led-test}`. | Api | IT-API |
| SRS-E7-7 | Materials: `GET /api/materials/presets`, `GET`/`POST /api/materials/user` (full replace). History: `GET`/`POST /api/print-history`, `GET /api/cure-history`, `GET /api/phase-timings`. Cure runs: `POST /api/cure-runs/{id}/{start,telemetry,finish,report,phase}`, `GET /api/cure-runs/{id}/report`. | Api | IT-API, QA-live |
| SRS-E7-8 | System: `POST /api/system/{reboot,shutdown,datetime,export-logs,export-csv,export-report,update}`, `GET /api/system/{version,update/manifest,update/package}`; also `GET`/`POST /api/system/network-time` (P, 1.0.142). | Api | IT-API |
| SRS-E7-9 | Network: `GET /api/network/status`, `POST /api/network/{diagnostics,static}` (ping, DNS tools, static or DHCP). | Api | IT-API |
| SRS-E7-10 | Developer: `POST /api/dev/log`, `GET`/`POST /api/dev/led-calibration`, `POST /api/dev/led-power`, `GET /api/dev/picolog/status`, `POST /api/dev/hdt/{start,abort,reset}`, `GET /api/dev/hdt/{status,report.csv}`. | Dvt-Hdt | IT-API |
| SRS-E7-11 | NFC: `GET`/`POST /api/nfc` (reader presence and enable flag). Cloud: `POST /api/cloud/config`. | Api | IT-API |
| SRS-E7-12 | UI automation, present only when the native UI hosts the API: `GET /api/ui/route`, `POST /api/ui/navigate`, `GET /api/ui/screenshot`, `POST /api/ui/tap`, `POST /api/ui/swipe`, `POST /api/ui/scan`, `GET`/`POST /api/ui/organization`. | Api | UT-UI, QA-live |
| SRS-E7-13 | Commands return `{ok, message}` plus `code` on a coded refusal. Almost everything answers HTTP 200 even when `ok=false`. Non-200 only for malformed bodies, a missing report, a missing update package and unknown routes. | Api | IT-API |
| SRS-E7-14 | Bare objects or arrays (no envelope): state, materials, histories, phase timings, version, network status and diagnostics, recipe status, developer status endpoints. | Api | IT-API |
| SRS-E7-15 | A refusal message starting with a bracketed code (e.g. `[9002] Fan below minimum speed`) carries that code. Any other refusal is reported as 6015. | Api | IT-API |
| SRS-E7-16 | These always answer `ok:true` regardless of the hardware: fan speed, door open, door-abort ack, chamber stop, cure stop, both diagnostics routes. This is deliberate fidelity to the original Python API and must be preserved. | Api | IT-API |
| SRS-E7-17 | Unhandled exceptions under `/api` become `{ok:false, message}` with HTTP 200 and never leak a stack trace. Every request is logged except the 1 s state poll. | Api | IT-API |
| SRS-E7-18 | PCA9685 at 0x55, I2C bus 0: fans, heater relay, chamber light, extractor, four UV dimming channels. Every write is read back and retried. | Hardware | UT-HW |
| SRS-E7-19 | TCA6424A at 0x23, bus 0: LED supply relay, valves, door magnet, motor direction, NFC reset. Outputs are staged before pins become outputs, so the relay cannot flash on at power-up. | Hardware | UT-HW |
| SRS-E7-20 | Two ADS1115 at 0x49 on buses 0 and 1: seven thermistor channels plus the N2 pressure input. | Hardware | UT-HW |
| SRS-E7-21 | Six tach inputs via libgpiod v2. Each line is requested once with pull-up and rising-edge detection, and a background thread counts edges. | Hardware | UT-HW, Bench |
| SRS-E7-22 | Door sensor on GPIO 27, high means closed. Unreadable is reported as unknown, never closed. | Hardware | UT-HW |
| SRS-E7-23 | N2 valve on GPIO 13, on / off. UV supply: two SSRs on GPIO plus a routing pin, verified on every wavelength change. | Hardware | UT-HW |
| SRS-E7-24 | Damper servo on GPIO 8 through a PIO helper, falling back to software PWM (with jitter) when the helper or PIO device is missing. | Hardware | UT-HW, Bench |
| SRS-E7-25 | Status strip: 21 addressable LEDs on GPIO 12 via a PIO helper. Never safety relevant: failures are recorded, not thrown. | Hardware | UT-HW |
| SRS-E7-26 | PicoLog TC-08 over USB for calibration: Developer mode only, simulated when requested (`SCURE_SIM_TC08`). | Dvt-Hdt | UT-App |
| SRS-E7-27 | NFC reader Eccel Pepper C2 as a USB serial device, detected by device path. Enabling without a reader is refused with 9052 (`SCURE_SIM_NFC` simulates). | Application-Platform | UT-App |
| SRS-E7-28 | The hardware layer refuses illegal operations by throwing a refusal. A write / read-back mismatch is a verification failure. Both become coded refusals at the controller boundary. | Hardware | UT-HW |
| SRS-E7-29 | The real board is used only on Linux with the I2C device present, the PWM chip answering, and simulation not forced. Otherwise a deterministic model substitutes silently with `hwSource: simulation`. Nothing prevents a cure in simulation. | Hardware | UT-HW, IT-API |
| SRS-E7-30 | Persistence files: `user_materials.json`, `cure_history.json`, `cure_reports.json`, `phase_timings.json`, `print_history.json`, `component_counters.json`, `led_calibration.json`, `nfc.json`, `cloud.json`, `dev_events.jsonl`, `ui-settings.json`, `ui-alerts.json`. Each is written whole through temp plus rename. | Application-Platform | UT-App |
| SRS-E7-31 | Config: `components.json` (hardware map and every tunable limit, at `/etc/scurebox/components.json`, kept across updates); `presets.json`, `errors.json`, `system.json` (serial, model, hardware revision, organisation defaults), `versions.json` (release history) in `/opt/scurebox/config`; `VERSION` next to the executable, reported by the API and UI. | Deploy-Ops | Review |
| SRS-E7-32 | Environment variables: `PORT`, `ASPNETCORE_URLS`, `SCURE_SIMULATE`, `SCURE_COMPONENTS`, `SCURE_DATA_DIR`, `SCURE_UI_DIR`, `DATABASE_URL`, `SCURE_HEARTBEAT_FILE`, `SCURE_SIM_TC08`, `SCURE_SIM_NFC`, `SCURE_UI_WINDOW`, `SCURE_UI_SIZE`, `SCURE_UI_HIDE_CURSOR`, `SCURE_UI_DRM_CARD`, `SCURE_UI_SHOTS`; plus `SCURE_SD_DIR` (SRS-UI-14). | Deploy-Ops | IT-API, Review |

### E §8 Runtime environment and lifecycle

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E8-1 | `scurebox-io-safe`: a one-shot at boot, before the firmware, that drives the UV supply pins low and releases the LED relay (closing the expander pull-up window). | Deploy-Ops | Bench |
| SRS-E8-2 | `scurebox-ui`: firmware plus API plus touchscreen in one process, owning the console. Restart always, with a 60 s systemd watchdog. | Deploy-Ops | Bench, Review |
| SRS-E8-3 | `scurebox`: the browser-UI build without Avalonia. Restart always, and it conflicts with `scurebox-ui`. | Kiosk-Web | Review |
| SRS-E8-4 | `scurebox-watchdog`: always restarted, at raised priority, deliberately not tied to the firmware units. | Deploy-Ops | Review, Bench |
| SRS-E8-5 | `scurebox-netbird-enroll`: enrols when a setup key is present, retrying every minute until success. | Deploy-Ops | Bench |
| SRS-E8-6 | `deploy/install.sh` (root, from an extracted release), in order: stop the legacy service; copy the app and link the data dir; enable I2C and append boot config plus display profile; patch both A/B boot partitions with the display profile; build the PIO helpers if possible; install and start the systemd units for the chosen UI; install the branded boot splash; give the display to the native UI by masking the console login; enrol NetBird when a key is present; install the output watchdog; install the wired-network config. | Deploy-Ops | Bench |
| SRS-E8-7 | Two install steps are non-fatal: the PIO helper build (the damper falls back to software PWM) and the network config, which is not re-applied immediately so an install over SSH cannot cut its own connection. | Deploy-Ops | Bench |
| SRS-E8-8 | Imaging: from the official RPi OS image, `build-image.py` edits the boot partition only (boot config, display profile, first-run script, release payload, user and SSH). `flash-cm5.ps1` on Windows with the CM5 in USB boot mode exposes the eMMC as a disk and raw-writes it, partition table last, first megabytes verified. Power-cycle without the jumper. First boot runs the installer from the payload, then reboots into the UI. | Deploy-Ops | Bench |
| SRS-E8-9 | The Windows installer bundle copies the release over the network, runs the on-device installer, and polls until the unit reports the new version and answers. Remote access can be connected in the same session, with the operator entering the unit address and seeing progress and result. | Deploy-Ops | Bench |
| SRS-E8-10 | USB update: Settings finds a signed `.scu` on a USB drive, verifies SHA-256 and the signature against the bundled public key, extracts, runs the installer's pre and post phases, and rolls back on failure. | Application-Platform | UT-App |
| SRS-E8-11 | Developer push: a script copies a freshly built release to a unit over SSH. | Deploy-Ops | Review |
| SRS-E8-12 | NetBird enrolment uses a setup key (at imaging or from the installer) or an operator login on the NetBird website from the installer, which stores no key or token on the PC. A key on the boot partition is moved to root-only storage on first boot and deleted. After successful enrolment every copy of the key is removed. | Deploy-Ops | Bench |
| SRS-E8-13 | The wired interface is configured so DHCP never times out (otherwise a unit wired directly to a PC dropped its address every 45 s). Static addressing stays available from the Network screen. | Deploy-Ops | Bench |

### E §9 Functional requirements (ids as in E)

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-RUN-1 | The server executes a program without help from the UI, advancing once per second. | Application-Process | UT-App |
| SRS-RUN-2 | A run passes through idle, pre-flight, running, paused and one of completed, aborted or error. | Domain | UT-Dom |
| SRS-RUN-3 | A start is refused while another run or another process is active. | Application-Process | UT-App, IT-API |
| SRS-RUN-4 | A start is refused when the program fails validation, reporting the validator's code. | Application-Process | UT-App |
| SRS-RUN-5 | An empty program completes immediately with an explanatory message (P: refused with 7001; see Conflicts). | Domain | UT-Dom |
| SRS-RUN-6 | Pause stops all outputs and freezes every clock. Resume shifts all clocks by the pause length and re-issues the step's command. | Domain | UT-Dom |
| SRS-RUN-7 | Abort stops outputs immediately and closes the run as aborted. | Application-Process | UT-App |
| SRS-RUN-8 | Skip ends the current step now and continues with the next, or completes the run. | Domain | UT-Dom |
| SRS-RUN-9 | Any refused command during a run fails the run, stops all outputs and reports the refusal's code. | Application-Process | UT-App |
| SRS-RUN-10 | The same run control is available on the screen and over HTTP, sharing one controller instance. | Api | IT-API |
| SRS-RUN-11 | Leaving the cure screen while a run is live aborts that run. | Native UI | UT-UI |
| SRS-STEP-1 | Six process types exist: Heating, Drying, Cure, Cooling, Bleacher, Nitrogen. | Domain | UT-Dom |
| SRS-STEP-2 | A ramp completes at target − 0.5 °C, or when the estimated ramp time has passed with no temperature reading. | Domain | UT-Dom |
| SRS-STEP-3 | A hold ends when the step's time has elapsed (from ramp completion or start per timer mode) and never before the target is reached. | Domain | UT-Dom |
| SRS-STEP-4 | Cooling ends when the chamber is at or below target + 0.5 °C. | Domain | UT-Dom |
| SRS-STEP-5 | Cooling drives the intake fan at 100 / 60 / 30 % for fast / medium / slow, opens the damper, and in fast mode also boosts the four panel fans. | Application-Process | UT-App |
| SRS-STEP-6 | A nitrogen purge opens the valve for a fixed 120 s and changes no other output. | Domain | UT-Dom |
| SRS-STEP-7 | Cure uses 405 nm, bleaching 450 nm, and only panels permitted for that wavelength are lit. | Application-Process | UT-App |
| SRS-STEP-8 | UV is lit at step start or at ramp completion per UV start mode, defaulting to at target. | Domain | UT-Dom |
| SRS-STEP-9 | A UV step without a temperature runs with the heater off and no ramp, optionally with ventilation. | Application-Process | UT-App |
| SRS-STEP-10 | Drying opens the damper and runs the intake fan at 30 % once the chamber is at temperature. | Application-Process | UT-App |
| SRS-STEP-11 | Commanded UV intensity is multiplied by the zone's calibration factor and clamped to the configured maximum duty. | Application-Process | UT-App, UT-HW |
| SRS-STEP-12 | At run end every fan stops, except fans of panels still lit, and the damper closes. | Application-Process | UT-App |
| SRS-STEP-13 | After a normal stop the heater element switches off at once and its fan runs on at 30 % for the configured cooldown. | Application-Process | UT-App |
| SRS-STEP-14 | With a BOFA declared connected, the extractor runs at `bofaDutyPercent` (10 % of its 0-10 V range) whenever the air-intake fan runs and stops with it. With none declared the output is never driven. | Application-Process | UT-App |
| SRS-STEP-15 | The extraction fan's 24 V supply opens and closes with the extraction, leading the speed reference up and following it down. At rest the connector is dead. | Hardware | UT-HW, Bench |
| SRS-STEP-16 | The connector reports a plug-in. A Settings switch claiming a unit while the connector reads empty raises warning 9048 without stopping anything, and an unreadable line never raises it. | Application-Process | UT-App |
| SRS-SAFE-1 | No UV panel can be lit while the door reads open; the hardware layer refuses. | Hardware | UT-HW |
| SRS-SAFE-2 | Heating cannot start while the door reads open. | Application-Process | UT-App |
| SRS-SAFE-3 | Door open 10 s with outputs live aborts: heater and heater fan off at once; UV, N2, cooling, fans and extractor off; run failed 6016. | Application-Process | UT-App |
| SRS-SAFE-4 | An unreadable door sensor is never treated as closed. | Hardware | UT-HW |
| SRS-SAFE-5 | The firmware writes a heartbeat file once a second. | Api | UT-App |
| SRS-SAFE-6 | A separate process cuts the heater relay, the four UV dimming channels and both UV supply relays when the heartbeat is older than 20 s, repeating every 5 s. | Hardware | UT-HW, Bench |
| SRS-SAFE-7 | The safety cut leaves fans, damper and valves running. | Hardware | UT-HW |
| SRS-SAFE-8 | A clean shutdown deletes the heartbeat file, disarming the watchdog. | Hardware | UT-Dom, UT-HW |
| SRS-SAFE-9 | Every process start verifies the required thermistors read, retrying three times, else refuses with 9001 (P: per-sensor 9010-9012). | Application-Process | UT-App |
| SRS-SAFE-10 | Every process start is refused while a critical fan fault is latched, with 9002 (P: per-fan 9020-9025). | Application-Process | UT-App |
| SRS-SAFE-11 | Before UV is lit, the fans of the panels about to be lit must reach 100 RPM, else refused with 9003 (P: 9030-9033). | Application-Process | UT-App |
| SRS-SAFE-12 | Heating refuses to start, and stops within the 10 s health check, when its fan is below 100 RPM or the chamber thermistor is invalid. | Application-Process | UT-App |
| SRS-SAFE-13 | A fan > 20 % below nominal for 60 s, or stopped 5 s, stops every cure output and blocks further starts until it recovers or is overridden. | Application-Process | UT-Dom, UT-App |
| SRS-SAFE-14 | A fan 10-20 % below nominal for 60 s raises a maintenance warning without stopping. | Domain | UT-Dom |
| SRS-SAFE-15 | An open chamber thermistor while heating is wanted shuts the heater down at once. | Domain | UT-Dom |
| SRS-SAFE-16 | A reading outside −20…120 °C is held at its last good value up to 15 s before being a fault. | Hardware | UT-Dom, UT-HW |
| SRS-SAFE-17 | Fan speed is derived over a window of at least one second shared by all callers, so a healthy fan cannot read stopped (`TachRateTracker`). | Domain | UT-Dom |
| SRS-SAFE-18 | The operator may override a failed fan check to continue, and the override is recorded in the run. | Application-Process | UT-App, UT-UI |
| SRS-SAFE-19 | Before the firmware starts, a boot service parks the UV supply pins low and releases the LED relay. | Deploy-Ops | Bench |
| SRS-SAFE-20 | On shutdown the firmware switches every output off and flushes its stores. | Api | UT-App, Bench |
| SRS-VAL-1 | Heating, drying and UV targets are 30…80 °C (P: Drying 30-50). | Domain | UT-Dom |
| SRS-VAL-2 | Cooling targets are 30…75 °C in the editor and at least 5 °C below the running temperature. | Domain | UT-Dom |
| SRS-VAL-3 | Temperature may not decrease step to step without a cooling step between. | Domain | UT-Dom |
| SRS-VAL-4 | Hold time is 1…120 min, or 1…720 for bleaching. | Domain | UT-Dom |
| SRS-VAL-5 | UV intensity is 10…100 %. | Domain | UT-Dom |
| SRS-VAL-6 | At most two purges. A purge must be followed by a UV step, and that step by cooling. | Domain | UT-Dom |
| SRS-VAL-7 | The editor offers only legal process types per position and clamps every value as entered. | Native UI | UT-UI |
| SRS-VAL-8 | Saving normalises: steps renumbered, per-type fields fixed, values clamped. | Native UI | UT-UI |
| SRS-VAL-9 | Programs can be imported from CSV on USB, each validated before being added. | Native UI | UT-UI, UT-Dom |
| SRS-VAL-10 | The estimate uses 13 / 50 / 80 s per °C by band for heating, 2.5 / 1.5 / 0.8 °C/min for cooling, and 120 s per purge. | Domain | UT-Dom |
| SRS-VAL-11 | The API accepts a wider cooling range, 20…80 °C, than the editor. | Api | IT-API |
| SRS-UI-1 | Full screen on the panel with no window manager; every modal is drawn inside the app. | Native UI | UT-UI, Bench |
| SRS-UI-2 | Layout on a fixed 1600×1000 surface, scaled, and rotated with touch input on a portrait panel (`ShellScaler`). | Native UI | UT-UI |
| SRS-UI-3 | At power-on the boot screen runs the self-tests, then Setup or Home. | Native UI | UT-UI |
| SRS-UI-4 | First-run setup requires a serial number, normally scanned; manual entry is deliberately hard to reach. | Native UI | UT-UI |
| SRS-UI-5 | No cure start while a critical alert is active or the door is open. | Native UI | UT-UI |
| SRS-UI-6 | Starting a cure first runs the fan pre-check and offers to continue on a fan failure. | Native UI | UT-UI |
| SRS-UI-7 | During a run the screen shows current step, phase, temperatures, remaining time and progress, refreshed at 1 Hz. | Native UI | UT-UI |
| SRS-UI-8 | Door open, fan failure, heater sensor fault, panel not heating and temperature stall each raise their own dialog during a run. | Native UI | UT-UI |
| SRS-UI-9 | At run end the operator is offered the report and the door release. | Native UI | UT-UI |
| SRS-UI-10 | Alerts are listed by severity with description, troubleshooting and support link, and can be dismissed. | Native UI | UT-UI |
| SRS-UI-11 | The screen sleeps after 2 min of inactivity, except during a run, in developer mode and on full-screen routes (`IdleService`). | Native UI | UT-UI |
| SRS-UI-12 | Developer mode is entered by ten presses and a PIN, and every transition is written to the developer log. | Native UI | UT-UI |
| SRS-UI-13 | Barcodes are read directly from the input devices, because the panel has no focused text field. | Native UI | UT-UI, Bench |
| SRS-UI-14 | Every SN set is also written to the card (`/mnt/ssd2/scure/config_backup.json`, `SCURE_SD_DIR`). A unit starting with no serial takes the card's. | Application-Platform | UT-App |
| SRS-UI-15 | An existing but unrestorable backup raises 3001, and an unwritable card raises 4003. Neither blocks, and with no card there is simply no second copy. | Native UI | UT-UI |
| SRS-UI-16 | Auto Sync is network time itself (real state shown; on keeps the clock synchronised; off releases it). It must outlive a restart: on an Origin device it is written through the supervisor, which owns `/opt/config/clock.conf` and is re-applied at boot. A runtime-only `timedatectl set-ntp` is undone at restart, and an RTC-less unit then boots months behind with HTTPS failing. | Application-Platform | UT-App, Bench |
| SRS-UI-17 | The organization can be read and set over the API (remote commissioning / re-image) without USB CSV or root. It must be a UUID, and a malformed one never replaces the stored id. | Api | IT-API |
| SRS-UI-18 | A cloud job may carry an NFC tag. Presenting the tag from any screen brings up Home and asks whether to start the job, naming job, program, printer and tag. The cure starts only on Start, through all normal gates (door, critical alerts, nitrogen, pre-flight). The newest job with the tag is asked about. An unknown tag says so and shows its number. A tag does nothing during a cure, while a question is open, or on Boot / Setup / Restart, and a tag left on the antenna asks once. | Application-Platform | UT-App (NfcTagReader, PepperC2Protocol), UT-UI (NfcJobService) |
| SRS-DATA-1 | A telemetry sample is recorded every 2 s of a run. | Application-Process | UT-App |
| SRS-DATA-2 | Every completed step writes a timing record including ramp seconds and start / end temperature. | Domain | UT-Dom |
| SRS-DATA-3 | Every run is stored with status, steps completed and the sensor and fan issues seen. | Application-Platform | UT-App |
| SRS-DATA-4 | A run report is a self-contained HTML document with step table, timing diagram, temperature and UV charts and issue notes. | Application-Platform | UT-App |
| SRS-DATA-5 | Reports and CSV exports go to a USB drive, with 9081 when none is present and 9082 on a write failure. | Application-Platform | UT-App |
| SRS-DATA-6 | Every data file is written atomically and survives a corrupt or missing file by falling back to an empty list. | Application-Platform | UT-App |
| SRS-DATA-7 | A run interrupted by a power cut is marked error when history is next loaded. | Application-Platform | UT-App |
| SRS-DATA-8 | Component on-hours are accumulated for UV panels, heater, heater fan and cooling fan. | Application-Platform | UT-App |
| SRS-DATA-9 | The unit reports software version, commit, OS, kernel, runtime and eMMC serial. | Application-Platform | IT-API |
| SRS-DATA-10 | Network status, ping, traceroute and name lookup are available, and addresses never reach a shell. | Application-Platform | UT-App |
| SRS-DATA-11 | A USB update package is installed only after its SHA-256 and signature verify against the bundled public key. | Application-Platform | UT-App |

### E §10 Non-functional requirements (ids as in E)

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-NFR-1 | The recipe and supervision loops each run at 1 Hz, and a slow hardware read must not stall the UI thread. | Application-Process | UT-App, Bench |
| SRS-NFR-2 | The heartbeat is written every second and the watchdog polls every 500 ms, so the worst-case delay from firmware death to output cut is about 20.5 s. | Hardware | Bench |
| SRS-NFR-3 | Every PWM and expander write is verified by read-back, with up to three retries. | Hardware | UT-HW |
| SRS-NFR-4 | The firmware starts without an IO board and behaves identically in simulation, so QA can run on a PC. | Hardware | IT-API |
| SRS-NFR-5 | The domain layer has no I/O and is fully unit-testable. | Domain | Review, UT-Dom |
| SRS-NFR-6 | The UI animates only opacity, because the panel's render stack does not animate transitions reliably. | Native UI | Review, Bench |
| SRS-NFR-7 | Data survives power loss: atomic writes, a tmpfs heartbeat, recovery of interrupted runs. | Application-Platform | UT-App |
| SRS-NFR-8 | The software runs self-contained with no runtime installed on the unit. | Deploy-Ops | Bench |
| SRS-NFR-9 | Every operator-facing error carries a code, a plain description and troubleshooting steps. | Domain | Build-gate |
| SRS-NFR-10 | The local API has no authentication and no TLS, and deployment must keep it on a trusted network. | Deploy-Ops | Review |
| SRS-NFR-11 | Default OS credentials and the developer PIN are compile-time or image constants and must be changed for production units. | Deploy-Ops | Review |

### E §12 Verification

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-E12-1 | Domain unit tests (rules, state machine, validation, estimation, sensor and fan policies on a fake clock): `dotnet test tests/SCureBox.Domain.Tests`. | Domain | UT-Dom |
| SRS-E12-2 | Hardware unit tests (drivers against fake buses, register sequences, safety cut, simulation model): `dotnet test tests/SCureBox.Hardware.Tests`. | Hardware | UT-HW |
| SRS-E12-3 | Application unit tests (controller, heating and cooling loops, runner, stores, platform services, reports): `dotnet test tests/SCureBox.Application.Tests`. | Application-Process | UT-App |
| SRS-E12-4 | API integration tests (every route in simulation, in process): `dotnet test tests/SCureBox.Api.Tests`. | Api | IT-API |
| SRS-E12-5 | UI tests (headless Avalonia: boot self-test order, dialogs, editor, cure screen, scaling and scrolling): `dotnet test tests/SCureBox.Ui.Tests`. | Native UI | UT-UI |
| SRS-E12-6 | Live QA `node qa/run-qa.mjs --api http://<unit>:3001`; chained QA `qa/run-all.ps1`. | Deploy-Ops | QA-live |
| SRS-E12-7 | About 640 cases across five test projects must pass before a release is published. The QA table adds about 100 live checks. | Deploy-Ops | QA-live |
| SRS-E12-8 | Traceability. Execution and steps: recipe state machine, runner and cure-controller tests. Safety: supervision, heating loop, watchdog monitor, glitch hold, fan health and safety cut tests. Validation: validator and estimator tests. Interface: API tests plus the QA table. Operator interface: UI tests. | Deploy-Ops | Review |
| SRS-E14-1 | Every release bumps `VERSION` and adds an entry to `config/versions.json`. A behaviour change updates the matching SRS section in the same commit. Flow charts are edited as Mermaid / draw.io source, not as exported images. | Deploy-Ops | Review |

---

## Part Q - UI reuse and QA conventions (`docs/03-ui-and-qa.md`)

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-Q-1 | Step A reuses the React UI from `sCure-A` unchanged. `npm run build` produces `dist/` (index.html, assets/, config/, materials/, videos/, compliance/), which uses absolute asset paths and must be served from the domain root. | Kiosk-Web | QA-live |
| SRS-Q-2 | The UI calls `http://localhost:3001/api` (`VITE_HW_API_URL` at build time), and three contexts (materials, print-history, cure-history) hardcode `http://localhost:3001`. The C# server must therefore listen on 3001, serve `dist/` at `/`, and keep CORS open. | Kiosk-Web | IT-API |
| SRS-Q-3 | There is no EventSource or WebSocket, only polling: `/api/state` every 1 s, telemetry every 5 s, alert summary every 30 s, `/api/network/status` every 3 s on the network page, HDT status every 1 s. | Kiosk-Web | QA-live |
| SRS-Q-4 | All commands are POST with query-string parameters and no body, except the JSON-body endpoints listed in `01-api-contract.md`. | Api | IT-API |
| SRS-Q-5 | The response envelope is `{ok: boolean, message: string, code?: number}`. | Api | IT-API |
| SRS-Q-6 | The React UI is a fixed 800×480 canvas scaled to the window (`root.style.scale`). On the 1280×800 10.1" Touch Display 2 it stretches 1.6× / 1.667×. | Kiosk-Web | Bench |
| SRS-Q-7 | Static assets are fetched from the same origin: `/config/system.json`, `/config/errors.json`, `/config/versions.json`. | Kiosk-Web | IT-API |
| SRS-Q-8 | With the API down, the UI shows alert 9089 and falls back to demo data for lists. This is not a server-side concern. | Kiosk-Web | Review |
| SRS-Q-9 | In the React UI, `CureProcessPage.tsx` sequences the program. It calls one endpoint per phase and waits on `/api/state`: the ramp ends at chamberTemp ≥ target − 0.5, and cooling is done at chamberTemp ≤ target + band. It then posts phase timing, then `/api/cure/stop` and `finish`. Pause = `stop?immediate=1` plus `door/open`, resume re-sends the phase command, pre-flight = `diagnostics/fan-test?fan=all` (plus `fans/override` on "continue anyway"). | Kiosk-Web | QA-live |
| SRS-Q-10 | The C# backend also offers a server-side recipe runner (`/api/recipe/*`) that runs a whole Material without the UI driving each phase. The scope requires it: recipe engine, state machine, process sequencing, abort handling. | Application-Process | IT-API |
| SRS-Q-11 | Validation: Heating, Drying, Cure and Bleacher 30-80 °C (P narrows Drying to 30-50 °C); Cooling 30-75 °C. Hold time: Bleacher 1-720 min, others 1-120 min, Cooling and Nitrogen 0. UV 10-100 %. | Domain | UT-Dom |
| SRS-Q-12 | The Cooling target must be ≥ 5 °C below the previous step's temperature. | Domain | UT-Dom |
| SRS-Q-13 | At most 2 Nitrogen steps. After Nitrogen only Cure or Bleacher, and after that only Cooling. Each N2 purge must be vented by a later Cooling step and followed by at least one Cure or Bleacher. | Domain | UT-Dom |
| SRS-Q-14 | Temperature is monotonically non-decreasing unless a Cooling step resets the chain. | Domain | UT-Dom |
| SRS-Q-15 | CSV has 10 columns, `Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,UVRampPercent,CoolingMode,Ventilation`. `Temperature=off` on Cure / Bleacher means UV-only, and the field is blank for Nitrogen. Time is blank for Cooling and Nitrogen. Ventilation is on / off, only on no-heat rows. The parser needs ≥ 4 columns per row and a header containing "process" or "step". | Domain | UT-Dom |
| SRS-Q-16 | Estimate: AMBIENT 25 °C. Heat bands in s/°C are ≤ 45 → 13, ≤ 75 → 50, else 80. Cooling in °C/min is fast 2.5, medium 1.5, slow 0.8. Nitrogen defaults to 120 s. `estimateProgram(steps)` = hold + ramp + cool + nitrogen; with timerMode on-ramp only max(0, ramp − hold) is added. Minutes = ceil(total/60). | Domain | UT-Dom |
| SRS-Q-17 | Simulation thermal model (no hardware): SIM_AMBIENT 24.0 °C; heats 0.5 °C/s toward target; cools at fast 5 / medium 2.5 / slow 1.0 °C/min; idle drift 0.05 °C/s back to ambient; dt clamped to 10 s; fan RPM 2850 when duty > 0; the door reads open 5 s after open_door, then re-closes. | Hardware | UT-HW |
| SRS-Q-18 | Domain unit tests (xunit) with a fake `TimeProvider` cover: validation, estimate, NTC math, pressure conversion, heater PI / delta-sigma, calibration filter, fan health, sensor supervision, LED supervision, strip mode ladder, recipe state machine. | Domain | UT-Dom |
| SRS-Q-19 | Integration tests (xunit plus `WebApplicationFactory`) cover: every route in simulation; JSON field presence for every `/api/state` key; error codes 7001 / 7002 / 7003 / 6015 / 9052; data round trips with run id `qa-test-run`; static UI serving; SPA fallback. | Api | IT-API |
| SRS-Q-20 | The browser QA tool `qa/qa-tool.html` uses the existing record shape `{id,name,desc,endpoint,method,body,expect|expectArray|check}`. It has an `apiUrl` input (default `http://localhost:3001`), a sequential runner, pass / fail / warn / skip tiles, and a text report export. | Deploy-Ops | QA-live |
| SRS-Q-21 | The headless runner `qa/run-qa.mjs` (node ≥ 18, no deps) runs the same table against a live server and exits non-zero on failure. `qa/run-all.ps1` builds, runs unit and integration tests, starts the API in simulation, runs the headless QA, and prints a summary. | Deploy-Ops | QA-live |

## Part R - SRS deliverable (`docs/srs/README.md`)

| Req id | Requirement | Area | Verified by |
|---|---|---|---|
| SRS-R-1 | `SRS-CUREBOXCTRL-RevA.docx` is the Stratasys-template SRS for CUREBOX-CTRL. It has a cover and approval block, revision control, sections 1-8 (purpose and scope, document set, functional requirements, states and modes, safety requirements, performance and priorities, verification, open items), and Annex A (mode transitions, per-step flow). | Deploy-Ops | Review |
| SRS-R-2 | The docx states the software as built (1.0.32). `[TBR]` values are filled wherever the code defines them, and every remaining `[TBR]` carries an open item in its section 8. | Deploy-Ops | Review |
| SRS-R-3 | `docs/sCure_SRS.html` must stay byte-identical to `sCure-A/docs/sCure_SRS.html`. Edit either one and copy the change to the other. | Deploy-Ops | Review (diff) |
| SRS-R-4 | The docx is generated, never hand-edited. Run `npm install docx` and then `node build-srs-docx.js SRS-CUREBOXCTRL-RevA.docx`. The requirement tables are plain arrays near the top of each section in `build-srs-docx.js`. If Word ever becomes the master, the README must note it. | Deploy-Ops | Review |

---

## Error code list

The list comes from P §9.11 (registry `config/errors.json` 4.0.0, 84 records) plus E §11. The "System action" column is taken from P §7.4, §9.5.1 and §9.14. **Status in 1.0.141** means: *raised*; *family* (grouped title, not raised); *not raised* (OI-59); *LED checks only* (raised only when `led_heating.enabled`, which is off when shipped). Fields: code, key, message, severity, category / layer.

| Code | Key | Message | Sev. | Cat. / layer | Raised when | System action | Status |
|---|---|---|---|---|---|---|---|
| 3001 | SERIAL_RESTORE_FAILED | Serial Number Restore Failed | critical | provisioning / daemon | A card backup exists but cannot be restored | Unit starts without an SN and goes to the SN step; nothing is blocked | raised |
| 3002 | CLOUD_COMM_FAILED | Cloud Communication Failed | critical | provisioning / backend | (cloud SN assignment, not built) | none | not raised |
| 3003 | SETUP_NO_INTERNET | No Internet Connection | warning | network / backend | (Setup internet check, not built) | none | not raised |
| 4001 | INVALID_DEVICE_NAME | Invalid Device Name | warning | validation / ui | Empty name (handled inline) | Next disabled | not raised |
| 4002 | DATA_FILE_WRITE_FAILED | Data File Write Failed | critical | storage / backend | (settings save failure; only logged) | none | not raised |
| 4003 | SD_BACKUP_WRITE_FAILED | SD Backup Write Failed | warning | storage / backend | SN could not be written to the card (no card, or write failed) | Warns only; Setup and machine continue | raised |
| 5001 | ORG_ID_NOT_FOUND | No Organization ID in File | warning | validation / ui | CSV has no UUID (handled inline) | Inline message; Link disabled | not raised |
| 6001 | PROGRAM_NAME_REQUIRED | Program Name Required | warning | validation / ui | Editor Save without a name | Inline "Enter a material name" | not raised |
| 6002 | NO_STEPS_DEFINED | No Steps Defined | warning | validation / ui | Save with no steps | Inline "Add at least one step" | not raised |
| 6003 | N2_SEQUENCE_INVALID | Invalid N₂ Purge Sequence | warning | validation / ui | N2 block rule broken (editor / CSV) | Inline message; Save / import refused | not raised |
| 6004 | STEP_TEMP_TOO_LOW | Step Temperature Too Low | warning | validation / ui | Temperature drop without Cooling | Inline message | not raised |
| 6005 | COOLING_TEMP_INVALID | Invalid Cooling Temperature | warning | validation / ui | Cooling target invalid | Inline message | not raised |
| 6006 | CSV_STRUCTURE_INVALID | Invalid CSV Structure | warning | validation / ui | Missing header / no data row | File Failed | not raised |
| 6007 | CSV_INVALID_PROCESS | Invalid CSV Process | warning | validation / ui | Unknown process | Row skipped, file Failed | not raised |
| 6008 | CSV_INVALID_TEMP | Invalid CSV Temperature | warning | validation / ui | Temperature out of range | File Failed | not raised |
| 6009 | CSV_INVALID_TIME | Invalid CSV Time | warning | validation / ui | Time out of range | File Failed | not raised |
| 6010 | CSV_TOO_MANY_N2 | Too Many Nitrogen Steps | warning | validation / ui | More than 2 N2 rows | File Failed | not raised |
| 6011 | CSV_SAVE_FAILED | CSV Save Failed | warning | io / ui | (editor USB save raises 9081 / 9082 instead) | none | not raised |
| 6012 | MIXED_MATERIALS_SELECTED | Mixed Materials Selected | warning | selection / ui | Different materials selected in Print History | "⚠ Cannot cure different materials together!"; Cure Together disabled | not raised |
| 6013 | NO_MATERIAL_SELECTED | No Material Selected | warning | selection / ui | (no program selected) | none | not raised |
| 6014 | PROGRAM_NOT_RUNNABLE | Cannot Start Program | warning | selection / ui | N2-only program with Nitrogen Mode off | "Cannot Start Cure" dialog; nothing starts | not raised |
| 6015 | PRECURE_CHECK_FAILED | Pre-Cure Check Failed | critical | safety / daemon | Any machine refusal without its own code (door at start, illegal state, out-of-range command, start while busy, a heater fault without a code) | Refusal returned; a failed run ends error; alert raised | raised |
| 6016 | DOOR_OPENED_MID_PROCESS | Door Opened — Process Aborted | critical | safety / daemon | Door open ≥ 10 s with any output live | Door abort (heater and fan off at once, Stop all, fans 0 %, BOFA off); run error; latched until ack (dismiss) or next process start; strip fault | raised |
| 7001 | INVALID_TARGET_TEMP | Invalid Target Temperature | warning | validation / backend | Step or command target out of range, broken temperature chain, (P) empty program at start | Start / command refused | raised |
| 7002 | INVALID_UV_INTENSITY | Invalid UV Intensity | warning | validation / backend | UV outside 10-100 % | Refused | raised |
| 7003 | INVALID_COOLING_MODE | Invalid Cooling Mode | warning | validation / backend | Unknown cooling mode; N2 block needing Cooling | Refused | raised |
| 7004 | CURE_TEMP_STALL | Cure Temperature Stall | warning | process / ui | Under 1 °C of movement in 5 min, 5 windows in a row (Cure screen); also every new heater / cooling fault the machine reports | "Temperature Warning" with Continue / Abort; run not paused (P) | raised |
| 7005 | CURE_ABORTED | Cure Aborted | warning | process / ui | Only the recovery from a DVT-induced firmware hang (`Application/Dvt/DvtHang.cs`) | An operator abort raises nothing (OI-46) | raised (DVT only) |
| 9001 | TEMP_SENSOR_DISCONNECTED | Temperature Sensor Disconnected | critical | safety / daemon | family of 9010-9012 | - | family |
| 9002 | FAN_FAILURE | Fan Below Minimum Speed - System Stopped | critical | safety / daemon | family of 9020-9025 | dismiss = fan ack | family |
| 9003 | LED_FAN_NOT_SPINNING | Cooling Fan Not Spinning - Job Not Started | critical | safety / daemon | family of 9030-9034 | dismiss = fan ack | family |
| 9004 | LED_NOT_HEATING | LED Panel Not Heating - Check LED Connection | critical | safety / daemon | family of 9040 / 9041 / 9044 / 9045 | - | family |
| 9005 | LED_PANEL_TEMP_DROP | LED Panel Fault - Temperature Dropped During Cure | critical | safety / daemon | family of 9042 / 9043 | - | family |
| 9006 | TEMP_READING_FROZEN | Temperature Reading Frozen - Heater Switched Off | critical | safety / daemon | Heater ≥ 50 % for 90 s and chamber moved < 0.01 °C | Element off (fan runs on); every heating start and process step refused; Cure screen pauses with stop only; machine reboots 60 s after (after run-on); latch on disk; clears on a ≥ 1 °C move or open | raised |
| 9007 | HEATER_NOT_HEATING | Heater Not Heating - Check Voltage Selector / Fuse | critical | safety / daemon | Heater ≥ 99 % for 600 s and rise < 0.5 °C, on the ramp up only | Element off (fan runs on); run ends error 9007; clears at next heating start; does not block a start | raised |
| 9008 | N2_PRESSURE_TOO_HIGH | Nitrogen Supply Pressure Too High - Nitrogen Closed | critical | safety / daemon | Line > 3.0 bar | Opening refused; an open valve closed at once and not reopened; run continues; self-clears | raised |
| 9009 | N2_NO_SUPPLY | No Nitrogen Supply - Line Pressure Too Low | warning | process / backend | Line < 0.5 bar with the valve closed and settled 3 s | Opening refused; never closes an open valve | raised |
| 9010 | CHAMBER_SENSOR_DISCONNECTED | Chamber Temperature Sensor Disconnected | critical | safety / daemon | Chamber NTC open: at a start, at once while heating, or for 60 s | Step refused; heater off at once; Cure screen pauses with Retry / Stop; self-clears on reading | raised |
| 9011 | LEFT_LED_SENSOR_DISCONNECTED | Left LED Temperature Sensor Disconnected | critical | safety / daemon | Left LED NTC open at a start or for 60 s | Every step refused while open | raised |
| 9012 | RIGHT_LED_SENSOR_DISCONNECTED | Right LED Temperature Sensor Disconnected | critical | safety / daemon | Right LED NTC open at a start or for 60 s | Every step refused while open | raised |
| 9013 | BACK_LED_SENSOR_DISCONNECTED | Back LED Temperature Sensor Disconnected | warning | maintenance / daemon | Back NTC open 60 s | Warning only | raised |
| 9014 | DOOR_LED_SENSOR_DISCONNECTED | Door LED Temperature Sensor Disconnected | warning | maintenance / daemon | Door NTC open 60 s | Warning only | raised |
| 9015 | N2_FLOW_BLOCKED | Nitrogen Not Flowing Into the Chamber - Nitrogen Closed | critical | process / daemon | Pressure did not drop 0.3 bar within 5 s of opening | Valve closed; running program fails; clears at the next opening | raised |
| 9016 | N2_SENSOR_NOT_READING | Nitrogen Pressure Sensor Not Reading | warning | hardware / daemon | 20 s without a valid reading; also boot check 6 | N2 opening refused; an open valve is not closed; clears on reading | raised |
| 9017 | WATCHDOG_TRIPPED | Firmware Stopped Responding - Watchdog Switched Heater and UV Off | critical | safety / daemon | A watchdog trip record found on firmware return | Run ended failed; all outputs off; late writes dropped; latched until ack (Alerts or `POST /api/watchdog/ack`) | raised |
| 9020-9025 | HEATER_ / COOLING_ / LEFT_LED_ / RIGHT_LED_ / BACK_LED_ / DOOR_LED_FAN_FAILURE | <Fan> Below Minimum Speed - System Stopped | critical | safety / daemon | ≥ 20 % below nominal (heater 11.8 %) for 60 s, or ≤ 5 % for 5 s | Every cure output off at once; every step refused; latched until 60 s at nominal, an ack while not failing, or an override | raised |
| 9030-9033 | LEFT / RIGHT / BACK / DOOR_LED_FAN_NOT_SPINNING | <Panel> LED Fan Not Spinning - Job Not Started | critical | safety / daemon | LED-fan spin test < 100 RPM before UV | Fans off, UV not lit, step refused; clears on the next pass / ack / override | raised |
| 9034 | COOLING_FAN_NOT_SPINNING | Chamber Cooling Fan Not Spinning - Step Not Started | critical | safety / daemon | Chamber-fan spin test < 100 RPM before Dry / Cool | Step refused | raised |
| 9040 / 9041 / 9044 / 9045 | <PANEL>_LED_PANEL_NOT_HEATING | <Panel> LED Panel Not Heating - Check LED Connection | critical | safety / daemon | Machine: Left / Right < 1.0 °C rise after 90 s of light. Screen: all four, 15 / 30 s rule | Machine: run continues. Screen: pauses with Continue anyway / Stop | LED checks only |
| 9042 / 9043 | LEFT / RIGHT_LED_PANEL_TEMP_DROP | <Panel> LED Panel Temperature Dropped During Cure | critical | safety / daemon | ≥ 1.0 °C below peak for 30 s | Run continues; self-clears | LED checks only |
| 9046 / 9047 | LEFT / RIGHT_UV_LIGHT_NOT_DETECTED | Left / Right UV Light Not Detected | warning | safety / daemon | Lit ≥ 10 % for 5 s and the photoresistor is not below 0.6 × dark | Warning only; clears when light is seen or the panel goes off | raised |
| 9048 | BOFA_NOT_DETECTED | BOFA Unit Not Detected | warning | hardware / daemon | Switch declares BOFA, presence line reads empty | Warning only; an unreadable line never raises it | raised |
| 9050 | LED_TEMP_SENSOR_DISCONNECTED | LED Temperature Sensor Disconnected | warning | maintenance / daemon | family of 9013 / 9014 | - | family |
| 9051 | FAN_WEAR_WARNING | Fan Speed Low - Replace Fan | warning | maintenance / daemon | family of 9060-9065 | dismiss = fan ack | family |
| 9052 | NFC_READER_NOT_DETECTED | NFC Reader Not Detected | warning | io / backend | NFC enabled with no reader; a reader seen since boot unplugged while enabled | Switch stays off; dropped from `ui-alerts.json` at load if undismissed | raised |
| 9060-9065 | HEATER_ / COOLING_ / LEFT_LED_ / RIGHT_LED_ / BACK_LED_ / DOOR_LED_FAN_WEAR | <Fan> Speed Low - Replace Fan | warning | maintenance / daemon | ≥ 10 % below nominal for 60 s | Warning only; clears within 10 % | raised |
| 9080 | UNKNOWN_DIAGNOSTIC_TOOL | Unknown Network Tool | warning | validation / backend | Unknown network diagnostic tool requested | Refused | raised |
| 9081 | USB_NOT_FOUND | No Disk-on-Key Connected | warning | storage / backend | No USB drive for CSV / report export or update | Message (report export: 3 s message only, no alert) | raised |
| 9082 | USB_WRITE_FAILED | Disk-on-Key Write Failed | warning | storage / backend | USB write failed | Message | raised |
| 9083 | LOG_EXPORT_FAILED | Log Export Failed | warning | storage / backend | Any log-export failure | Alert plus "✗ No USB drive found" | raised |
| 9084 | NETWORK_STATUS_UNAVAILABLE | Network Status Unavailable | warning | network / backend | Network status cannot be read | Alert | raised |
| 9085 | NETWORK_DIAGNOSTIC_FAILED | Network Diagnostic Failed | warning | network / backend | Ping / traceroute / DNS failed | Alert | raised |
| 9086 | UPDATE_FAILED | Software Update Failed | critical | update / backend | Update failed (integrity failures included) | Modal shows the failed step and Retry | raised |
| 9087 | UPDATE_PACKAGE_NOT_FOUND | Update Package Not Found | warning | update / backend | No package on USB | Modal stops at the package step | raised |
| 9088 | UPDATE_INTEGRITY_FAILED | Update Integrity Check Failed | critical | security / ui | (reported as 9086 instead) | - | not raised |
| 9089 | HW_API_UNREACHABLE | Hardware Service Unreachable | critical | system / ui | Screen can no longer read the machine state (once per loss) | Critical alert; blocks Start Cure while undismissed | raised |

Notes:

* Family mapping: 9010-9012 → 9001; 9013-9014 → 9050; 9020-9025 → 9002; 9030-9034 → 9003; 9040, 9041, 9044, 9045 → 9004; 9042-9043 → 9005; 9060-9065 → 9051.
* `ErrorCoverageTests.NotImplemented` lists the 20 not-raised codes: 3002, 3003, 4001, 4002, 5001, 6001-6014 and 9088.
* Built-in fallback differences (OI-60): 7004 is critical, 9004 / 9005 are warnings, and 6016 has the key DOOR_OPENED_DURING_CURE. Other keys and messages differ too (NO_USB_DRIVE, "Machine API Unreachable", category hardware / system), and there is no troubleshooting.

---

## Conflicts between sources

Each item states both sides; neither side is invented. **Default to P (the newer product SRS, 1.0.141)** unless the owner decides otherwise, and record each item as a question in the ticket.

| # | Topic | Source A | Source B |
|---|---|---|---|
| C-1 | Runtime / version | E: .NET 8, written against 1.0.32 | Repo: .NET 10, 1.0.152. P: 1.0.141 |
| C-2 | Boot self-test | E §5.1: 6 checks | P §3.3.1: 7 checks (adds N2 Pressure Sensor), planned-restart skip, simulation pass |
| C-3 | Empty program | E SRS-RUN-5: completes immediately with a message | P §7.3.1: refused at Start with 7001. E §6.2: 6015 |
| C-4 | Drying upper limit | E SRS-VAL-1, Q: Drying 30-80 °C | P §6.7.2: Drying 30-50 °C (the runner refuses > 50) |
| C-5 | Sensor / fan codes | E §5-§9: 9001 / 9002 / 9003 / 9051 raised | P §9 and E §11 update: per-component codes, families not raised (E says "since 1.0.106", P says "since 1.0.141") |
| C-6 | Temperature stall | E §5.7: the UI pauses the run and asks | P §7.3.6: the run is not paused (OI-47) |
| C-7 | Nitrogen Mode minimum | P §11.3: 0.5 bar (window 0.5-3) | P §11.6 diagram and §11.7: 1 bar |
| C-8 | Registry size | P §9 intro: 76 records | P §9.9 / §9.11 / §9.13: 84 records |
| C-9 | Watchdog cut | E §5.7: heater SSR, four UV dimming channels, both LED supply relays | P §7.4: heater element, four UV dimming channels, both UV supply SSRs |
| C-10 | Error 7005 | E §11: defined but never raised | E §13 item 2 and P: raised only by the DVT hang recovery |
| C-11 | UI canvas | Q: React 800×480 scaled | E SRS-UI-2: native 1600×1000 scaled and rotated |
| C-12 | Simulation slow cooling | Q simulation: slow 1.0 °C/min | Estimator: slow 0.8 °C/min (different models; keep both) |
| C-13 | Fan pre-check threshold | E §5.6: every chamber fan ≥ 100 RPM | P §6.8: judged against the fan-health stop / warn thresholds; WARN does not block |
| C-14 | Interrupted run | E SRS-DATA-7: marked error | P §8.3 / OI-69: only the JSON backend does it; DB-10 requires it |
| C-15 | Card backup | SRS-UI-14 / P §3.5: backup to `/mnt/ssd2/scure` | P §3.5 measurement / OI-74: the path cannot exist on the Origin image, so 4003 is raised on every SN set |
| C-16 | Fan test fixed nominal | P §11.3 / OI-52: 2850 / 3050 / 2780 RPM shown at 0 RPM | Q: simulation fan RPM 2850 when duty > 0 |
| C-17 | Auto Sync | E SRS-UI-16 / P §11.3 (1.0.142): network time itself | P OI-54 parts (a)-(c) still open |

### OPEN QUESTIONS in the SRS

Source P §12 lists the Open Issues that are still open; closed ones are noted at the end. E §13 lists known gaps. E and P also mark individual items open or TBR. Do not resolve these in code. Build the current behaviour as specified above, and carry each question into the ticket that touches it.

**P §12.1 - still open from revision 1.0**

1. **OI-8** Name validation rules: only "non-empty" is specified. Is there a maximum length, a set of allowed characters, or a uniqueness rule (local or cloud)? (§4.3.3)
2. **OI-10** Organization CSV schema: any file containing a UUID is accepted, and the first UUID wins. Is a stricter schema or validation required? (§5.3.2)
3. **OI-12** Print entries and organization scope. (a) Should the unit record a print for every cure it runs? (b) Recent Prints shows only with an organization linked, but the stored history is not organization-scoped. Must history be kept per organization? (§6.4, §10)
4. **OI-15** Same-material rule: is material-name equality the full business rule, or are there tray / channel / position rules beyond it? (§6.4.1)

**P §12.2 - new in revision 2.0**

5. **OI-29** Is GrabCAD still a requirement (what reaches it, by which path), or should it be removed in favour of sCure Cloud? (§1.3, §2)
6. **OI-30** SN provisioning. (a) Keep cloud SN assignment and registration, or retire that flow and 3001-3003? (b) Must a scanned SN be validated (uniqueness, checksum, prefix)? (c) Who corrects a wrongly scanned SN, and how? (§3)
7. **OI-31** Config write failure. (a) Must a failed `ui-settings.json` save be shown to the user and block the step (4002 or a new code)? (b) Must the System Name, organization, favorites, calibration and counters be backed up too, or is identity enough? (See OI-67; settled for the SN only.)
8. **OI-32** Should sCure Cloud receive the System Name, SN and organization, and when (on change or every sync)? Today only the cloud display name (default "CureBox") is sent. Supersedes OI-9 and OI-11.
9. **OI-33** Boot self-test failure policy. (a) Should a failure block cures or raise an alert, and with which codes? (b) Should the result be recorded? (c) Confirm the acceptance values: door wait 60 s, sensor wait 5 s, LED tests 15 s / 30 s with a 0.8 °C rise, and the planned-restart skip within 10 min.
10. **OI-34** Origin sign-in on the unit. (a) Which methods must work (e-mail and password, Google, Microsoft)? Google refuses the windowless "auto" mode. (b) Should the step check the internet first and show an offline message?
11. **OI-35** (superseded by OI-70; history only) Presets that break the rules: correct the presets, or relax the rules?
12. **OI-36** Presets must offer no Edit action at all (the hidden Edit position opened the preset). What should happen to a program already saved with a preset's id?
13. **OI-37** Should pending print ids be cleared when the selection changes? Should Cure Together with a single print also start the cure?
14. **OI-38** Is print `duration` in seconds in the portal contract? The `send_print` fallback uses the estimate in minutes (or 20) and must then be converted.
15. **OI-39** Must program names be unique (and how is a clash reported), or should prints reference the program by id? Favoriting can change which program a print runs.
16. **OI-40** Should the Home estimate follow Nitrogen Mode? What is the real purge duration? 120 s is fixed and not configurable.
17. **OI-41** A blank Cooling temperature in a CSV becomes 25 °C and always fails. Should it default to a valid value (e.g. 30 °C), or report "Cooling needs a target temperature"?
18. **OI-42** Door open mid-run: the screen says "Process Paused", but the run is not paused (heater and UV stay commanded, the timer counts). Should UV and heater be cut and the clocks frozen during the 10 s grace, or should the wording change? Do relays K1 / K2 cut the LED supply in hardware when the door opens? (unconfirmed)
19. **OI-43** N2 Purge step. (a) Must it run the step pre-flight (sensors, critical fan) and a line-pressure check (threshold, code)? (b) Is 120 s the required fill time, or should it be a setting? (Partly resolved: line checks 9008 / 9009 / 9015 / 9016 exist.)
20. **OI-44** Cooling uses fixed fan duties (100 / 60 / 30 %). Is that the requirement, or is a closed-loop cooling rate (°C/min per mode) required?
21. **OI-45** Which representative program should the §7.7 timing figure show (e.g. Heating → N2 → Cure → Cooling) for regeneration with `tools/gen-timing.mjs`?
22. **OI-46** Operator abort. (a) Should it record or raise 7005 in the run and on Alerts? (b) Is the 15 min heater-fan run-on after an abort intended (only a door abort cuts at once)?
23. **OI-47** Stall (7004), pause on 9010 / 9006, fan-failure continue-anyway and LED-panel checks live only in the Cure screen, so a run started via `/api/recipe/start` gets none of them. (a) Must the firmware enforce them for every run? (b) Should the Temperature Warning pause the run?
24. **OI-48** A run's sensor and fan issues are taken only at the end (the data model says "open at any point"). Should the run accumulate issues over the whole run?
25. **OI-49** Report file names. (a) Two patterns exist (`cure-report-<M>-<yyyy-MM-dd>` overwrites same-day runs; `scure-report-<M>-<yyyyMMdd-HHmm>`). Which single, per-run-unique pattern is required? (b) Must report-export failures 9081 / 9082 be raised as alerts, as 9083 is?
26. **OI-50** Settings feedback for refused or failed commands: damper and BOFA refusals are only logged; fan-slider refusals are hidden; the LED test shows FAIL with no reason; heating refusals give generic 6015; Export Logs always says "No USB drive found". Which must show a message or raise a specific code, and with what text?
27. **OI-51** Should the fan sliders show the current duty? Should a manual fan duty be cleared on leaving Settings, after a timeout, or at the next process start?
28. **OI-52** The fan test shows a fixed nominal (2850 / 3050 / 2780) next to FAIL at 0 RPM. Should it show the measured 0? Are the fixed values needed anywhere?
29. **OI-53** With no pressure reading ("N/A"), Nitrogen Mode can still be switched on (9016 only warns). Must it be blocked outright? (Window 0.5-3 bar settled by the owner 2026-10-25; supersedes OI-27.)
30. **OI-54** Main defect closed in 1.0.142. Still open: (a) the time zone cannot be set on the unit; (b) who may set the clock by hand (any operator outside a cure today); (c) should offline-on-purpose units get a battery-backed RTC (the board RTC reads 1970)? Supersedes OI-28.
31. **OI-55** Should Unlink ask for confirmation or a PIN, and should it return to Setup or only clear the organization?
32. **OI-56** Is a maintenance warning on component on-hours required (which components, which hour limits, which code)? The old Lead On Time / W/1053 is gone.
33. **OI-57** One fixed four-digit PIN on every unit, with no attempt limit or lock-out. Is that acceptable for CRA / EN 18031, or is a per-unit or service-account credential with an attempt limit required?
34. **OI-58** Network screen, LED Intensity Calibration, Material HDT Calibration and the Restarting screen have no SRS section. Should they get one, and who owns them?

**P §12.2 - §9 Error management and §10 Data**

35. **OI-59** 20 registry codes are never raised (3002, 3003, 4001, 4002, 5001, 6001-6014, 9088), which conflicts with ERR-01 and diagram traceability. Should the screens raise them (as alerts, or as inline text resolved by code), or should the codes be retired from the registry and diagrams?
36. **OI-60** Should the built-in fallback registry be generated from `errors.json` at build time? Is running on the fallback itself an alert condition (its severities differ and drive the start block)?
37. **OI-61** Screen alerts never auto-clear, and a cleared critical still blocks Start Cure. Is operator acknowledgement of every critical intended, or should self-clearing codes leave the screen or stop blocking?
38. **OI-62** Registry delivery. (a) How do edits reach installed machines (update only, cloud push, USB)? (b) Add videoUrl to editableFields? (c) Keep, redefine or drop `layer`?
39. **OI-63** Should the LED panel checks (9040-9045) be enabled for production? If so, which check (machine Left / Right 90 s / 1.0 °C, or screen all-four 15 / 30 s) and which thresholds?
40. **OI-65** Keep the optional PostgreSQL backend? If so: device-local or central, who provisions it, access control and secrets, backup, and migration between backends. Or drop it?
41. **OI-66** Retention for `phase_timings.json`, `ui-alerts.json`, `dev_events.jsonl` and `print_history.json`, which are unbounded today (count or age)? Should phase timings be pruned with their run?
42. **OI-67** Is losing all data except the SN on reflash acceptable, or is backup / restore (USB or cloud) required, at least for counters, calibration and SN?
43. **OI-68** PostgreSQL telemetry keeps only a subset, and the material name in `v_cure_history` is empty for unit-started runs. Must both backends keep identical cure-run data?
44. **OI-69** Should DB-10 (interrupted run → error) apply to the PostgreSQL backend as well? Should an interrupted run be `error`, or a distinct status (e.g. "interrupted / power loss")?

**P §12.4 - new in revision 2.1**

45. **OI-70** Who supplies the real per-material post-cure parameters for the 19 P3 presets (today rigid / high-temp / clear / elastomer placeholders: dry, cure and cool, ≤ 65 °C, ≤ 1 h)? Until then, should the screen mark these programs as provisional?
46. **OI-71** Confirm gesture-only Home as the requirement, with no Start button kept for accessibility, so the reference screenshots (ref-startcure.png, ref-editbtn.png, ref-actions.png, home.png) and the edit-mode / home-start-cure diagrams can be regenerated.
47. **OI-72** The BOFA chain was never measured. Who measures the 4DA_ANALOG volts against percent, the fan start percent, and the presence polarity (`bofa.present_active_low` is an assumption; `/api/state bofaDetected` with the cable in and out)? Should 9048 stay a warning until then? (F2 is a 0.5 A PTC at 24 V, which bounds the fan.)
48. **OI-73** UV-light thresholds (ratio 0.6, 5 s, 10 %, from a 55 kΩ dark reading) are uncalibrated. What are the measured values (low intensity, partly lit panel)? Should 9046 / 9047 stay warnings or stop a cure?
49. **OI-74** There is no removable medium on the Origin image, so 4003 fires on every SN set. (a) Should the backup go to the USB drive when present, with its absence silent? (b) Will a dedicated card be fitted, and at which mount point? (c) Should the backup be off by default until settled?

**Other items marked open in the sources**

50. Hardware pull-down on LED_SWITCH_SIGNAL is an open hardware item (P §7.4).
51. Nitrogen analog input without a 2:1 divider saturates, so the over-pressure interlock is blind until the divider is fitted (P §9.14.8).
52. `[TBR]` values in `SRS-CUREBOXCTRL-RevA.docx`: every remaining `[TBR]` carries an open item in that document's section 8 (R). Not readable as text here; read `build-srs-docx.js` for the list.

**E §13 - known gaps (code facts the owner has not yet accepted or rejected)**

53. No dedicated over-temperature trip. Protection is indirect: the sensor validity band, the 80 °C ceiling, the heating-loop health check and the watchdog.
54. Error 7005 is raised only by the DVT hang test. An operator abort has no code.
55. `uvRampPercent` is carried on a step but never used. No UV ramping is implemented.
56. Immediate stop and normal stop behave identically except for the message. Only a door abort skips the run-on.
57. LED panel heating checks (9004 / 9005, now 9040-9045) are disabled by default.
58. Two ramp-time models coexist: the runtime uses one flat rate chosen by the target, while the estimator integrates band by band. They disagree across band boundaries.
59. Two validators: the editor allows cooling 30-75 °C, the API 20-80 °C.
60. Temperature-stall detection lives only in the UI. An HTTP-driven run has none.
61. Nitrogen steps skip the sensor and fan pre-flight.
62. Simulation is a silent fallback, visible only through `hwSource`, and cures can run against the simulated machine.
63. The local API is unauthenticated with open CORS, and several routes always answer `ok:true`.
64. Default credentials are baked in: image user and password, the installer's default unit password, and the developer PIN.
65. A NetBird setup key written at imaging time sits in clear text on the boot partition until the first boot moves it.
66. Phase timings have no DB backend.
67. Material HDT calibration state is not persisted, so a restart during calibration loses it.
68. The boot self-test can be skipped with any number of failures. LED checks are failed when the door check failed.
69. Two UI stacks (native and browser kiosk) are still selected at install time.
70. `/api/recipe/*` and `/api/ui/*` are implemented but missing from `01-api-contract.md`.
71. The bundled Program List carries no verified post-cure profiles (= OI-70; 46 / 55 / 39 / 45 min per profile by `ProgramEstimator`).
72. The BOFA connector was never exercised on a unit (= OI-72). The schematic sheet is "4DA INTERFACE (Q18, Q19, U19) & CONNECTOR (J16)". If the polarity is wrong, flip the key.
73. The registry publishes 20 codes the firmware never raises (= OI-59). The card half of the setup family is built (3001 / 4003), the cloud half is not, and no endpoint allocates a serial. 9088: the updater verifies the package but reports a failure without that code.

**Closed, for reference (do not reopen):** OI-64 (closed 1.0.110 by 9017); OI-1, 7, 13, 16, 19, 25, 26 (resolved); OI-6 (reopened and resolved by the card backup); OI-9, 11 (→ OI-32); OI-17, 21, 22 (obsolete); OI-18, 20 (largely resolved → OI-59, OI-61); OI-23, 24 (→ OI-65, 67, 68); OI-27 (→ OI-53); OI-28 (→ OI-54); OI-35 (→ OI-70); OI-43 partly and OI-53 largely resolved (1.0.107-1.0.109); OI-31 (b) resolved for the SN.
