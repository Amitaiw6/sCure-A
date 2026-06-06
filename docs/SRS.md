<style>
  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1a1a2e; line-height: 1.7; max-width: 900px; margin: 0 auto; padding: 40px; }
  h1 { border-bottom: 3px solid #0ea5e9; padding-bottom: 12px; color: #0c4a6e; }
  h2 { border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 48px; color: #0c4a6e; }
  h3 { color: #1e40af; margin-top: 32px; }
  h4 { color: #475569; }
  table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 0.9em; }
  th { background: #0c4a6e; color: white; padding: 10px 14px; text-align: left; }
  td { border: 1px solid #e2e8f0; padding: 8px 14px; }
  tr:nth-child(even) { background: #f8fafc; }
  code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; color: #0f172a; }
  pre { background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow-x: auto; }
  pre code { background: none; color: inherit; }
  blockquote { border-left: 4px solid #0ea5e9; padding: 12px 20px; margin: 16px 0; background: #f0f9ff; color: #0c4a6e; }
  .cover-page { text-align: center; padding: 80px 0 60px; page-break-after: always; }
  .cover-page h1 { border: none; font-size: 2.4em; color: #0c4a6e; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600; }
  .badge-critical { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
  .badge-high { background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa; }
  .badge-medium { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
  .badge-low { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
  .req-id { font-family: monospace; font-weight: 700; color: #0ea5e9; }
  hr { border: none; border-top: 1px solid #e2e8f0; margin: 32px 0; }
  .toc a { text-decoration: none; color: #1e40af; }
  .toc a:hover { text-decoration: underline; }
  .watermark { color: #cbd5e1; font-size: 0.8em; text-align: center; margin-top: 60px; }
</style>

<div class="cover-page">

# S-Cure
## Software Requirements Specification

---

**Document ID:** SRS-SCURE-2026-001

**Version:** 1.1.0

**Classification:** Confidential

**Date:** April 2026

---

| | |
|---|---|
| **Prepared by:** | S-Cure Development Team |
| **Approved by:** | ___________________________ |
| **Customer:** | S-Cure Ltd. |
| **Project:** | S-Cure Curing System Control Software |
| **Platform:** | Raspberry Pi Compute Module 5 (CM5-104032) |

---

*S-Cure Ltd. -- All Rights Reserved*

</div>

---

## Document Control

### Revision History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 0.1.0 | March 2026 | Dev Team | Initial draft |
| 0.9.0 | March 2026 | Dev Team | Feature complete draft |
| 1.0.0 | April 2026 | Dev Team | Release candidate |
| 1.1.0 | April 2026 | Dev Team | Added Nitrogen rules, CoolingMode, screensaver, CSV format update |

### Distribution List

| Name | Role | Access |
|------|------|--------|
| CTO | Approver | Full |
| Project Manager | Reviewer | Full |
| CS Team Lead | Contributor | Sections 3.10, 6 |
| QA Lead | Reviewer | Full |
| Hardware Engineer | Contributor | Sections 3.5, 4.5 |

### Referenced Documents

| Document ID | Title | Version |
|-------------|-------|---------|
| HW-SPEC-001 | S-Cure Hardware Specification | 1.0 |
| RPi-CM5-DS | Raspberry Pi CM5 Datasheet | Rev 1.0 |
| UI-DESIGN-001 | S-Cure UI/UX Design Document | 1.0 |
| TEST-PLAN-001 | S-Cure Test Plan | TBD |

---

## Table of Contents

<div class="toc">

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [Functional Requirements](#3-functional-requirements)
   - 3.1 [Setup & Configuration](#31-setup--configuration)
   - 3.2 [Home Screen](#32-home-screen)
   - 3.3 [Material Management](#33-material-management)
   - 3.4 [Cure Process](#34-cure-process)
   - 3.5 [Temperature Control](#35-temperature-control)
   - 3.6 [Top Bar](#36-top-bar)
   - 3.7 [Settings](#37-settings)
   - 3.8 [Print History](#38-print-history)
   - 3.9 [Network](#39-network)
   - 3.10 [Alerts & Errors](#310-alerts--errors)
   - 3.11 [Software Update](#311-software-update)
   - 3.12 [On-Screen Keyboard](#312-on-screen-keyboard)
   - 3.13 [Wake/Sleep & Screen Saver](#313-wakesleep--screen-saver)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Data Models](#5-data-models)
6. [API Specification](#6-api-specification)
7. [System Architecture](#7-system-architecture)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Glossary](#9-glossary)

</div>

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the complete functional and non-functional requirements for the **S-Cure Curing System Control Software**. This document serves as the primary reference for development, testing, and validation of the software system.

This document is intended for:
- Software development team
- Quality assurance engineers
- Hardware integration engineers
- Customer support team
- Project stakeholders

### 1.2 Scope

The S-Cure software controls an industrial UV/thermal curing chamber designed for post-processing of 3D printed parts, composite materials, and dental models. The software system consists of three layers:

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| **Frontend** | React 19 + TypeScript + Vite | Touch UI (800x480) |
| **Middleware** | Python Flask API | Hardware abstraction, system commands |
| **Driver** | C++ with pybind11 | GPIO, SPI, PWM, real-time control |

### 1.3 Definitions & Abbreviations

| Term | Definition |
|------|-----------|
| Cure | UV/thermal treatment process for hardening materials |
| Phase | A single step in a cure sequence (Heating, Drying, Cure, Bleaching, Cooling, Nitrogen) |
| Material Profile | A CSV-defined sequence of cure phases for a specific material |
| Preset | Factory-defined material profile (read-only, non-deletable) |
| PI Controller | Proportional-Integral feedback controller for temperature regulation |
| DAC | Delta-Sigma Digital-to-Analog Converter for heater PWM modulation |
| RPi CM5 | Raspberry Pi Compute Module 5 (quad Cortex-A76, 2.4GHz, 4GB RAM) |
| Ramp | Temperature increase period before hold timer begins |
| SCU | Signed Cure Update -- the update package format (.scu) |
| BOFA | Fume extraction system brand |

### 1.4 Conventions

Throughout this document:

- <span class="badge badge-critical">CRITICAL</span> -- Safety-critical requirement, must be implemented and verified
- <span class="badge badge-high">HIGH</span> -- Core functionality, required for release
- <span class="badge badge-medium">MEDIUM</span> -- Important feature, may be deferred
- <span class="badge badge-low">LOW</span> -- Nice-to-have, lowest priority
- **SHALL** -- Mandatory requirement
- **SHOULD** -- Recommended but not mandatory
- **MAY** -- Optional

---

## 2. Overall Description

### 2.1 Product Perspective

The S-Cure software is an embedded control system for a standalone curing apparatus. It operates as a self-contained kiosk application without dependency on external servers or internet connectivity.

```
  +-----------+       +-----------+       +-----------+
  |  7" Touch |       |  RPi CM5  |       |  IO Board |
  |  Display  |◄─────►|  SoC      |◄─────►|  Relays   |
  |  800x480  |  HDMI |  4GB RAM  |  GPIO |  Sensors  |
  +-----------+       +-----------+       +-----------+
                            │
                      +-----------+
                      | Ethernet  |
                      | USB Ports |
                      +-----------+
```

### 2.2 User Classes

| User Class | Description | Access Level |
|------------|-------------|-------------|
| **Operator** | Daily user. Selects materials, starts/monitors cures, views history | UI: Home, Cure Process, Print History |
| **Technician** | Maintenance role. Runs diagnostics, adjusts hardware settings | UI: All pages including Settings |
| **CS Engineer** | Remote support. Edits error documentation and troubleshooting guides | File: `errors.json` (editable fields only) |
| **Factory** | Manufacturing setup. Configures device identity, loads presets, flashes firmware | File: `system.json`, presets folder, firmware |

### 2.3 Operating Environment

| Parameter | Specification |
|-----------|--------------|
| **Processor** | BCM2712 Quad Cortex-A76 @ 2.4GHz |
| **Memory** | 4GB LPDDR4X |
| **Storage** | 32GB eMMC |
| **Display** | 7" capacitive touch, 800x480 pixels |
| **OS** | Raspberry Pi OS (Debian Bookworm) |
| **Runtime** | Chromium 120+ in kiosk mode |
| **Network** | Gigabit Ethernet, optional WireGuard VPN |
| **USB** | 2x USB 3.0 for updates and log export |
| **GPIO** | 40-pin header for hardware control |

### 2.4 Design Constraints

| ID | Constraint |
|----|-----------|
| DC-01 | No physical keyboard; all input via on-screen touch keyboard |
| DC-02 | Temperature range limited to 20--80 degrees C by hardware |
| DC-03 | All touch targets minimum 44x44 pixels (WCAG 2.5.5) |
| DC-04 | System must operate fully offline (no internet dependency) |
| DC-05 | Dark-only UI theme (high contrast for industrial environment) |
| DC-06 | Single-user system; no authentication required |
| DC-07 | Viewport locked to 800x480; no responsive scaling |

### 2.5 Assumptions & Dependencies

| ID | Assumption |
|----|-----------|
| A-01 | IO Board firmware is stable and communicates via GPIO |
| A-02 | Thermocouple sensor provides accurate readings within +/-0.5 degrees C |
| A-03 | Door sensor is a normally-closed contact switch |
| A-04 | N2 pressure sensor provides analog reading convertible to bar |
| A-05 | Chromium browser is pre-installed and configured for kiosk mode |

---

## 3. Functional Requirements

### 3.1 Setup & Configuration

#### <span class="req-id">FR-3.1.1</span> Initial Setup Wizard <span class="badge badge-high">HIGH</span>

| Attribute | Value |
|-----------|-------|
| **Description** | First-boot wizard for device configuration |
| **Trigger** | `setupComplete === false` in system config |
| **Precondition** | Device has been powered on for the first time (or after factory reset) |

**Requirements:**

1. The system SHALL display a 3-step setup wizard:
   - **Welcome**: Animated logo with "Get Started" button
   - **Step 1 -- Name**: Device naming via on-screen keyboard
   - **Step 2 -- Organization**: Organization linking via USB CSV file
2. The user SHALL be able to skip organization setup ("Continue without organization")
3. After setup completion, the system SHALL navigate to the home screen (`/`)
4. Setup state SHALL persist in `localStorage` under key `scure-org`
5. Step indicators (dots) SHALL show current progress

#### <span class="req-id">FR-3.1.2</span> System Configuration <span class="badge badge-high">HIGH</span>

| Attribute | Value |
|-----------|-------|
| **Source File** | `/config/system.json` |
| **Mutability** | Read-only (except where noted) |

**Read-only fields:**

| Field | Example | Description |
|-------|---------|-------------|
| `serialNumber` | cure45223 | PCB serial number |
| `firmware` | 0.63.0-dev | Current firmware version |
| `lastBoot` | 2026-03-29T08:23:00 | Last boot ISO timestamp |
| `deviceName` | OR200001 | Factory device identifier |
| `leadOnTimeHours` | 10 | UV LED cumulative hours |
| `model` | S-Cure A | Device model |
| `hardwareRevision` | CM5-rev1.0 | Hardware revision |
| `manufacturer` | S-Cure Ltd. | Manufacturer |

**User-editable:**

| Field | Storage | Description |
|-------|---------|-------------|
| `systemName` | localStorage | Display name shown in TopBar |

#### <span class="req-id">FR-3.1.3</span> Organization Management <span class="badge badge-medium">MEDIUM</span>

1. Organization ID SHALL be extracted from a CSV file on USB drive
2. CSV SHALL contain a UUID matching pattern: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
3. Organization ID SHALL be stored in `localStorage`
4. Organization can be changed or removed in Settings page
5. Print history features SHALL require an active organization

---

### 3.2 Home Screen

#### <span class="req-id">FR-3.2.1</span> Recent Prints Display <span class="badge badge-high">HIGH</span>

| Attribute | Value |
|-----------|-------|
| **Location** | Top section of home screen |
| **Max Items** | 3 most recent |
| **Data Source** | PrintHistoryContext |

**Each print log SHALL display:**

| Element | Description |
|---------|-------------|
| Status icon | Green check (completed), Yellow triangle (aborted), Red X (error) |
| Print name | e.g. "Print #008" |
| Material name | e.g. "st45" |
| Duration | e.g. "20min" |
| Time ago | e.g. "2d ago" |
| Printer name | e.g. "OR200001" |

**Behavior:**
1. Tapping a log SHALL select it and deselect any previous material selection
2. If a matching material exists (by name), Start Cure SHALL be enabled for the selected print
3. Only one item can be selected at a time (print OR material)
3. "View All" button SHALL open PrintHistoryModal
4. Section hidden or shows placeholder when no organization is linked

#### <span class="req-id">FR-3.2.2</span> Material List <span class="badge badge-high">HIGH</span>

1. The system SHALL display all available materials (presets + user-created)
2. Preset materials SHALL show a lock icon (non-deletable, non-editable)
3. Material count SHALL be displayed: "Material List (N)"
4. Selected material SHALL have a blue border highlight

#### <span class="req-id">FR-3.2.3</span> Material Actions <span class="badge badge-high">HIGH</span>

| Button | Action |
|--------|--------|
| **+ New** | Opens CsvBuilderModal for new material |
| **CSV** | Opens ImportCsvModal for file upload |
| **Edit** | Toggles edit mode (pencil + trash icons per user material) |
| **Start Cure** | Navigates to `/cure-process` with selected material |

---

### 3.3 Material Management

#### <span class="req-id">FR-3.3.1</span> CSV Builder <span class="badge badge-high">HIGH</span>

| Attribute | Value |
|-----------|-------|
| **Component** | CsvBuilderModal |
| **Input Method** | Touch controls only (no keyboard input for values) |

**Layout:** Horizontal scrollable cards (left-to-right). Each step is a card. "Add Step" button at the end. Steps scroll and center on addition.

**Step Configuration:**

| Field | Control | Range | Applies To |
|-------|---------|-------|------------|
| Process Type | Select dropdown | Drying, Heating, Cure (405nm), Bleaching (450nm), Cooling, N₂ Purge | All |
| Temperature | +/- buttons | 20--80 degrees C, step 5 | All except Nitrogen |
| Time | +/- buttons | 1--120 min, step 1 | Drying, Heating, Cure, Bleacher |
| Cooling Mode | Select | Fast / Medium / Slow | Cooling only |
| Timer Mode | Select | At temperature / On ramp start | Cure, Bleaching |
| UV Intensity | +/- buttons | 5--100%, step 5 | Cure, Bleaching |
| UV Start Mode | Select | Immediately / At temperature | Cure, Bleaching |

**Validation Rules (Save button):**

| Rule | Error Message |
|------|---------------|
| No name entered | "Enter a program name" |
| No steps | "Add at least one step" |
| N₂ without Heating/Cure/Bleacher after | "Add a Heating, Cure, or Bleaching step after N₂ purge" |
| N₂ without any Cooling step | "Nitrogen must be vented — add a Cooling step to save the program" |

Validation errors appear only when the user taps the Save button.

#### <span class="req-id">FR-3.3.2</span> CSV Import <span class="badge badge-high">HIGH</span>

**CSV Format:**

```csv
Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,UVRampPercent,CoolingMode
1,Heating,40,10,,,,,
2,Nitrogen,,,,,,,
3,Cure,40,15,on-target,30,at-target,,
4,Cooling,25,,,,,,medium
```

**Column mapping:**

| # | Column | Description |
|---|--------|-------------|
| 1 | Step | Step number |
| 2 | Process | Heating, Drying, Cure, Bleacher, Cooling, Nitrogen |
| 3 | Temperature | 20-80°C (empty for Nitrogen) |
| 4 | Time | 1-120 min (empty for Cooling/Nitrogen) |
| 5 | TimerMode | `on-ramp` or `on-target` (Cure/Bleacher only) |
| 6 | UVIntensity | 5-100% (Cure/Bleacher only) |
| 7 | UVStart | `at-start` or `at-target` (Cure/Bleacher only) |
| 8 | UVRampPercent | 10-100% (optional) |
| 9 | CoolingMode | `fast`, `medium`, or `slow` (Cooling only) |

**Validation Rules:**

| Rule | Condition | Error Message |
|------|-----------|---------------|
| Column count | < 4 columns | "Not enough columns (need at least 4)" |
| Process type | Not in valid list | "Invalid process (must be Heating, Drying, Cure, Cooling, Bleacher, or Nitrogen)" |
| Temperature | < 20 or > 80 | "Invalid temperature (must be 20-80)" |
| Time | < 1 or > 120 | "Invalid time (must be 1-120)" |
| Max N₂ steps | > 2 | "Maximum 2 nitrogen purge steps allowed" |
| N₂ without process | No Heating/Cure/Bleacher after N₂ | "Add a Heating, Cure, or Bleaching step after N₂ purge" |
| N₂ without Cooling | N₂ present but no Cooling step | "Nitrogen must be vented — add a Cooling step" |
| Temp decreasing | Temp drops without Cooling | "Temperature cannot decrease without a Cooling step" |
| No valid steps | 0 parsed | "No valid steps found" |

#### <span class="req-id">FR-3.3.3</span> Preset Materials <span class="badge badge-high">HIGH</span>

| Preset | Steps | Total Duration |
|--------|-------|---------------|
| st45 | Drying -> Heating -> Cure -> Cooling | 30 min |
| Carbon Fiber | Drying -> Heating -> Cure -> Bleaching -> Cooling | 61 min |
| Fiberglass | Drying -> Heating -> Cure -> Cooling | 33 min |
| ABS-Like | Drying -> Heating -> Cure -> Bleaching -> Cooling | 53 min |
| Dental Model | Drying -> Heating -> Cure -> Bleaching -> Cooling | 23 min |
| Flexible | Drying -> Heating -> Cure -> Cooling | 55 min |

**Constraints:**
- Loaded from `/materials/presets/` on every app start
- NOT stored in localStorage
- NOT deletable or editable by any user

#### <span class="req-id">FR-3.3.4</span> Material Persistence <span class="badge badge-medium">MEDIUM</span>

1. User materials SHALL persist in `localStorage` (key: `scure-materials`)
2. On save, CSV file SHALL auto-download to the browser
3. Material data includes: id, name, steps[], totalDuration, csvContent, createdAt, isPreset

#### <span class="req-id">FR-3.3.5</span> Material Editing <span class="badge badge-medium">MEDIUM</span>

1. Edit mode shows pencil icon per non-preset material
2. Clicking pencil opens CsvBuilderModal pre-populated with existing data
3. Modal title changes to "Edit Program", save button to "Update"
4. Preset materials SHALL NOT show edit controls

---

### 3.4 Cure Process

#### <span class="req-id">FR-3.4.1</span> Process Initiation <span class="badge badge-critical">CRITICAL</span>

1. Cure SHALL start automatically when navigating to `/cure-process`
2. Back button (arrow) SHALL be hidden during active cure
3. The ONLY exit path SHALL be via Abort confirmation

#### <span class="req-id">FR-3.4.2</span> Heating Ramp <span class="badge badge-critical">CRITICAL</span>

| Parameter | Value |
|-----------|-------|
| Start temperature | 25 degrees C (ambient) |
| Ramp rate | ~2 seconds per degree C |
| Ramp complete | When `chamberTemp >= targetTemp` |

**Behavior:**
1. During ramp: gauge shows current temp, label shows "RAMP degrees C"
2. Status bar: orange "Heating" badge, "XX degrees C -> YY degrees C", "Timer starts at target"
3. Phase timer does NOT count during ramp
4. After ramp completes: label changes to "HOLD degrees C", timer starts counting

#### <span class="req-id">FR-3.4.3</span> Phase Execution <span class="badge badge-critical">CRITICAL</span>

| Phase Status | Visual |
|-------------|--------|
| **Active** | Colored border, animated gauge, countdown timer |
| **Completed** | 100% progress, "Done" status |
| **Pending** | Dashed border, 40% opacity, "Waiting..." |

**Phase card elements:**
- Badge (top): process name + icon
- Circular gauge: temperature or intensity
- Time left: countdown `MM:SS`
- Range bar: progress within range
- Status text: current action
- Bottom stats: MIN elapsed, SEC, % DONE

#### <span class="req-id">FR-3.4.4</span> Nitrogen Purge <span class="badge badge-high">HIGH</span>

| Parameter | Value |
|-----------|-------|
| Trigger | When a Nitrogen step is reached in the cure sequence |
| Condition | `nitrogenMode === true` on the system |
| Duration | Configurable, default 60 seconds |
| Pressure requirement | >= 6 bar at activation (NOT checked during process) |
| Max per program | 2 Nitrogen steps |

**Placement rules:**
1. After Nitrogen: must have a Heating, Cure, Bleacher, or Cooling step
2. Program must include a Cooling step to vent nitrogen from the chamber
3. At least one Heating, Cure, or Bleaching step must follow the N₂ purge
4. If N₂ is not enabled on the system, Nitrogen steps are automatically skipped

**Behavior:**
1. Status bar: white "N2" badge, countdown in seconds
2. TopBar N2 icon: pulsing white animation
3. Phase advancement paused until purge completes
4. On abort: nitrogen flow stops immediately

#### <span class="req-id">FR-3.4.5</span> Process Completion <span class="badge badge-high">HIGH</span>

**Completion overlay (full-screen):**
1. Green checkmark icon (56px)
2. "Cure Complete!" heading
3. Material name, total time, step count
4. "Open Door" button (only exit)
5. Button press: sends door open command, navigates to `/`

#### <span class="req-id">FR-3.4.6</span> Process Abort <span class="badge badge-critical">CRITICAL</span>

**Abort sequence:**
1. User taps "Abort" on active phase card
2. AbortModal confirmation dialog appears
3. "Yes, Abort" -> immediate shutdown of ALL hardware:
   - Heater OFF
   - UV OFF
   - Cooling OFF
   - Nitrogen OFF
   - Target temperature cleared
4. Navigate to home screen (`/`)

#### <span class="req-id">FR-3.4.7</span> Phase Card Scrolling <span class="badge badge-medium">MEDIUM</span>

1. Each card: fixed 200px width, `shrink-0`
2. Container: `overflow-x-auto` with `-webkit-overflow-scrolling: touch`
3. Scroll snap: `scroll-snap-type: x mandatory`, cards have `snap-start`
4. Supports > 4 phases via horizontal swipe

---

### 3.5 Temperature Control

#### <span class="req-id">FR-3.5.1</span> PI Controller <span class="badge badge-critical">CRITICAL</span>

| Parameter | Value |
|-----------|-------|
| Proportional gain (Kp) | 0.08 |
| Integral gain (Ki) | 0.00015 |
| Derivative gain (Kd) | 0.0 |
| Integrator max | 0.85 |
| Integrator min | 0.0 |
| Loop frequency | 20 Hz (50ms) |
| At-temperature threshold | +/- 1.5 degrees C |

**Control equation:**
```
error = target - current
integral += Ki * error  (clamped to [0, 0.85])
output = Kp * error + integral + Kd * (error - prev_error)
power = clamp(output, 0, 1)
```

#### <span class="req-id">FR-3.5.2</span> Delta-Sigma DAC <span class="badge badge-critical">CRITICAL</span>

```
delta = (last_output ? value - 1.0 : value)
sigma = accumulator + delta
output = (sigma > 0.5)
accumulator = sigma
```

- Converts 0-1 power value to binary heater ON/OFF at 20Hz
- Provides fine-grained average power control

#### <span class="req-id">FR-3.5.3</span> Fan Management <span class="badge badge-high">HIGH</span>

| Event | Fan Action |
|-------|-----------|
| Heating starts | Fan ON at 100% |
| Heating stops | Fan reduces to 60% |
| 10 min after stop | Fan OFF |

#### <span class="req-id">FR-3.5.4</span> Temperature Display <span class="badge badge-high">HIGH</span>

| Condition | Display |
|-----------|---------|
| Heater off | White text |
| Heater on < 10s | White text |
| Heater on >= 10s | Red text + red thermometer icon |
| Target active | Orange "Target: XX degrees C" below current temp |

---

### 3.6 Top Bar

#### <span class="req-id">FR-3.6.1</span> Layout <span class="badge badge-high">HIGH</span>

```
+-------+---+-------------------+---+---+---+---+---+---+
| Logo  |   | [Door] [Temp]     |   |N2 |NFC| B | S | G |
| Name  | < |  Open   24.0C     | C |   |   | e | e | l |
|       |   |       Target:80C  | l |   |   | l | t | o |
+-------+---+-------------------+---+---+---+---+---+---+
```

#### <span class="req-id">FR-3.6.2</span> Status Icons <span class="badge badge-medium">MEDIUM</span>

| Icon | Size | Behavior |
|------|------|----------|
| Clock | 24px | Reserved for future use |
| N2 (circled) | 40px | Gray=off, White=enabled, Pulsing=active flow |
| NFC (circled) | 40px | Hidden when NFC disabled in settings |
| Bell | 24px | Badge with alert count; Red=critical, Orange=warnings |
| Settings | 24px | Navigate to `/settings` |
| Globe | 24px | White=connected, Red=disconnected |

#### <span class="req-id">FR-3.6.3</span> Navigation Restrictions <span class="badge badge-high">HIGH</span>

1. Back arrow hidden on home screen (`/`)
2. Back arrow hidden during cure process (`/cure-process`)
3. Back arrow visible on all other pages

---

### 3.7 Settings

#### <span class="req-id">FR-3.7.1</span> Power Controls <span class="badge badge-high">HIGH</span>

| Action | Button | Confirmation | API Call |
|--------|--------|-------------|----------|
| Reboot | Gray "REBOOT" | `confirm()` dialog | `POST /api/system/reboot` |
| Shutdown | Red "SHUTDOWN" | `confirm()` dialog | `POST /api/system/shutdown` |

**Post-shutdown behavior:** Black screen with S-Cure logo at 40% opacity. Double-tap to wake.

#### <span class="req-id">FR-3.7.2</span> Hardware Controls <span class="badge badge-medium">MEDIUM</span>

| Control | Type | Range |
|---------|------|-------|
| Damper | OPEN/CLOSE buttons | Binary |
| LED Cooling Airflow | Touch slider | 0-100% PWM |
| Chamber Intake Fan | Touch slider | 0-100% PWM |
| Chamber Heating Fan | Touch slider + Fan Test | 0-100% PWM |
| Chamber Heating | Gradient slider + +/- | 20-80 degrees C |

#### <span class="req-id">FR-3.7.3</span> Diagnostics <span class="badge badge-medium">MEDIUM</span>

| Test | Output |
|------|--------|
| Fan Test | RPM reading + OK/FAIL |
| LED Diagnostic | 4x LED temperatures + OK/FAIL |

#### <span class="req-id">FR-3.7.4</span> Toggles <span class="badge badge-medium">MEDIUM</span>

| Toggle | Condition | Side Effect |
|--------|-----------|-------------|
| Nitrogen Mode | Requires N2 >= 6 bar | Shows "(min 6 bar)" when blocked |
| NFC | None | Hides/shows NFC icon in TopBar |
| BOFA Control | None | Controls fume extraction |

#### <span class="req-id">FR-3.7.5</span> Log Export <span class="badge badge-medium">MEDIUM</span>

**Flow:** Button press -> "Exporting..." -> mount USB -> copy `/var/log/scure` -> unmount -> "Done!" / "No USB found"

**Feedback states:** idle -> loading (bounce animation) -> success (checkmark, 3s) / error (X, 3s) -> idle

#### <span class="req-id">FR-3.7.6</span> Software Update <span class="badge badge-high">HIGH</span>

See Section 3.11.

---

### 3.8 Print History

#### <span class="req-id">FR-3.8.1</span> Print Log Schema <span class="badge badge-high">HIGH</span>

```json
{
  "id": "log-001",
  "printName": "Print #008",
  "materialName": "st45",
  "printerName": "OR200001",
  "date": "2026-03-29T10:30:00",
  "duration": 20,
  "status": "completed",
  "steps": 3,
  "csvFile": "presets/st45.csv"
}
```

#### <span class="req-id">FR-3.8.2</span> Multi-Select & Cure <span class="badge badge-medium">MEDIUM</span>

1. Checkbox per log entry (no selection limit)
2. Validation: all selected logs must share the same `materialName`
3. Mixed materials: red error "All prints must use the same material"
4. Valid selection: green "Ready to cure Nx {materialName}"
5. "Cure Together" button: stores IDs in `sessionStorage`, navigates to cure
6. After successful cure: selected logs removed from history

---

### 3.9 Network

#### <span class="req-id">FR-3.9.1</span> Status Tab <span class="badge badge-medium">MEDIUM</span>

**Displayed information:**

| Field | Source |
|-------|--------|
| IP Address | `hostname -I` via API |
| MAC | `/sys/class/net/eth0/address` |
| WireGuard IP | From interface list |
| Gateway | `ip route | grep default` |
| Connection Name | DHCP/Static identifier |
| Protocol | ethernet |

#### <span class="req-id">FR-3.9.2</span> Static IP Configuration <span class="badge badge-medium">MEDIUM</span>

| Field | Validation | Default |
|-------|-----------|---------|
| IP Address | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | Current IP |
| Gateway | Same pattern | Current gateway |
| Subnet Mask | Same pattern | 255.255.255.0 |
| DNS Server | Same pattern | 8.8.8.8 |

#### <span class="req-id">FR-3.9.3</span> Diagnostics Tab <span class="badge badge-medium">MEDIUM</span>

| Tool | Command on RPi | Timeout |
|------|---------------|---------|
| Ping | `ping -c 4 -W 3 {address}` | 15s |
| Traceroute | `traceroute -m 15 -w 3 {address}` | 15s |
| NS Lookup | `nslookup {address}` | 15s |

---

### 3.10 Alerts & Errors

> **Note for CS team:** The fields `description`, `troubleshooting`, and `supportUrl` in `/config/errors.json` are editable. All other fields (`code`, `title`, `severity`, `category`) are system-defined and must not be modified.

#### <span class="req-id">FR-3.10.1</span> Critical Errors <span class="badge badge-critical">CRITICAL</span>

| Code | Title | Category |
|------|-------|----------|
| E-101 | Laser Temperature too High | temperature |
| E-102 | Chamber Overheat | temperature |
| E-103 | System Motor Failure | mechanical |
| E-104 | Door Lock Failure | safety |
| E-105 | UV LED Failure | electrical |
| E-106 | N2 Pressure Critical | gas |
| E-107 | Power Supply Fault | electrical |
| E-108 | Communication Error | system |

#### <span class="req-id">FR-3.10.2</span> Warnings <span class="badge badge-high">HIGH</span>

| Code | Title | Category |
|------|-------|----------|
| W-301 | Filter Needs Cleaning | maintenance |
| W-302 | Fan Speed Low | mechanical |
| W-303 | N2 Pressure Low | gas |
| W-304 | High Lead On Time | maintenance |
| W-305 | Software Update Available | system |
| W-306 | Network Disconnected | network |
| W-307 | Door Sensor Misaligned | safety |

#### <span class="req-id">FR-3.10.3</span> QR Code Generation <span class="badge badge-medium">MEDIUM</span>

1. QR codes auto-generated from `supportUrl` field using `qrcode.react`
2. List view: 28x28px QR per row
3. Detail view: 80x80px QR with full URL text
4. Scanning QR opens the documentation page for that specific error

#### <span class="req-id">FR-3.10.4</span> Alert Detail View <span class="badge badge-high">HIGH</span>

**Sections:**
1. Header: icon + error code + title
2. Status badge: Critical (red) / Warning (orange)
3. Problem Description (CS-editable)
4. Troubleshooting Steps -- numbered list (CS-editable)
5. QR Code + documentation URL (CS-editable)
6. Support contacts: email, phone, live chat
7. "Dismiss Alert" button

---

### 3.11 Software Update

#### <span class="req-id">FR-3.11.1</span> Update Package Format <span class="badge badge-high">HIGH</span>

```
scure-update-1.2.0.scu
  ├── scure-update-1.2.0.tar.gz        (payload)
  │   ├── manifest.json
  │   ├── install.sh
  │   ├── frontend/                     (built React app)
  │   ├── server/                       (Python + C++ files)
  │   └── materials/presets/            (updated presets)
  └── scure-update-1.2.0.tar.gz.sig    (RSA-4096 signature)
```

#### <span class="req-id">FR-3.11.2</span> Build Process <span class="badge badge-high">HIGH</span>

```bash
# Generate signing keys (first time only)
./tools/build-update.sh --init-keys

# Build update package
./tools/build-update.sh 1.2.0
# Output: updates/scure-update-1.2.0.scu
```

#### <span class="req-id">FR-3.11.3</span> Installation Process <span class="badge badge-high">HIGH</span>

| Step | Action | Failure |
|------|--------|---------|
| 1 | Mount USB, find newest `.scu` file | "No USB / No .scu found" |
| 2 | Extract and verify RSA-4096 signature | "Verification failed" |
| 3 | Read `manifest.json` for version | Display version |
| 4 | Run `install.sh --pre` (backup) | Abort |
| 5 | Run `install.sh --post` (install) | Auto-rollback |
| 6 | Restart services | Complete |

#### <span class="req-id">FR-3.11.4</span> Update UI <span class="badge badge-medium">MEDIUM</span>

- Step-by-step progress with spinner/check/X icons
- Cancel button disabled during installation
- Success: green panel with version, auto-reload
- Failure: red panel with error, rollback confirmation, retry button

---

### 3.12 On-Screen Keyboard

#### <span class="req-id">FR-3.12.1</span> Keyboard Specification <span class="badge badge-high">HIGH</span>

| Attribute | Value |
|-----------|-------|
| Rendering | React Portal to `document.body` |
| Z-index | 99999 |
| Coverage | Full screen (fixed inset-0) |
| Layouts | QWERTY letters + Numbers/Symbols |

**Keys:**
- 10-key top row (q-p) + backspace (red)
- 9-key middle row (a-l, indented)
- Shift + 9-key bottom row (z-?) + Shift
- ?123/ABC toggle, comma, space bar, period, Done (blue)

#### <span class="req-id">FR-3.12.2</span> Dialog Integration <span class="badge badge-high">HIGH</span>

When keyboard is opened from within a Radix Dialog:
1. Dialog component returns `null` (hidden)
2. Keyboard renders via Portal (full screen)
3. On "Done": keyboard closes, Dialog re-renders with updated value

---

### 3.13 Wake/Sleep

#### <span class="req-id">FR-3.13.1</span> Shutdown Behavior <span class="badge badge-medium">MEDIUM</span>

1. After SHUTDOWN: `sessionStorage.scure-shutdown = 'true'`
2. Black screen with S-Cure logo (40% opacity)
3. First tap: "Tap again to start"
4. Second tap: clear sessionStorage, render app
5. Page reload via `window.location.reload()`

#### <span class="req-id">FR-3.13.2</span> Screen Saver <span class="badge badge-medium">MEDIUM</span>

| Parameter | Value |
|-----------|-------|
| Idle timeout | 2 minutes (120 seconds) |
| Wake method | Double-tap (same as shutdown screen) |
| Disabled during | Active cure process (`/cure-process`) |

**Behavior:**
1. After 2 minutes without touch/pointer activity, the WakeScreen overlay is displayed
2. Any touch or pointer movement resets the idle timer
3. First tap: "Tap again to start"
4. Second tap: dismiss screensaver, resume normal UI, reset idle timer
5. The screensaver SHALL NOT activate during an active cure process
6. Events tracked: `pointerdown`, `pointermove`, `touchstart`

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement | Target |
|----|------------|--------|
| NFR-4.1.1 | UI frame rate | 60fps on RPi CM5 |
| NFR-4.1.2 | Temperature control loop | 20Hz (50ms) |
| NFR-4.1.3 | Hardware state polling | Every 5 seconds |
| NFR-4.1.4 | Page transition time | < 200ms |
| NFR-4.1.5 | Production build size | < 500KB gzipped |
| NFR-4.1.6 | Initial load time | < 3 seconds |

### 4.2 Usability

| ID | Requirement |
|----|------------|
| NFR-4.2.1 | All touch targets minimum 44x44 pixels |
| NFR-4.2.2 | Viewport fixed at 800x480 with CSS scaling |
| NFR-4.2.3 | No physical keyboard dependency |
| NFR-4.2.4 | Minimum font size: 10px |
| NFR-4.2.5 | Dark theme only (black background #0a0a0a) |
| NFR-4.2.6 | Cursor hidden on touch devices (`pointer: coarse`) |
| NFR-4.2.7 | Text selection disabled globally |
| NFR-4.2.8 | GPU-accelerated scrolling (`-webkit-overflow-scrolling: touch`) |

### 4.3 Reliability

| ID | Requirement |
|----|------------|
| NFR-4.3.1 | Fully offline operation (no internet required) |
| NFR-4.3.2 | User data persists across reboots via localStorage |
| NFR-4.3.3 | Automatic rollback on update failure |
| NFR-4.3.4 | Preset materials always available (file-based) |
| NFR-4.3.5 | Door lock enforced during active cure |
| NFR-4.3.6 | Fan cooldown guaranteed for 10 min after heating |

### 4.4 Security

| ID | Requirement |
|----|------------|
| NFR-4.4.1 | Updates signed with RSA-4096 |
| NFR-4.4.2 | Signature verified before installation |
| NFR-4.4.3 | System config fields read-only |
| NFR-4.4.4 | Preset materials immutable |
| NFR-4.4.5 | Destructive actions require confirmation |
| NFR-4.4.6 | No remote code execution capability |

### 4.5 Hardware Interface

| ID | Requirement |
|----|------------|
| NFR-4.5.1 | GPIO via `/sys/class/gpio/` (sysfs) |
| NFR-4.5.2 | PWM via `/sys/class/pwm/pwmchip0/` |
| NFR-4.5.3 | Temperature via SPI thermocouple |
| NFR-4.5.4 | Architecture: React -> Flask (HTTP) -> C++ (pybind11) -> GPIO |

### 4.6 Maintainability

| ID | Requirement |
|----|------------|
| NFR-4.6.1 | Error definitions editable without code changes (`errors.json`) |
| NFR-4.6.2 | Presets addable via CSV files |
| NFR-4.6.3 | Logs exportable to USB |
| NFR-4.6.4 | Field firmware updates via USB |
| NFR-4.6.5 | Modular React component architecture |

---

## 5. Data Models

### 5.1 CureStep

```typescript
interface CureStep {
  step: number                              // Sequence number (1-based)
  process: 'Heating' | 'Drying' | 'Cure' | 'Cooling' | 'Bleacher' | 'Nitrogen'
  temperature: number | null                // 20-80 deg C (null for Nitrogen)
  intensity: number | null                  // 0-100%
  time: number                              // 1-120 minutes (0 for Cooling/Nitrogen)
  coolingMode?: 'fast' | 'medium' | 'slow'  // Cooling only
  uvIntensity?: number | null               // 5-100% (Cure/Bleacher)
  timerMode?: 'on-ramp' | 'on-target'      // When to start countdown
  uvStartMode?: 'at-start' | 'at-target'   // When UV turns on
  uvRampPercent?: number                    // 10-100%
}
```

### 5.2 Material

```typescript
interface Material {
  id: string                                // UUID
  name: string                              // Display name
  steps: CureStep[]                         // Ordered cure phases
  totalDuration: number                     // Sum of step times (minutes)
  csvContent: string                        // Raw CSV for export
  createdAt: string                         // ISO 8601 timestamp
  isPreset: boolean                         // true = factory, immutable
}
```

### 5.3 PrintLog

```typescript
interface PrintLog {
  id: string                                // UUID
  printName: string                         // e.g. "Print #008"
  materialName: string                      // Material used
  printerName: string                       // Device name (e.g. "OR200001")
  date: string                              // ISO 8601 timestamp
  duration: number                          // Total minutes
  status: 'completed' | 'aborted' | 'error'
  steps: number                             // Number of phases
  csvFile: string                           // Path to CSV
}
```

### 5.4 HardwareState

```typescript
interface HardwareState {
  chamberTemp: number                       // Current deg C
  targetTemp: number | null                 // Target deg C (null = no target)
  heatingStartTime: number | null           // ms timestamp for red indicator
  doorClosed: boolean                       // Door sensor
  isHeating: boolean                        // Heater relay
  isCooling: boolean                        // Cooling fan
  uvOn: boolean                             // UV LED
  uvIntensity: number                       // 0-100%
  nitrogenMode: boolean                     // N2 enabled
  nitrogenActive: boolean                   // N2 flowing
  nitrogenDuration: number                  // Purge seconds
  n2LinePressure: number                    // Input bar
  systemName: string                        // Editable display name
  nfcEnabled: boolean                       // NFC reader
  networkConnected: boolean                 // Browser online
  apiConnected: boolean                     // Python API reachable
}
```

### 5.5 ErrorDef

```typescript
interface ErrorDef {
  code: string                              // "E-101" or "W-301"
  title: string                             // Short description
  severity: 'critical' | 'warning'          // Determines UI treatment
  category: string                          // Grouping (temperature, safety, etc.)
  description: string                       // ** CS-EDITABLE **
  troubleshooting: string[]                 // ** CS-EDITABLE **
  supportUrl: string                        // ** CS-EDITABLE ** (used for QR)
}
```

### 5.6 SystemConfig

```typescript
interface SystemConfig {
  serialNumber: string                      // Factory (read-only)
  firmware: string                          // Factory (read-only)
  lastBoot: string                          // System (read-only)
  deviceName: string                        // Factory (read-only)
  leadOnTimeHours: number                   // System (read-only)
  model: string                             // Factory (read-only)
  hardwareRevision: string                  // Factory (read-only)
  manufacturer: string                      // Factory (read-only)
  organizationId: string                    // User-set via USB CSV
  setupComplete: boolean                    // Set after initial wizard
}
```

---

## 6. API Specification

### 6.1 Base URL

```
http://localhost:3001/api
```

### 6.2 Endpoints

#### System

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/state` | Hardware state (polled 5s) | None |
| `POST` | `/system/reboot` | Reboot RPi CM5 | Confirm |
| `POST` | `/system/shutdown` | Shutdown RPi CM5 | Confirm |
| `POST` | `/system/export-logs` | Copy logs to USB | None |
| `POST` | `/system/update` | Install .scu from USB | None |

#### Chamber

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chamber/temperature?target=60` | Set target temp, start PI loop |
| `POST` | `/chamber/stop` | Stop heating, begin fan cooldown |

#### Hardware

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/door/open` | Actuate door lock solenoid |
| `POST` | `/fans/{name}?speed=50` | Set fan PWM (led_cooling, chamber_intake, chamber_heating) |
| `POST` | `/damper/open` | Open damper |
| `POST` | `/damper/close` | Close damper |

#### Diagnostics

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/diagnostics/fan-test` | Returns `{ rpm: number, status: string }` |
| `POST` | `/diagnostics/led-test` | Returns `{ results: [{ name, temp, status }] }` |

#### Network

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/network/status` | IP, MAC, gateway, interfaces |
| `POST` | `/network/diagnostics` | Body: `{ tool, address }` |
| `POST` | `/network/static` | Body: `{ ip, gateway, subnet, dns }` |

---

## 7. System Architecture

### 7.1 Software Stack

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND                          │
│  React 19 + TypeScript + Vite + shadcn/ui           │
│  Tailwind CSS 4 + Recharts + qrcode.react           │
│                                                     │
│  Pages:  Home | Cure | Settings | Network | Alerts  │
│  State:  5 React Contexts (Hardware, Material,      │
│          PrintHistory, Alerts, SystemConfig)         │
├─────────────────────────────────────────────────────┤
│                    MIDDLEWARE                         │
│  Python 3.11 + Flask + Flask-CORS                   │
│                                                     │
│  Modules: app.py (API) | temperature_control.py     │
│           updater.py (USB updates)                   │
├─────────────────────────────────────────────────────┤
│                    DRIVER                             │
│  C++ 17 + pybind11                                  │
│                                                     │
│  hw_driver.cpp    → GPIO, PWM, SPI                  │
│  temperature_control.hpp → PI loop at 20Hz          │
├─────────────────────────────────────────────────────┤
│                    HARDWARE                          │
│  RPi CM5 | GPIO 40-pin | SPI thermocouple           │
│  Heater relay | UV LEDs | Door solenoid | N2 valve  │
│  PWM fans | Damper motor | Door sensor              │
└─────────────────────────────────────────────────────┘
```

### 7.2 File Structure

```
sCure-A/
├── docs/
│   └── SRS.md                    ← This document
├── public/
│   ├── config/
│   │   ├── system.json           (device config, read-only)
│   │   └── errors.json           (error defs, CS-editable)
│   └── materials/
│       ├── presets/               (6 factory CSV profiles)
│       └── print_history.json    (default print logs)
├── src/
│   ├── pages/          (7)       HomePage, CureProcess, Settings,
│   │                             Network, Alerts, MaterialEditor, Setup
│   ├── components/     (16+11)   PhaseCard, TopBar, OnScreenKeyboard, etc.
│   ├── context/        (5)       Hardware, Material, PrintHistory,
│   │                             Alerts, SystemConfig
│   ├── services/       (1)       hardware-api.ts
│   └── lib/            (1)       utils.ts
├── server/
│   ├── app.py                    Flask API server
│   ├── temperature_control.py    PI controller (Python)
│   ├── updater.py                USB update manager
│   └── hardware/
│       ├── hw_driver.cpp         C++ GPIO/PWM driver
│       ├── temperature_control.hpp  C++ PI controller
│       └── build.sh              Compile script
└── tools/
    └── build-update.sh           Update package builder
```

---

## 8. Traceability Matrix

| Requirement | Component(s) | Test Type |
|-------------|-------------|-----------|
| FR-3.1.1 Setup Wizard | SetupPage, SystemConfigContext | Integration |
| FR-3.2.1 Recent Prints | HomePage, PrintHistoryContext | UI |
| FR-3.3.1 CSV Builder | CsvBuilderModal, MaterialContext | UI, Unit |
| FR-3.3.2 CSV Import | ImportCsvModal, parseCsv() | Unit |
| FR-3.4.1 Process Init | CureProcessPage | Integration |
| FR-3.4.2 Heating Ramp | CureProcessPage, HardwareContext | Integration, HW |
| FR-3.4.4 N2 Purge | CureProcessPage, HardwareContext | Integration, HW |
| FR-3.4.6 Abort | AbortModal, CureProcessPage | Safety |
| FR-3.5.1 PI Controller | temperature_control.py/.hpp | Unit, HW |
| FR-3.5.2 Delta-Sigma | temperature_control.py/.hpp | Unit |
| FR-3.6.4 Alert Badge | TopBar, AlertsContext | UI |
| FR-3.7.1 Power Controls | SettingsPage, hardware-api | Integration, HW |
| FR-3.9.2 Static IP | NetworkPage, app.py | Integration |
| FR-3.10.1 Error Defs | errors.json, AlertsContext | Unit |
| FR-3.10.3 QR Codes | AlertsPage, qrcode.react | UI |
| FR-3.11.3 Update Install | UpdateModal, updater.py | Integration |
| FR-3.12.1 Keyboard | OnScreenKeyboard | UI |
| NFR-4.1.2 20Hz Loop | temperature_control | Performance |
| NFR-4.2.1 Touch Targets | All components | Accessibility |
| NFR-4.4.1 Signed Updates | build-update.sh, updater.py | Security |

---

## 9. Glossary

| Term | Definition |
|------|-----------|
| **Bleaching** | UV treatment at 450nm wavelength for whitening/brightening |
| **Chamber** | The enclosed curing cavity where materials are processed |
| **Cure (process)** | UV treatment at 405nm wavelength for hardening resin |
| **Damper** | Mechanical valve controlling airflow in/out of chamber |
| **Delta-Sigma DAC** | Modulation technique converting analog value to fast on/off switching |
| **Drying** | Heat-only phase for moisture removal before curing |
| **eMMC** | Embedded MultiMediaCard -- built-in flash storage on CM5 |
| **GPIO** | General Purpose Input/Output pins on Raspberry Pi |
| **Kiosk Mode** | Full-screen browser mode without address bar or window controls |
| **PI Controller** | Feedback control algorithm using Proportional and Integral terms |
| **pybind11** | C++ library for creating Python bindings |
| **Ramp** | Period of increasing temperature from ambient to target |
| **SCU** | Signed Cure Update -- the `.scu` package format |
| **SPI** | Serial Peripheral Interface -- used for thermocouple communication |
| **WireGuard** | Lightweight VPN protocol for secure remote access |

---

<div class="watermark">

**S-Cure Ltd.** -- Software Requirements Specification -- SRS-SCURE-2026-001 v1.0.0

*This document is confidential and proprietary. Unauthorized distribution is prohibited.*

</div>