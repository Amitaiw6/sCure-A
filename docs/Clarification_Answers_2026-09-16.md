# Answers to "Items to Clarify — Bench & Product Owner" (v2, 2026-09-10)

Answered 2026-09-16 from the legacy sCure-A repository (Python/Flask + `io_controller`), the IO-board schematic package BRD-74205 rev07 (`io_controller/IO BOARD SCURE.pdf`), the HSI sheet (`io_controller/HSI sCure (3).xlsx`), the legacy SRS (`docs/sCure_SRS.html`), the DVT catalog (`DVT/catalog`), and a live read-out of the test unit `testingcm5` (Pi CM5) over SSH on 2026-09-16.

Evidence labels used below:

- **CODE** — what the shipped legacy code does today.
- **SCHEMATIC** — BRD-74205 rev07 netlist / HSI.
- **BENCH** — measured on `testingcm5` (date given). One reference unit only, not a production carrier.
- **OPEN** — not answerable from any of the above; needs the named person.

---

## Bench items

### B1 — Door interlock

**Sensing path (SCHEMATIC).** The external door sensor enters on `J17_SSR_LED/DOOR SWITCH` pin 2. That node feeds `R125` (1 kΩ, AT1206FRE071KL) which commons the `+CONTROL` inputs of three CPC-1017N relays on `Safety.SchDoc`:

| Relay | LOAD_1 | LOAD_2 | Gates |
|---|---|---|---|
| K1 | GPIO16 | `SSR_SWITCH_450NM` → `J20_SSR_LED_450` | 450 nm SSR enable |
| K2 | GPIO20 | `SSR_SWITCH_405NM` → J17 pin 3 | 405 nm SSR enable |
| K3 | `HEATER_PWM` | `HEATER_PWM_1` → `J19_PWM_HEATER` | Heater PWM |

The CM5 never drives that node. GPIO27 is a passive tap behind `D10` (BAT54J) with `R46` (10 kΩ to EXT_3V3) as the only pull-up; the software configures the pin as input with the internal pull off (`pinctrl set 27 ip pn`). So the hardware interlock covers UV *and* heater; software only observes.

**Polarity (BENCH 2026-07-22, re-read 2026-09-16).** `pinctrl get 27` → `ip pn | hi` with the door closed. `open_level = 0` in `components.json`.

**Grace-period behaviour (CODE, `server/io_bridge.py`).**
- The status watchdog runs every `status_sec` (1 s). Door open while any output is live starts a countdown of `door_sensor.abort_after_sec` (default 10 s).
- Door closes in time → log "Door closed in time - process continues", process continues.
- Countdown expires → `door_abort()`: every output off (heater, UV, cooling, fans, N2, BOFA, damper), Err **6016**, status strip red until `POST /api/door-abort/ack` or a new process starts.
- Independently, `SystemController.set_led()` / `enable_heater()` refuse while the door is not confirmed CLOSED, and the hardware relays already removed the SSR/heater drive the moment the sensor line dropped. The DVT door test `DVT-SAF-012` requires `uv_off_time ≤ 1 s` measured on the Ophir trace — that is the hardware path, not the 10 s software grace.

**CLOSED (hardware owner, 2026-09-16).** The hardware owner closed this item. No further bench checks are requested for the door interlock.

### B2 — UV wavelength routing / GPIO17

**Schematic (SCHEMATIC).** Confirmed again by text-extracting all 13 pages of the rev07 package: no net named GPIO17 anywhere. GPIO16, GPIO20, GPIO27 all appear on multiple sheets.

**Bench (BENCH 2026-09-07).** On `testingcm5` the pin *is* connected to something: GPIO17 HIGH cuts the 12 V rail of the Door LED-driver DIM stage in every SSR combination (door DIM measured 0 V); GPIO17 LOW with only the 450 nm SSR on gives the door its full 12 V DIM. So the old assumption "HIGH = 450 nm" was inverted and Bleaching never dimmed the door.

**What the code does now (CODE, since v0.8.33/v0.8.39).** The premise in the item ("both SSRs enabled in 405 nm mode and routing is the sole selector") is outdated:

| Mode | GPIO16 (450 SSR) | GPIO20 (405 SSR) | GPIO17 | LED_SWITCH relay K4 (TCA P05→Q28→K4, `J21_LED_SWITCH` LED_OUT1/LED_OUT2) |
|---|---|---|---|---|
| 450 nm / Bleaching | 1 | 0 | 0 | 0 |
| 405 nm / Cure | 1 | 1 | 0 | 1 |
| idle / safe | 0 | 0 | 0 (parked) | 0 |

Turn-on order on every wavelength change: all LEDs off → K4 to the mode position (verified by read-back, 0.1 s settle) → GPIO17 set and read back → SSR enables → DIM PWM. GPIO17 is set to 0 in both modes and only verified; wavelength is selected by the SSR pair plus K4, and per-panel PWM decides which panel lights (only `LED_DOOR` has `450nm` in its `modes` list). Live now: `pinctrl get 17` → `op dl | lo`.

**ANSWERED (hardware owner, 2026-09-16): GPIO17 is wired to the PCA9685 (U15) `OE` pin 23.** It is not a wavelength-routing line and never was. `OE` is active-low output enable for all 16 PWM channels.

What that means, from the PCA9685 datasheet and the code's `MODE2 = 0x04` (totem-pole, `OUTNE = 00`):
- GPIO17 LOW: PWM outputs follow their registers (normal operation).
- GPIO17 HIGH: all 16 chip outputs are forced to 0, whatever the registers hold, and without any I2C traffic.

Per channel, using the code's inversion table (expected, only the door DIM has been measured):

| PCA channels | Effect of GPIO17 HIGH |
|---|---|
| 11–14 LED_BACK/DOOR/RIGHT/LEFT DIM | 0 → LEDs dark. **Matches the 2026-09-07 bench result (door DIM 0 V in every SSR combination).** |
| 6 HEATER_PWM | 0 → heater off |
| 10 4DA_BOFA_PWM | 0 → BOFA off |
| 0–5 fans, 7 LIGHT1, 8–9 MOT1/2_EN | behind inverting stages → expected full on (fans full speed, motor enables asserted; motors still stopped because TCA direction pins idle at 0/0) |

Consequences for the .NET contract:
- The "wrong-wavelength hazard" in this item does not exist. Wavelength is selected by the SSR pair GPIO16/GPIO20 plus relay K4 (table above). The legacy code already keeps GPIO17 LOW in every mode and reads it back.
- The `routing` key is misnamed. Rename it (for example a PWM output-enable, active low) rather than delete it: the read-back is still a valid check that the PWM stage is enabled.
- GPIO17 is an I2C-independent way to force heater PWM and all LED DIM to zero, which is worth considering as a stop path when the I2C bus hangs. That is a design suggestion, not current behaviour.
- The legacy HSI row `WAVELENGTH_ROUTING-GPIO17` ("HIGH=450nm, LOW=405nm") and the `components.json` comment are wrong and need correcting.

### B3 — Fan connector map and thresholds

**Physical map (SCHEMATIC `FAN.SchDoc`, all 4-pin B4B-XH: +12V, GND, TACHO_HV, PWM_HV):**

| Logical fan | Connector | PCA9685 CH | Tach GPIO (J1 pin) |
|---|---|---|---|
| FAN_HEATER | `J4_FAN_HEATER` | 0 | GPIO22 (15) |
| FAN_DOOR | `J1_FAN_DOOR` | 1 | GPIO23 (16) |
| FAN_RIGHT | `J5_FAN_RIGHT` | 2 | GPIO24 (18) |
| FAN_LEFT | `J6_FAN_LEFT` | 3 | GPIO19 (35) |
| FAN_BACK | `J9_FAN_BACK` | 4 | GPIO25 (22) |
| FAN_COOLING (chamber) | `J7_FAN_CHAMBER` | 5 | GPIO26 (37) |

PWM stages are inverting (2N7002 level shifters, `PCA_INVERTED`); tach = 2 pulses/rev, open-collector with pull-up.

**TCA6424A FAN1..6_ONOFF (P11–P16).** `FANONOFF.SchDoc` shows they drive Q20–Q25 → Q29–Q34 (FDN304P high-side +12 V switches) → `J22` (8-pin B8B-XH). They are **not** in series with the six fan connectors above; they switch six separate +12 V outputs on J22. `TCA6424A.fan_onoff()` exists but nothing calls it automatically. Whether J22 is populated/cabled on the machine: OPEN (bench).

**Thresholds (CODE, `components.json` `fan_health`, policy 2026-09-09):** while a fan is commanded ≥ 30 % duty, measured RPM is compared with the nominal table (linear interpolation between duty points); ≥ 10 % low for 60 s → warning 9051 "replace the fan"; ≥ 20 % low for 60 s → critical 9002 (all outputs stopped, no process may start, alert names the fan with measured/expected RPM). Heater pre-flight: FAN_HEATER at 100 % must exceed `min_fan_rpm` 100. LED-fan pre-flight (Err 9003, v0.8.58) blocks any UV start if an LED fan's tach reads 0.

Nominal RPM (BENCH 2026-09-09, `testingcm5`):

| Fan | 100 % | 80 % | 60 % | 50 % | 30 % |
|---|---|---|---|---|---|
| FAN_HEATER | 3530 | 2925 | — | 1870 | 915 |
| FAN_COOLING | 4790 | — | 2690 | — | 1235 |
| FAN_LEFT/RIGHT/BACK/DOOR | 3560 (Left measured; the others share it until measured) | | | | |

Known defect on the reference unit: FAN_DOOR tach reads 0 RPM since 2026-09-14 (others ≈ 3550) while the panel still warms — every `POST /api/uv` is refused on that unit until fixed.

The diagnostic API already returns raw values (`/api/state.fanRpm` per fan); per-fan nominal tables for production units are OPEN (bench).

**J22 ANSWERED (hardware owner, 2026-09-16):** nothing is connected to `J22` on the machine. FAN1..6_ONOFF (TCA P11–P16) are unused board-level outputs and play no part in fan control; the six fans are controlled only by PCA9685 PWM and monitored by their tach lines.

### B4 — BOFA

**CODE:** PCA9685 CH10 = `4DA_BOFA_PWM` (not inverted); `io_bridge.set_bofa()` writes the duty, `/api/state.bofaOn`; forced off by the door abort.

**SCHEMATIC (`Light Sensor.SchDoc`, the "4DA" block):** there is more on the board than the code uses —
- `4DA BOFA_EN` — GPIO6 (J1 pin 31) → R132 → Q18/Q19, F2-fused +24 V branch (an enable for the BOFA stage).
- `4DA BOFA_PRESENT` — Schmitt buffer U19A → GPIO18 (J1 pin 12, netlist-derived, marked "probable" in the HSI).
- `4DA ANALOG` — into the U18B op-amp stage on `LED_DRIVER.SchDoc` that produces `4DA_BOFA_PWM`.

So a presence input and an enable exist on the PCB; neither GPIO6 nor GPIO18 is in `io_controller.py`. Levels and connector semantics: OPEN (bench + BOFA unit datasheet).

### B5 — Pressure sensor and light sensors

**Pressure (BENCH 2026-09-14 + CODE since v0.8.57/0.8.59).** The HSI's Honeywell ABP2 at I2C 0x28 is **not populated** (receive-byte scan: bus 0 = 0x23, 0x45, 0x49, 0x55, 0x5d, 0x65; bus 1 = 0x48, 0x49). ADS1115 **U8** (bus 0, 0x48, the `SENSOR1_A1` placeholder) is also absent, so the legacy kPa formula is moot. The real N2 line device is an SMC ISE20-series pressure switch/sensor wired `Analog_IN → R86 (120 Ω) → ADS1115 U7 AIN3` (bus 1, 0x49). Measured: 0.52 V with no pressure, ADC full-scale (clamped) with pressure; `on_above_volts` 2.0; `set_point_mpa` 0.6 must match the value programmed on the switch. Hardware issue flagged 2026-09-14: the switch output at supply level reaches the 3.3 V ADS input through R86 alone (input clamp overdriven) — a divider/clamp on `Analog_IN` is required. **Model ANSWERED (hardware owner, 2026-09-16): SMC ISE20A-T-01.** Decoded from SMC catalog CAT.ES100-114:

| Code | Meaning |
|---|---|
| ISE20A | 3-screen digital pressure switch, positive pressure, rated −0.100 to 1.000 MPa, IP40, 12–24 VDC, ≤ 35 mA |
| T | **PNP open collector 2 outputs + analog voltage output 1–5 V** (output impedance ≈ 1 kΩ, accuracy ±2.5 % F.S.) |
| (blank) | units selection function |
| 01 | R1/8 port |
| (blank) | no lead wire (5-core cable ZS-46-5L ordered separately) |

Lead colours for -T: Brown DC+, Blue DC−, Black OUT1 (PNP), White OUT2 (PNP), **Gray analog output**.

The code's `pressure_sensor.mode = analog_voltage` with 1–5 V = −0.1…1.0 MPa matches this model: 0 MPa = 1.364 V, 0.6 MPa (6 bar) = 3.545 V.

The 2026-09-14 bench reading does **not** fit the gray lead. A powered 1–5 V output can never read 0.52 V (minimum 1 V), and its 5 V maximum through ≈1 kΩ cannot drive the ADC into hard overload. The behaviour seen, about 0.5 V without pressure and ADC clamped with pressure, fits a **PNP switch output (black or white lead)**, which swings to supply minus ≤ 1 V, i.e. 11–23 V into a 3.3 V ADC through R86 (120 Ω). That is the overdrive flagged on 2026-09-14.

Consequences:
- If a PNP output is on `Analog_IN`: the software must run `mode: switch`, and a divider/clamp is mandatory to protect U7.
- If the gray lead is moved to `Analog_IN`: `analog_voltage` is right, but without a 2:1 divider the input saturates above ≈ 3.2 V (≈ 0.5 MPa), so the 6 bar guard can never read a value. Fit the divider and set `divider: 2.0`.

**Still OPEN (bench):** which lead colour is actually on `Analog_IN`, and whether the switch was powered during the 0.52 V reading.

**Light sensors.** U10 (bus 1, 0x48) *is* present on the bus, but no photo-sensor front end for AIN0/AIN1 exists in rev07 (`Light Sensor.SchDoc` actually holds the NFC level shifters, servo, heater PWM, 4DA/BOFA and the SSR/door switch). AIN2/AIN3 are `J14_ANALOG_IN` with 2:1 dividers. Nothing in the product uses `LIGHT1/LIGHT2`. v1 or later: product decision (OPEN, PO).

### B6 — NFC reader

**The reader actually used is not on the board's NFC header.** BENCH 2026-09-14: an Eccel **Pepper C2** on USB (STM32 VCP 0483:5740 → `/dev/ttyACM0`, binary protocol at 115200, firmware 1.14, tag UID read successfully). CODE: `server/app.py` detects it by USB identity (Err `NFC_READER_NOT_DETECTED` when absent), `DVT/bench/nfc_monitor.py` reads tags. Quirk: the C2 only services USB CDC RX after a `SET_LINE_CODING`, so every open sets 9600 then 115200.

The board's own path — `J15_UART_NFC` with SPI level shifters U11/U13/U21, `NFC_CS` GPIO4, `NFC_INT` GPIO7, `NFC_RESET` TCA P01 (10 ms active-low pulse, idle HIGH) — is unused apart from the reset pulse.

**ANSWERED (hardware owner, 2026-09-16): the NFC reader is connected to the system over USB.** v1 NFC scope is therefore the USB Pepper C2 (USB CDC, Eccel binary protocol). The J15 SPI path and the TCA `NFC_RESET` pulse are out of scope: the reset line goes to the unused J15 header, not to the USB reader.

### B7 — CM5 carrier, rails, BOM

**Reference unit (BENCH 2026-09-16):** `Raspberry Pi Compute Module 5 Rev 1.0`, revision code `c04180` (4 GB, wireless variant — `wlan0` exists), eMMC `BJTD4R` (Samsung, manfid 0x15) 29.1 GiB. OS: Raspberry Pi OS / Debian 13 (trixie) standard image — **not** `origin.img`.

**IO board (SCHEMATIC):** PCBA "IO BOARD SCURE" BRD-74205 rev07, 40-pin header `J1` (3020-40-0100-00) to the CM5 carrier; rails +24V, +12V (`12V_IN` connector 1862042), +5V_EXT, EXT_3V3 (LM25149 buck IC1). The CM5 carrier board itself is not identified anywhere in the repo — OPEN (David/Roman).

**config.txt on the reference unit:** `dtparam=i2c_arm=on`, `dtparam=i2c0=on`, `dtparam=spi=off`, `dtoverlay=vc4-kms-v3d`, `dtoverlay=vc4-kms-dsi-ili9881-7inch`, `dtoverlay=dwc2,dr_mode=host` under `[cm5]`. Both I2C buses enabled — see B11.

**"Origin" naming:** the legacy SRS §2 defines *Printer (Origin)* as the Stratasys Origin printer that feeds the sCure Box, so `origin-device`/`origin-rpi5` is consistent with that product family. Whether the image is David/Roman's internal base or an upstream reference: OPEN (ask them).

### B8 — Primary storage medium

**Legacy paths are documentation only.** `/etc/scure/config.json` and `/mnt/ssd2/scure/config_backup.json` appear in the SRS and nowhere in the code; on the reference unit `/etc/scure` does not exist and `/mnt` is empty.

**What the legacy code actually persists (CODE):**
- `server/data/*.json` — component counters, cure/print history fallbacks, user materials, NFC setting, LED calibration, `cloud.json` (absent on the reference unit).
- PostgreSQL (`server/db`, `schema.sql`) — prints, materials, cure runs, reports (503 without a database).
- Browser `localStorage` — `organizationId` + `setupComplete` (`scure-org`), device name (`scure-system-name`), cure-history mirror.
- Serial number — static `public/config/system.json` (`"cure45223"`, a placeholder).

**Physical medium on the reference unit (BENCH):** CM5 on-board eMMC `mmcblk0` (512 MiB FAT `/boot/firmware` + 28.6 GiB ext4 `/`), no second storage device. The `appliance/` design (2026-08-25: dm-verity A/B root, LUKS `/data`, RAUC) is designed, not built. What the production unit carries: OPEN.

### B9 — OTA mechanism and bundled services

**Legacy update path (CODE, `server/updater.py`):** USB only. A `.scu` file (outer tar containing `<payload>.tar.gz` + `.sig`) is verified with `openssl dgst -sha256 -verify keys/scure-update.pub` (RSA public key in the repo), extracted, then `install.sh --pre` / `--post`, with `install.sh --rollback` on failure. Endpoints: `GET /api/system/update/manifest` (version + SHA-256 for a UI-side integrity check), `GET /api/system/update/package`, `POST /api/system/update`; errors 9081 (no USB) / 9087 (no `.scu`). **There is no GCP-bucket code in this repository.**

**Reference unit (BENCH 2026-09-16):** no SWUpdate, no RAUC, no `motion`; `dwc2` is in host mode, not `g_ether`. **`netbird.service` is installed, enabled and running on `testingcm5` too** (`/usr/bin/netbird`), alongside `wayvnc` — who installed it and for what: OPEN (ask David/Roman; likely developer remote access).

**Alignment point:** `appliance/` chose RAUC + `tryboot` for A/B; `origin.img` ships SWUpdate + `rpi-ab-slot-mapper`. One of the two must win before Epic 7 — see PO-9.

### B10 — Touchscreen and USB

**Reference unit (BENCH 2026-09-16):** Raspberry Pi **Touch Display 2, 7"** on DSI-2 (overlay `vc4-kms-dsi-ili9881-7inch`, native 720×1280, cmdline `video=DSI-2:800x1280@60,rotate=270`), Goodix **GT911** touch at I2C0 0x5d plus the panel regulator at 0x45 — i.e. the touch panel shares `i2c-0` with the IO board (TCA 0x23, ADS U6 0x49, PCA 0x55). Kiosk: lightdm + Chromium kiosk, `wayvnc` for remote view.

**Divergence to resolve:** the C# port (`sCureBox-CS`) targets the **10.1" Touch Display 2** (`vc4-kms-dsi-ili79600-10-1inch, rotation=90`), which needs its own panel power. Which panel is production: OPEN (PO).

**USB (BENCH):** 5 root hubs (dwc2 + 2× xHCI USB2 + 2× USB3), a QinHeng 1a86:8091 4-port hub on bus 4 (carrier side), no devices attached at read-out. USB consumers in the code: Ophir StarBright and Pico TC-08 (DVT only), Eccel NFC reader, and a USB stick for updates/CSV/report export (`find_usb_mount`: any `/dev/sd*` mounted under `/media` or `/run/media`, then `/media/usb`, `/media/pi`, `/mnt/usb`, last resort `mount /dev/sda1|sdb1`).

### B11 — I2C bus numbering

**Confirmed on the reference unit (BENCH 2026-09-14/16):**

| Linux bus | Header pins | Devices |
|---|---|---|
| `i2c-0` (GPIO0/1, pins 27/28, needs `dtparam=i2c0=on`) | 27/28 | TCA6424A 0x23, ADS1115 U6 0x49, PCA9685 0x55, touch 0x45/0x5d, 0x65 (unidentified) |
| `i2c-1` (GPIO2/3, pins 3/5, needs `dtparam=i2c_arm=on`) | 3/5 | ADS1115 U10 0x48, ADS1115 U7 0x49 (chamber thermistor NTC7 on AIN2, N2 pressure on AIN3) |

The heater safety gate reads `TEMP_CHAMBER` = U7 AIN2 on `i2c-1`, so the item's escalation is correct: an image without `i2c_arm=on` **and** `i2c0=on` disables both the sensor gate and every actuator. Note also `i2c-11/13/14` exist (RP1 internal / DSI), and the io_controller stack assumes a single owner per bus — a second process on `/dev/i2c-1` produced wrong-channel ADS samples on this unit.

### B12 — Damper servo

**Model ANSWERED (hardware owner, 2026-09-16): MG90S** — `components.json` is right, the HSI's "SG90" is wrong. **CODE/SCHEMATIC:** MG90S on GPIO8 (J1 pin 24) → R91/Q16 inverting stage → `J2_MOTOR_DAMPER` (3-pin PH). Pulses 0.5–2.4 ms, `signal_inverted = true`, driver = RP1 PIO helper (`server/hardware/pio_servo`, hardware-timed, v0.8.2) with lgpio fallback, `settle_sec` 1.5. Cooling uses `damper_open_angle 0` / `damper_closed_angle 90`. `pinctrl get 8` → `PIO8`. No read-back exists (agreed: never a safety precondition).

**CLOSED (hardware owner, 2026-09-16).** The answer is confirmed as complete. No further bench checks are requested for the damper servo.

### B13 — Motor 1 / Motor 2

**SCHEMATIC (`Motor_analog_input.SchDoc`):** L298N U9. OUT1/OUT2 → `J12_PWM_SERVO` pins 1/2 (misnamed; pins 5/6 carry `SENSOR1_ANALOG1/2`), OUT3/OUT4 → `J13_DAMBER_EXHAUST` pins 1/2 (pins 4/6 carry `SENSOR2_ANALOG1/2`). Direction: TCA P24/P25 (M1), P21/P22 (M2); enable/speed: PCA CH8/CH9. Feedback ADC U8 is **not present** on the reference unit's bus.

**CODE:** `TCA6424A.motor()` and `all_safe()` (stop both at startup) exist; nothing in `server/` ever drives a motor. **v1 does not use them.** What is cabled to J12/J13 on the machine: OPEN (bench).

### B14 — Wi-Fi

**BENCH 2026-09-16:** the reference CM5 is the wireless variant — `wlan0` (brcmfmac, MAC 2c:cf:67:df:88:15) is up and "connected" under NetworkManager, Bluetooth service running. **CODE:** the product uses `eth0` only (network status, static IP via `nmcli` on eth0, `NetworkPage`); the SRS has no Wi-Fi requirement. So: present on the test hardware, unused by the software, disabled by `origin.img`. Product decision: OPEN (PO).

---

## Product Owner items

### PO-1 — Evidence levels
Not decided anywhere in the repo. What exists: the DVT catalog assigns methods per test and the standing rule that shutdown proofs are taken on physical outputs (heater-body thermocouple, Ophir irradiance trace), i.e. the DVT program already treats door, UV, heater, thermistor, fans, cooling, nitrogen and damper as bench-only. Simulation (`hwSource: simulation`) is used for UI/QA only. The assignment itself is the PO's call.

### PO-2 — Serial number provisioning
SRS §3 requires a cloud-assigned SN (up to 5 attempts, setup blocked until saved, persisted to Storage and backed up to SD). **CODE:** nothing of this exists — the SN is the static placeholder in `public/config/system.json`. The `appliance/` design (Serial Service, `SC000001…`, signed offline range tokens) is designed, unbuilt. Decision: OPEN (PO).

### PO-3 — SD/backup write failure
SRS OI-6 is still open; no backup-storage code exists at all. Decision: OPEN (PO).

### PO-4 — Device-name validation
SRS §4: default "S-Cure" (OI-7), only "non-empty" is specified (OI-8). **CODE:** `SetupPage` trims and requires non-empty, on-screen keyboard, no maximum length, no character-set rule, no uniqueness; stored client-side in `localStorage` (`scure-system-name`, default "sCure"); `system.json` ships `deviceName "OR200001"`. Story 2.1's "1–64 printable, no default" is stricter than both SRS and code — needs the PO.

### PO-5 — Timer-start / UV-start
The SRS is internally inconsistent and the code disagrees with part of it:
- SRS §6.7 defines `TimerMode` (`on-ramp` | `on-target`, default on-target) and `UVStart` (`at-start` | `at-target`, default at-target).
- OI-16: the runtime never branched on them — `CureProcessPage` always ramps first, then starts the countdown ("Timer starts at target"). This is still true in the code.
- OI-17 says Time/TimerMode/UVStart were removed from the recipe model — but the current code still carries them (`StepCard`, `StepModal`, `CsvBuilderModal`, `MaterialContext` CSV header `Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,…`), and `program-estimate.ts` only uses `on-ramp` to avoid adding the ramp to the estimate.

So the honest legacy characterization for the fixtures is: *fields captured and validated, runtime always on-target/at-target*. The intended behaviour is OPEN (PO/QA).

### PO-6 — Release-readiness criteria
Nothing in the repo. The DVT plan (`DVT_Verification_Plan_SRS_RevB`) has per-test pass criteria, no alpha/beta/customer-site thresholds. OPEN (PO).

### PO-7 — Dependency-license approval
Nothing in the repo. OPEN (PO).

### PO-8 — Organization Link
**CODE:** the CSV is read as text and matched with `/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i` — first match wins, case-insensitive, no RFC 4122 version/variant check, no case normalization, stored as matched in `localStorage` (`scure-org`). No CSV schema exists (SRS OI-10). The organization is never sent to the cloud (SRS OI-11): the cloud sync snapshot contains machine name, state, counters, programs, prints and cures — not `organizationId`. Error 5001 `ORG_ID_NOT_FOUND`. Everything beyond that is OPEN (PO).

### PO-9 — Update delivery (C1–C7)
From the legacy code only:
- **C1** file-level: a `.scu` payload tarball applied by `install.sh` into `/opt/scure`.
- **C2** rollback = `install.sh --rollback` (script-level), no A/B partitions.
- **C3** trust root = the RSA public key `keys/scure-update.pub` shipped in the repo; verified with `openssl dgst -sha256` against `/opt/scure/keys/scure-update.pub` (falling back to the repo copy). **Security finding, unrelated to the question but found while answering it:** the matching *private* key `keys/scure-update.key` is committed to this repository (`git ls-files` lists it, and no ignore rule covers it). Anyone with repo access can sign a package this signature check will accept. If this key is the one used for real update packages it must be rotated and the old one revoked, not merely deleted from the tree.
- **C4** trigger = a technician/operator: USB stick + "Update Software" in Settings. No device polling, no push.
- **C5** no device identity for updates. The cloud agent uses a per-machine `X-Machine-Key` from `cloud.json`, outbound-only.
- **C6, C7** OPEN (PO / customer).

The `appliance/` design (RAUC A/B, signed bundles) and `origin.img` (SWUpdate A/B) are two further, incompatible candidates. Which one is "the customer's existing infrastructure" is exactly the question to put to David/Roman.

### PO-10 — Multi-material cure-together
SRS §6.4: Cure Together is allowed for one print or several prints of the **same material** (name equality); different materials are blocked with "Cannot cure different materials together!". **CODE** implements exactly that rule (`HomePage` / `PrintHistoryModal`). OI-15 (positions/trays beyond name equality) is the open business rule. OPEN (PM).

### PO-11 — CI/CD
No `.github/workflows` and no `.gitlab-ci.yml` in this repo. Test tooling that exists: `qa-tool/index.html` (browser QA), `DVT/tests` (pytest), and `qa/run-all.ps1` in the C# repo. Runner choice still undecided.

### PO-12 — Cloud inbound writes
**CODE:** the legacy cloud agent is outbound-only by design (docstring: "There is deliberately no command that actuates hardware… Outbound-only: no inbound ports needed"). It POSTs a snapshot to `<url>/api/agent/sync` every ~10 s with `X-Machine-Key`, and applies a small set of portal commands returned in the response (`upsert_program`, simulated `send_print`), acking their ids on the next sync. The agent is off unless `server/data/cloud.json` has `url` + `key` (absent on the reference unit). SRS OI-9/OI-11/OI-20(c) remain open. Customer confirmation: OPEN (PO).

---

## Still open — who can close it

| # | Question | Who |
|---|---|---|
| B2 | ~~What GPIO17 is wired to~~ answered: PCA9685 OE. Confirm the full-output effect of GPIO17 HIGH on fans/heater on the bench | Bench |
| B3 | ~~J22~~ answered: not connected. Per-fan nominal tables on production units | Bench |
| B4 | BOFA model / control-connector spec; levels on BOFA_EN / BOFA_PRESENT | Bench + BOFA datasheet |
| B5 | ~~Model~~ answered: ISE20A-T-01. Which lead colour is on Analog_IN; divider fitted or not; light sensors in scope? | Bench / PO |
| B6 | ~~USB or J15~~ answered: USB | — |
| B7 | Carrier board identity and BOM; is "Origin" internal or upstream | David/Roman |
| B8 | Production storage medium | David/Roman |
| B9 | Who installed NetBird (also on the test unit); SWUpdate vs RAUC vs .scu | David/Roman |
| B10 | 7" vs 10.1" Touch Display 2 for production | PO |
| B13 | What is cabled to J12/J13 | Bench |
| B14 | Wi-Fi in or out of v1 | PO |
| PO-1..12 | As listed above | PO / customer |
