# Thermistor vs photoresistor under UV — sCure bench experiment, 2026-09-14

Two sensors placed side by side inside the sCure chamber, read by an Arduino Uno,
while the machine's LED power was stepped 30 → 100 % in 10 % steps.

## Setup

- Arduino Uno on COM3, sketch `scripts/uv_sensors.ino` (115200 baud, CSV `ms,ntc,ldr`
  every 200 ms, each value the mean of 8 ADC samples).
- **A0 = thermistor** (10 kΩ NTC assumed, β 3950): 5 V → NTC → A0, 10 kΩ from A0 to GND.
- **A1 = photoresistor** (CdS LDR): 5 V → LDR → A1, 10 kΩ from A1 to GND.
- Counts are raw 10-bit ADC (0–1023). More light / more heat = lower sensor resistance = higher count.
- Machine: sCure test unit 192.168.154.142, app 0.8.45, real IO board, all four LED
  calibration factors 1.0, door closed. LED drive via `POST /api/uv?on=1&intensity=N&wavelength=W`.
- Ophir StarBright (fw SB1.30) + PD300RM-8W head, 450 nm run only, driven over WinUSB by
  `UV Jig/tools/starbright.py` (Ophir's COM object refuses this firmware). AUTO range, 5 Hz.

## Experiment 1 — 405 nm sweep, 60 s per step  (`405nm_sweep_2026-09-14/`)

30 s baseline (UV off) → 30…100 % @ 60 s each → UV off, 60 s tail. Chamber started at 22 °C.

| UV % | Thermistor | Photoresistor | Hottest LED zone |
|---|---|---|---|
| off | 514 | 56 | 24 °C |
| 30 | 594 | 978 | 26 °C |
| 40 | 637 | 983 | 29 °C |
| 50 | 671 | 987 | 32 °C |
| 60 | 700 | 989 | 35 °C |
| 70 | 729 | 992 | 38 °C |
| 80 | 752 | 994 | 42 °C |
| 90 | 775 | 994 | 45 °C |
| 100 | 792 | 996 | 49 °C |

(settled = mean of the last 15 s of each step)

## Experiment 2 — 450 nm sweep, 120 s per step, with Ophir  (`450nm_sweep_2026-09-14/`)

30 s baseline → 30…100 % @ 120 s each → UV off, 60 s tail. Chamber started warm (25.6 °C,
LEDs 28 °C) because it followed experiment 1 and an aborted 60 s run.

| UV % | Ophir mW/cm² | Thermistor | Photoresistor | Hottest LED zone |
|---|---|---|---|---|
| off | 0.002 | 571 | 45 | 28 °C |
| 30 | 12.03 | 589 | 944 | 29 °C |
| 40 | 15.81 | 600 | 955 | 30 °C |
| 50 | 19.05 | 614 | 961 | 32 °C |
| 60 | 22.50 | 623 | 966 | 34 °C |
| 70 | 25.53 | 634 | 970 | 36 °C |
| 80 | 28.29 | 646 | 973 | 39 °C |
| 90 | 30.70 | 659 | 975 | 42 °C |
| 100 | 32.90 | 672 | 977 | 45 °C |

Ophir vs commanded intensity: linear fit 0.299 mW/cm² per %, intercept +3.9 mW/cm², R² 0.993.
The curve bends over: mW/cm² per % falls steadily from 0.40 at 30 % to 0.33 at 100 %
(LED efficiency drop with junction temperature and/or driver compression at the top).

## Findings

- **Thermistor**: monotonic and well resolved in both runs (~10–40 counts per 10 % step) but
  never reaches a plateau inside a step, even at 120 s — it is a ramp riding on the
  previous step. It tracks the LED-zone temperatures reported by the machine, i.e. it is
  measuring radiant/convective heat from the panels, not UV.
- **Photoresistor (CdS)**: saturated at 30 % with the 10 kΩ divider (944–996 of 1023 across
  the whole range). Response is fast (<200 ms both ways). To resolve intensity, use a
  ~470 Ω–1 kΩ fixed resistor instead of 10 kΩ, or move the LDR further from the panels.
  Note CdS peaks at ~550 nm and degrades under sustained UV.
- **Ophir**: the reference. Steady to ±0.005 mW/cm² within a step; brief "over" replies for
  ~1 s at each turn-on while it auto-ranges (logged as blank samples).
- Tails after "UV off" in both runs show the door being opened (photoresistor jumps,
  thermistor cools sharply) — ignore data after that point.

## Files

- `*_sweep_*.csv` — Arduino rows at 200 ms: host_time, elapsed_s, arduino_ms, ntc_counts,
  ldr_counts, uv_intensity, phase, chamber_c, led_max_c (+ meter_mw_cm2 on the 450 run).
- `*_meter.csv` — every Ophir sample at 5 Hz with the commanded intensity.
- `*.png` — time series + settled response plots. `run_log.txt` — console log of the run.
- `scripts/` — sketch, sweep/log/plot/live-viewer scripts (also in the repo under `DVT/bench/`).
