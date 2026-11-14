"""Process figures — one schematic of the sCure machine and its bench, with the
parts a test touches highlighted, per test and per procedure step.

    figure_svg(test_id, step=None) -> str      SVG for the wizard (QSvgWidget)
    figure_caption(test_id) -> str             one-line caption (translated)
    export_all(catalog, out_dir)               <test>.svg + <test>_step<n>.svg for the docs

The drawing is generated, not hand-drawn: every test declares which elements
are involved and in what state, so all 31 figures share one machine, one
legend and one visual language, and a new test gets a figure by adding a
spec below (the pytest suite refuses a catalog test without one).

Top view of the chamber: LED panels on the left, right and back walls and on
the door (front, bottom of the picture), each with its thermistor and its
cooling fan; the heater in the floor with the control NTC on one end and the
type-K thermocouple bond (TC-08) on the other, the thermal cutout beside it;
the circulation fan above the heater; the intake fan and damper in the
corner. The mains chain on the right: inlet, 15 A inlet fuse, voltage
selector, 5 A heater branch fuse, heater SSR, LED SSR and drivers, PSU and
the CM5 controller with its heartbeat. Instruments sit on the bench row at
the bottom, wired to the point they measure.

The figure is an engineering drawing and stays in ENGLISH in every console
language: component tags (F fuse, K SSR, E heater, M fan, RT thermistor, TC
thermocouple, SV solenoid valve, QE gas probe, B sensor, Y actuator, H LED
panel, A electronics), a header and an ISO 7200-style title block with the
test, step, catalog revision, date and legend.

Element states:  focus   what the step is about (orange)
                 on      energised / active (warm fill)
                 off     de-energised (grey)
                 fault   the injected fault (red, crossed)
                 instr   an instrument in use (blue)
                 ok      restored / verified (green)
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path


# ---------------------------------------------------------------- palette (theme.py values, kept Qt-free here)
INK, MUTED, LINE, PAPER, CARD = "#1b2430", "#6b7a8c", "#d9dee6", "#eef1f5", "#ffffff"
ACCENT, OK, WARN, BAD, INFO, PURPLE = "#e8461f", "#1f9d61", "#d68a0c", "#d62839", "#2f6fdb", "#7c5cbf"
HOT, HOT_FILL, UV, UV_FILL = "#e8760c", "#ffd9c2", "#7c5cbf", "#e6ddf7"

STATE_STROKE = {"focus": ACCENT, "on": HOT, "off": MUTED, "fault": BAD, "instr": INFO, "ok": OK, None: INK}
STATE_FILL = {"focus": "#ffe3d9", "on": HOT_FILL, "off": "#e6e9ee", "fault": "#ffd6da", "instr": "#dbe7fb", "ok": "#d9f2e5", None: CARD}

DW, DH = 660, 396                 # drawing area (element coordinates live here)
HEAD, TB = 26, 62                 # header strip / title block heights
W, H = DW, HEAD + DH + TB         # full sheet
FONT = "Arial, Helvetica, sans-serif"
MONO = "Consolas, 'Courier New', monospace"

# component tags (engineering reference designators) — shown on the drawing
TAGS = {
    "inlet": "X1", "fuse_inlet": "F1", "selector": "S1", "fuse_heater": "F2", "ssr_heater": "K1", "ssr_led": "K2", "drivers": "A2",
    "psu": "G1", "controller": "A1", "heartbeat": "WD", "pe": "PE", "heater": "E1", "cutout": "F3", "ntc_heater": "RT1",
    "chamber_sensor": "RT2", "th_left": "RT3", "th_right": "RT4", "th_back": "RT5", "th_door": "RT6", "tc_heater": "TC1",
    "ref_tc": "TC2", "fan_circ": "M1", "fan_intake": "M2", "fan_led_left": "M3", "fan_led_right": "M4", "fan_led_back": "M5",
    "fan_led_door": "M6", "bofa": "M7", "damper": "Y1", "door_lock": "Y2", "door_sensor": "B1", "n2_valve": "SV1", "n2_nozzle": "N1",
    "led_left": "H1", "led_right": "H2", "led_back": "H3", "led_door": "H4", "ui": "HMI", "o2_center": "QE1", "o2_corner": "QE2",
    "ophir_head": "UV1", "current_probe": "CT1", "resistor_10k": "R1", "magnet": "MG1", "grid": "TC3-18", "build_head": "BH", "nfc_reader": "B2",
}
LED_POS = ("left", "right", "back", "door")

# ---------------------------------------------------------------- elements
E: dict[str, dict] = {}


def _el(eid, kind, label, group="machine", **g):
    E[eid] = dict(kind=kind, label=label, group=group, **g)


_el("enclosure", "box", "Enclosure", x=30, y=30, w=400, h=310, rx=8)
_el("chamber", "box", "Chamber", x=70, y=60, w=300, h=230, rx=4)
_el("led_back", "panel", "Back LED panel", x=110, y=62, w=210, h=10)
_el("led_left", "panel", "Left LED panel", x=72, y=100, w=10, h=150)
_el("led_right", "panel", "Right LED panel", x=358, y=100, w=10, h=150)
_el("led_door", "panel", "Door LED panel", x=120, y=278, w=200, h=10)
_el("th_back", "dot", "Back thermistor", cx=215, cy=67)
_el("th_left", "dot", "Left thermistor", cx=77, cy=175)
_el("th_right", "dot", "Right thermistor", cx=363, cy=175)
_el("th_door", "dot", "Door thermistor", cx=220, cy=283)
_el("fan_led_back", "fan", "Back LED fan", cx=215, cy=44, r=9)
_el("fan_led_left", "fan", "Left LED fan", cx=52, cy=175, r=9)
_el("fan_led_right", "fan", "Right LED fan", cx=388, cy=175, r=9)
_el("fan_led_door", "fan", "Door LED fan", cx=300, cy=312, r=9)
_el("door", "door", "Door", x1=100, y1=290, x2=340, y2=290)
_el("door_sensor", "smallbox", "Door sensor", x=342, y=284, w=16, h=12)
_el("door_lock", "smallbox", "Door lock", x=82, y=284, w=16, h=12)
_el("heater", "heater", "Heater", x=140, y=190, w=160, h=36)
_el("tc_heater", "dot", "TC-08 bond", cx=300, cy=208, r=5)
_el("ntc_heater", "dot", "Control NTC", cx=140, cy=208, r=5)
_el("cutout", "smallbox", "Thermal cutout", x=210, y=230, w=20, h=10)
_el("fan_circ", "fan", "Circulation fan", cx=220, cy=150, r=12)
_el("chamber_sensor", "dot", "Chamber sensor", cx=220, cy=100)
_el("grid", "grid", "16-channel grid")
_el("ref_tc", "dot", "Reference thermocouple", cx=250, cy=110, r=4)
_el("fan_intake", "fan", "Intake fan", cx=52, cy=300, r=10)
_el("damper", "smallbox", "Damper", x=70, y=300, w=30, h=8)
_el("vents", "vents", "Seams and vents")
_el("ui", "smallbox", "UI", x=150, y=318, w=50, h=16)
# nitrogen purge (DVT-GAS-007)
_el("n2_valve", "smallbox", "N2 valve", x=34, y=232, w=24, h=12)
_el("n2_nozzle", "dot", "N2 nozzle", cx=76, cy=238, r=4)
_el("bofa", "smallbox", "Extraction (BOFA)", x=392, y=44, w=26, h=12)
_el("ophir_head_c", "smallbox", "UV head (centre)", x=204, y=160, w=32, h=12, group="instrument")
# build head + NFC reader (DVT-NFC-001)
_el("build_head", "smallbox", "Build head (NFC tag)", x=196, y=118, w=48, h=14)
_el("nfc_reader", "smallbox", "NFC reader", x=204, y=134, w=32, h=8)
# electrical chain
_el("inlet", "plug", "Mains inlet", cx=470, cy=60, group="electrical")
_el("fuse_inlet", "fuse", "Inlet fuse 15 A", x=506, y=52, w=36, h=16, group="electrical")
_el("selector", "selector", "Voltage selector", x=572, y=42, w=64, h=36, group="electrical")
_el("fuse_heater", "fuse", "Heater fuse 5 A", x=506, y=110, w=36, h=16, group="electrical")
_el("ssr_heater", "box", "Heater SSR", x=572, y=102, w=64, h=30, rx=3, group="electrical")
_el("ssr_led", "box", "LED SSR", x=572, y=160, w=64, h=30, rx=3, group="electrical")
_el("drivers", "box", "LED drivers x4", x=496, y=156, w=60, h=38, rx=3, group="electrical")
_el("psu", "box", "PSU 12 V", x=496, y=218, w=60, h=28, rx=3, group="electrical")
_el("controller", "box", "Controller (CM5)", x=572, y=212, w=64, h=42, rx=3, group="electrical")
_el("heartbeat", "dot", "Heartbeat", cx=624, cy=246, r=4, group="electrical")
_el("pe", "earth", "Protective earth", cx=470, cy=300, group="electrical")
_el("wire_heater", "wire", "Heater branch", pts=[(572, 117), (430, 117), (430, 208), (300, 208)], group="electrical")
_el("wire_led", "wire", "LED supply", pts=[(572, 175), (430, 175), (368, 175)], group="electrical")
_el("wire_ctrl", "wire", "Control supply", pts=[(572, 233), (430, 233)], group="electrical")
# instruments (drawn only when a spec lists them)
_el("tc08", "instrument", "PicoLog TC-08", x=40, y=348, w=74, h=24, to=(300, 208), group="instrument")
_el("ophir", "instrument", "Ophir StarBright", x=124, y=348, w=80, h=24, to=(220, 298), group="instrument")
_el("ophir_head", "smallbox", "UV head", x=204, y=294, w=32, h=12, group="instrument")
_el("thermal_cam", "instrument", "Thermal camera", x=214, y=348, w=80, h=24, to=(300, 340), group="instrument")
_el("operator", "person", "Operator", cx=254, cy=358, group="instrument")
_el("uv_meter", "instrument", "UV radiometer", x=304, y=348, w=80, h=24, to=(340, 290), group="instrument")
_el("dmm", "instrument", "DMM / clamp", x=304, y=348, w=80, h=24, to=(496, 175), group="instrument")
_el("logger", "instrument", "Data / shock logger", x=304, y=348, w=100, h=24, to=(230, 175), group="instrument")
_el("ac_source", "instrument", "AC source", x=450, y=348, w=74, h=24, to=(470, 72), group="instrument")
_el("earth_tester", "instrument", "Earth bond tester", x=450, y=348, w=90, h=24, to=(470, 300), group="instrument")
_el("megger", "instrument", "Insulation tester", x=450, y=348, w=90, h=24, to=(470, 72), group="instrument")
_el("hipot", "instrument", "Hipot tester", x=450, y=348, w=80, h=24, to=(470, 72), group="instrument")
_el("touch_meter", "instrument", "Touch-current meter", x=450, y=348, w=100, h=24, to=(470, 300), group="instrument")
_el("power_analyzer", "instrument", "Power analyzer", x=540, y=348, w=90, h=24, to=(490, 60), group="instrument")
_el("scope", "instrument", "Scope + probe", x=540, y=348, w=90, h=24, to=(470, 117), group="instrument")
_el("current_probe", "ring", "Current probe", cx=470, cy=117, r=8, group="instrument")
_el("n2_supply", "instrument", "N2 regulator + flow meter", x=40, y=348, w=110, h=24, to=(46, 244), group="instrument")
_el("o2_center", "dot", "O2 probe (centre)", cx=252, cy=176, r=4, group="instrument")
_el("o2_corner", "dot", "O2 probe (corner)", cx=345, cy=265, r=4, group="instrument")
_el("o2_analyser", "instrument", "O2 analyser", x=304, y=348, w=80, h=24, to=(252, 176), group="instrument")
_el("ophir_usb", "instrument", "StarBright on the machine USB", x=450, y=348, w=130, h=24, to=(604, 254), group="instrument")
_el("resistor_10k", "smallbox", "10 kOhm resistor", x=118, y=214, w=22, h=10, group="instrument")
_el("magnet", "smallbox", "Hand magnet", x=356, y=302, w=18, h=10, group="instrument")
_el("short", "short", "Short circuit", cx=490, cy=60, group="instrument")
_el("crate", "box", "Crate", x=18, y=18, w=424, h=334, rx=10, dash=True, group="instrument")
_el("truck", "instrument", "Truck", x=450, y=348, w=60, h=24, to=None, group="instrument")
_el("registry", "instrument", "Error registry", x=450, y=348, w=90, h=24, to=(372, 324), group="instrument")
_el("log", "instrument", "Machine log", x=540, y=348, w=80, h=24, to=(604, 254), group="instrument")

# ---------------------------------------------------------------- figure specs
F: dict[str, dict] = {}


def m(*bases, **kw):
    """Merge base state dicts, later ones and the keywords overriding."""
    out = {}
    for b in bases: out.update(b)
    out.update(kw); return out


def fig(caption: str, el: dict, steps: dict | None = None, selector: str = "230", mains: str = "230 V", **extra):
    return dict(caption=caption, el=el, steps=steps or {}, selector=selector, mains=mains, **extra)


HEAT_ON = dict(inlet="on", fuse_inlet="on", selector="on", fuse_heater="on", ssr_heater="on", wire_heater="on", heater="on", fan_circ="on")
UV_ON = dict(inlet="on", ssr_led="on", drivers="on", wire_led="on", led_left="on", led_right="on", led_back="on", led_door="on",
             fan_led_left="on", fan_led_right="on", fan_led_back="on", fan_led_door="on")
TC = dict(tc_heater="instr", tc08="instr")
TRACE_TURN = dict(tc_heater="focus", tc08="focus", ssr_heater="off", heater="off", wire_heater="off")

F["DVT-SAF-018"] = fig(
    "230 V mains into the 110 V selector position — the 5 A heater branch fuse must open first, and nothing else",
    {**HEAT_ON, "selector": "fault", "fuse_inlet": "focus", "fuse_heater": "focus", "ac_source": "instr", "current_probe": "instr", "scope": "instr", "thermal_cam": "instr"},
    {0: dict(fuse_inlet="focus", fuse_heater="focus", selector="fault", heater=None, ssr_heater=None, wire_heater=None, inlet=None),
     1: dict(current_probe="focus", scope="focus", heater=None, ssr_heater=None, wire_heater=None, inlet=None),
     2: dict(ac_source="focus", inlet="on", current_probe="focus", heater=None, ssr_heater=None, wire_heater=None),
     3: dict(ui="focus", heater="on"),
     4: dict(fuse_heater="fault", heater="off", wire_heater="off", ssr_heater="off", thermal_cam="focus"),
     5: dict(inlet="off", heater="off", wire_heater="off", ssr_heater="off", fuse_heater="fault", enclosure="focus"),
     6: dict(inlet="off", heater="off", fuse_heater="fault"),
     7: dict(fuse_heater="ok", selector="ok", heater="on")},
    selector="110", mains="230 V")

F["DVT-SAF-019"] = fig(
    "A dead short across the mains inlet — the 15 A inlet fuse interrupts it; inlet, filter and earth survive",
    {"inlet": "focus", "short": "fault", "fuse_inlet": "focus", "pe": "instr", "ac_source": "instr", "current_probe": "instr", "scope": "instr"},
    {0: dict(ac_source="focus", pe="focus", short=None), 1: dict(inlet="on", short=None, controller="on", ui="on"),
     2: dict(short="fault", fuse_inlet="fault", scope="focus", current_probe="focus"),
     3: dict(inlet="off", short="off", enclosure="focus", fuse_inlet="fault"), 4: dict(pe="focus", short=None, earth_tester="instr", megger="instr", ac_source=None)})

F["DVT-SAF-001"] = fig(
    "Circulation fan supply opened while the heater is at full output — the software must cut the heater; the cut is read on the heater-body thermocouple",
    {**HEAT_ON, **TC, "fan_circ": "fault", "ui": "focus"},
    {0: dict(fan_circ="fault", tc08="focus", tc_heater="focus"), 1: dict(ui="focus", log="instr"), 2: TRACE_TURN,
     3: dict(ui="focus"), 4: dict(fan_circ="ok", ui="focus", heater="off", ssr_heater="off", wire_heater="off"), 5: dict(tc08="focus")})

F["DVT-SAF-002"] = fig(
    "Heater control NTC unplugged during heat-up — heating must stop; the de-energisation is the rise-to-fall turn on the TC-08 trace",
    {**HEAT_ON, **TC, "ntc_heater": "fault"},
    {0: dict(ntc_heater="fault", tc08="focus"), 1: TRACE_TURN, 2: dict(ui="focus"),
     3: dict(ui="focus", ssr_heater="off", heater="off", wire_heater="off", tc_heater="focus"),
     4: dict(ntc_heater="ok", ui="focus", heater="on"), 5: dict(tc08="focus")})

F["DVT-SAF-004"] = fig(
    "LED thermistor open circuit — cure start inhibited, LED drive cut mid-cure within 2 s (Ophir trace), alarm names the sensor",
    {**UV_ON, "th_right": "fault", "ophir_head": "instr", "ophir": "instr"},
    {0: dict(th_right="fault", led_left=None, led_right=None, led_back=None, led_door=None, ssr_led=None, drivers=None, wire_led=None, inlet=None),
     1: dict(ui="focus", th_right="fault", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off", drivers="off", wire_led="off"),
     2: dict(th_right="fault", ophir="focus", ophir_head="focus", led_right="off", ssr_led="off", drivers="off", wire_led="off"),
     3: dict(ui="focus", th_right="fault")})

F["DVT-SAF-005"] = fig(
    "One LED cooling fan disabled — job start inhibited, mid-job stop, and the error names the right fan",
    {**UV_ON, "fan_led_right": "fault"},
    {0: dict(fan_led_right="fault", led_left=None, led_right=None, led_back=None, led_door=None, ssr_led=None, drivers=None, wire_led=None),
     1: dict(ui="focus", fan_led_right="fault", ssr_led="off", drivers="off", wire_led="off", led_left="off", led_right="off", led_back="off", led_door="off"),
     2: dict(ui="focus", fan_led_right="fault"), 3: dict(fan_led_right="fault", led_right="off", ssr_led="off", drivers="off", wire_led="off"),
     4: dict(th_right="focus", fan_led_right="fault")})

F["DVT-SAF-006"] = fig(
    "Chamber intake fan disconnected, then rotor blocked — job start inhibited and the fan named; injected again during cooling",
    {"fan_intake": "fault", "damper": "focus", "ui": "focus"},
    {0: dict(fan_intake="fault"), 1: dict(ui="focus", fan_intake="fault"), 2: dict(ui="focus"), 3: dict(fan_intake="fault", damper="on", fan_circ="on", chamber="focus")})

F["DVT-SAF-020"] = fig(
    "Desk review — every alarm raised in DVT-SAF-001…DVT-SAF-020 checked against the error registry: names the component, states the recovery, logged with a timestamp",
    {"ui": "focus", "registry": "instr", "log": "instr", "controller": "focus"},
    {0: dict(ui="focus"), 1: dict(registry="focus"), 2: dict(ui="focus", registry="focus"), 3: dict(log="focus", controller="focus")})

F["DVT-SAF-007"] = fig(
    "110 V mains into the 220 V selector position — about a quarter of the heater power; the chamber must not silently fail to reach temperature",
    {**HEAT_ON, "selector": "fault", "ac_source": "instr", "current_probe": "instr", "chamber_sensor": "instr", "ui": "focus"},
    {0: dict(selector="fault", ac_source="focus", heater=None, ssr_heater=None, wire_heater=None, inlet=None), 1: dict(inlet="on", controller="on", ui="on", heater=None, ssr_heater=None, wire_heater=None),
     2: dict(ui="focus", heater="on"), 3: dict(current_probe="focus", wire_heater="focus"), 4: dict(chamber_sensor="focus", chamber="focus"),
     5: dict(ui="focus"), 6: dict(fuse_heater="ok", fuse_inlet="ok", cutout="ok"), 7: dict(selector="ok", heater="on")},
    selector="230", mains="110 V")

F["DVT-SAF-017"] = fig(
    "Voltage selector between detents (open circuit) — controller and UI run, the heater receives no power; the alarm must tell the customer to set the selector",
    {"inlet": "on", "fuse_inlet": "on", "selector": "fault", "wire_ctrl": "on", "psu": "on", "controller": "on", "ui": "on",
     "fuse_heater": "off", "ssr_heater": "off", "wire_heater": "off", "heater": "off", **TC, "current_probe": "instr", "ac_source": "instr"},
    {0: dict(selector="fault", ac_source="focus"), 1: dict(controller="focus", ui="focus", psu="focus"), 2: dict(ui="focus", tc08="focus"),
     3: dict(current_probe="focus", wire_heater="off"), 4: dict(chamber_sensor="instr", tc_heater="focus", chamber="focus"), 5: dict(ui="focus"),
     6: dict(ui="focus", ssr_heater="off"), 7: dict(selector="ok", heater="on", wire_heater="on", ssr_heater="on", fuse_heater="on"),
     8: dict(tc08="focus", log="instr")},   # the fuse / damage inspection step removed (user, 2026-11-12)
    selector="mid", mains="230 V")

F["DVT-THM-001"] = fig(
    "Step from ambient to the setpoint with the 16-channel grid, the reference thermocouple and the control sensor logged — overshoot, settling, uniformity, heat-up time",
    {**HEAT_ON, "grid": "instr", "ref_tc": "instr", "chamber_sensor": "instr", "tc08": "instr", "ac_source": "instr"},
    {0: dict(ac_source="focus", selector="focus", chamber_sensor="focus", heater=None, ssr_heater=None, wire_heater=None), 1: dict(grid="focus", ref_tc="focus", tc08="focus", heater=None, ssr_heater=None, wire_heater=None),
     2: dict(ui="focus", heater="on"), 3: dict(chamber_sensor="focus"), 4: dict(ref_tc="focus"), 5: dict(ref_tc="focus", chamber_sensor="focus"),
     6: dict(chamber_sensor="focus"), 7: dict(grid="focus"), 8: dict(chamber_sensor="focus"), 9: dict(heater="off", ssr_heater="off", wire_heater="off", grid="focus", fan_intake="on", damper="on"), 10: dict(tc08="focus")})

F["DVT-THM-007"] = fig(
    "Step from ambient to 80 C at 220 V with the 16-channel grid read by the machine — heat-up time, then a 5 minute hold and the uniformity over it",
    {**HEAT_ON, "grid": "instr", "chamber_sensor": "instr", "tc08": "instr", "ac_source": "instr"},
    {0: dict(ac_source="focus", selector="focus", chamber_sensor="focus", heater=None, ssr_heater=None, wire_heater=None),
     1: dict(ui="focus", heater="on", grid="focus", tc08="focus"), 2: dict(chamber_sensor="focus"), 3: dict(chamber_sensor="focus", grid="focus"),
     4: dict(heater="off", ssr_heater="off", wire_heater="off", grid="focus"), 5: dict(tc08="focus")})

F["DVT-ENV-001"] = fig(
    "The packaged unit shipped by truck with a shock logger and indicators inside the crate — functional acceptance before and after, inspection on arrival",
    {"crate": "focus", "logger": "instr", "truck": "instr", "enclosure": "focus"},
    {0: dict(ui="focus", heater="on", led_right="on", led_left="on", led_back="on", led_door="on", crate=None), 1: dict(logger="focus", crate="focus"), 2: dict(truck="focus", crate="focus"),
     3: dict(crate="focus", logger="focus"), 4: dict(crate=None, enclosure="focus", door="focus", door_sensor="focus", led_left="focus", led_right="focus", led_back="focus", led_door="focus"),
     5: dict(logger="focus", crate=None), 6: dict(ui="focus", heater="on", led_right="on", led_left="on", led_back="on", led_door="on", crate=None)})

F["DVT-ELE-001"] = fig(
    "Earth bond: high test current from the inlet PE pin to every accessible conductive part — the resistance must stay under the limit at every point",
    {"pe": "focus", "earth_tester": "instr", "enclosure": "focus", "inlet": "focus"},
    {0: dict(earth_tester="focus"), 1: dict(pe="focus", enclosure="focus", door="focus", earth_tester="focus"), 2: dict(enclosure="focus"), 3: dict(pe="focus", fuse_inlet="focus", selector="focus")})

F["DVT-ELE-002"] = fig(
    "Insulation resistance: L and N shorted together, 500 V DC against PE for 60 s",
    {"inlet": "focus", "pe": "focus", "megger": "instr", "short": "focus"},
    {0: dict(short="focus", inlet="focus"), 1: dict(megger="focus", pe="focus"), 2: dict(operator="instr")})

F["DVT-ELE-003"] = fig(
    "Dielectric strength: the test voltage across mains-to-PE and across every insulation barrier (mains to SELV, mains to LED driver output); no breakdown",
    {"inlet": "focus", "pe": "focus", "hipot": "instr", "psu": "focus", "drivers": "focus", "controller": "focus"},
    {0: dict(hipot="focus"), 1: dict(hipot="focus", inlet="focus", pe="focus", enclosure="focus"), 2: dict(hipot="focus", psu="focus", drivers="focus", wire_led="focus", wire_ctrl="focus"),
     3: dict(megger="instr", hipot=None)})

F["DVT-ELE-004"] = fig(
    "Touch current at the accessible parts, both polarities, with PE open as the single fault, idle and at full load",
    {"touch_meter": "instr", "pe": "focus", "enclosure": "focus", "operator": "instr"},
    {0: dict(touch_meter="focus", inlet="on"), 1: dict(pe="fault", touch_meter="focus"), 2: {**HEAT_ON, **UV_ON, "touch_meter": "focus"}})

F["DVT-ELE-005"] = fig(
    "Input current, real power and inrush per operating mode at 100 / 110 / 230 / 240 V — idle, HEAT, CURE, everything on; I²t against the fuse and breaker curves",
    {"power_analyzer": "instr", "ac_source": "instr", "current_probe": "instr", "inlet": "focus", "fuse_inlet": "focus"},
    {0: dict(ac_source="focus", selector="focus"), 1: dict(controller="on", ui="on", power_analyzer="focus"), 2: m(HEAT_ON, power_analyzer="focus"),
     3: m(UV_ON, power_analyzer="focus"), 4: {**HEAT_ON, **UV_ON, "fan_intake": "on", "power_analyzer": "focus"}, 5: dict(inlet="on", current_probe="focus", scope="instr", power_analyzer=None),
     6: dict(fuse_inlet="focus"), 7: dict(inlet="focus", ui="focus")})

F["DVT-SAF-008"] = fig(
    "Door interlock — no UV with the door open; opening the door mid-cure removes UV within 1 s on the Ophir trace; the lock holds against a pull; magnet defeat attempted",
    {**UV_ON, "door": "focus", "door_sensor": "focus", "door_lock": "focus", "ophir_head": "instr", "ophir": "instr"},
    {0: dict(door="fault", ui="focus", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off", drivers="off", wire_led="off"),
     1: dict(door="fault", ophir="focus", ophir_head="focus", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off", drivers="off", wire_led="off"),
     2: dict(door_lock="focus", door="focus"), 3: dict(magnet="fault", door_sensor="focus", door="fault")})   # steps 5-6 removed (user, 2026-11-12)

F["DVT-SAF-009"] = fig(
    "Heater fed from an external supply with the machine commanding nothing and its limits untouched — the independent thermal cutout must open; trip time, trip temperature and reset temperature on the heater-body thermocouple, the trace itself the fourth deliverable",
    {**HEAT_ON, **TC, "cutout": "focus", "controller": "off", "ssr_heater": "off"},
    {0: dict(cutout="focus", tc_heater="focus", heater=None, ssr_heater=None, wire_heater=None),
     1: dict(tc08="focus", tc_heater="focus", fan_circ="focus", heater=None, ssr_heater=None, wire_heater=None),
     2: dict(controller="off", ssr_heater="off", wire_heater="on", heater="on", ui="focus"),
     3: dict(cutout="fault", heater="off", wire_heater="off", ssr_heater="off", tc08="focus", tc_heater="focus")})

F["DVT-SAF-010"] = fig(
    "Firmware hung on purpose — the separate output watchdog must cut: UV off on the StarBright, heater off on the TC-08 trace; nothing restarts by itself",
    {**HEAT_ON, **TC, "heartbeat": "fault", "controller": "fault", "ssr_heater": "focus", "ssr_led": "focus", "ophir_head": "instr", "ophir": "instr"},
    {0: m(UV_ON, tc_heater="focus", tc08="focus", ophir="focus", ophir_head="focus"),
     1: dict(controller="fault", heartbeat="fault", ssr_heater="focus", ssr_led="focus", ophir="focus", tc_heater="focus"),
     2: dict(controller="focus", heater="off", ssr_heater="off", wire_heater="off", log="instr")})

F["DVT-SAF-011"] = fig(
    "Mains cut for 20 ms … 60 s during a job — nothing resumes by itself on restoration, the door is releasable, the job is marked aborted, the configuration survives",
    {**HEAT_ON, **UV_ON, **TC, "inlet": "fault", "ac_source": "instr", "door_lock": "focus"},
    {0: dict(inlet="fault", ac_source="focus"), 1: dict(inlet="on", heater="off", ssr_heater="off", wire_heater="off", ssr_led="off", drivers="off", wire_led="off", led_left="off", led_right="off", led_back="off", led_door="off", tc_heater="focus", tc08="focus"),
     2: dict(inlet="fault", door_lock="focus", door="focus"), 3: dict(ui="focus", log="instr", inlet="on"), 4: dict(controller="focus", inlet="fault", log="instr")})

F["DVT-SAF-012"] = fig(
    "UV radiometer scanned along the door seam, hinge, damper, vents, cable entries and panel joints at 10 cm, then at the operator position",
    {**UV_ON, "vents": "focus", "uv_meter": "instr", "door": "focus"},
    {0: dict(vents="focus", uv_meter="focus", door="focus", damper="focus"), 1: dict(operator="instr", uv_meter="focus", vents=None), 2: dict(operator="focus", uv_meter="focus", vents=None)})

F["DVT-SAF-013"] = fig(
    "Door switch connector unplugged - the LEDs and the heating are commanded on and neither may turn on",
    {**UV_ON, "door_sensor": "fault", "ssr_led": "focus", "door": "focus"},
    {0: dict(door_sensor="fault", ui="focus"),
     1: dict(door_sensor="fault", ui="focus", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off", drivers="off", wire_led="off"),
     2: dict(door_sensor="fault", ui="focus", heater="off", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off"),
     3: dict(ui="focus", log="instr", door_sensor="fault", led_left="off", led_right="off", led_back="off", led_door="off", ssr_led="off"),
     4: dict(door_sensor="ok")})

F["DVT-SAF-014"] = fig(
    "Software stack failure - screen killed (the cure carries on), storage read-only (safe, alarm), I2C bus lost (heater and UV off) - read on the StarBright and the heater-body thermocouple",
    {**HEAT_ON, **UV_ON, "controller": "fault", "ui": "fault", "ssr_heater": "focus", "ssr_led": "focus", "log": "instr", "ophir": "instr", "ophir_head": "instr"},
    {0: m(UV_ON, ophir="focus", ophir_head="focus"),
     1: dict(controller="fault", ui="fault", ssr_heater="focus", ssr_led="focus", ophir="focus"),
     2: dict(controller="ok", heater="off", ssr_heater="off", ssr_led="off", log="focus")})

F["DVT-THM-002"] = fig(
    "30-minute cure at the working point with thermocouples bonded to all four LED panels next to the built-in thermistors — back-face maximum, rate of rise, junction margin",
    {**HEAT_ON, **UV_ON, "th_left": "instr", "th_right": "instr", "th_back": "instr", "th_door": "instr", "tc08": "instr"},
    {0: dict(ui="focus", chamber_sensor="focus"), 1: dict(tc08="focus", th_left="focus", th_right="focus", th_back="focus", th_door="focus"), 2: dict(led_left="focus", led_right="focus", led_back="focus", led_door="focus"),
     3: dict(tc08="focus"), 4: dict(led_right="focus"), 5: dict(th_right="focus"), 6: dict(led_right="focus"), 7: dict(ui="focus", ssr_led="focus"), 8: dict(tc08="focus")})

F["DVT-SAF-015"] = fig(
    "LED cooling degraded in steps (fan duty 75 / 50 / 25 %, or an obstruction) on one side — the alarm must name the SIDE and blame the right fan; other panels stay quiet",
    {**UV_ON, "fan_led_right": "fault", "th_right": "instr", "ui": "focus"},
    {0: dict(th_right="focus", fan_led_right="focus"), 1: dict(fan_led_right="fault"), 2: dict(th_right="focus", ui="focus"), 3: dict(ui="focus"), 4: dict(ui="focus", led_right="focus"),
     5: dict(ui="focus", fan_led_right="fault"), 6: dict(fan_led_right="focus"), 7: dict(th_right="focus", led_right="off", ssr_led="off", drivers="off", wire_led="off"),
     8: dict(led_left="focus", led_back="focus", led_door="focus", th_left="focus", th_back="focus", th_door="focus"), 9: dict(fan_led_right="ok", ui="focus")})

F["DVT-SAF-016"] = fig(
    "One LED panel electrically disconnected (at the driver or at the panel) — detected at switch-on, the alarm names the panel, the job does not run dark, the other three keep working",
    {**UV_ON, "led_right": "fault", "wire_led": "focus", "drivers": "focus", "dmm": "instr"},
    {0: dict(led_right="fault", wire_led="focus", drivers="focus"), 1: dict(led_right="fault", dmm="focus", inlet="on", led_left="off", led_back="off", led_door="off", ssr_led="off"),
     2: dict(led_right="fault", ui="focus"), 3: dict(ui="focus", led_right="fault"), 4: dict(ui="focus", led_right="fault", led_left="off", led_back="off", led_door="off", ssr_led="off", drivers="off"),
     5: dict(led_right="fault", led_left="on", led_back="on", led_door="on"), 6: dict(led_right="fault", ui="focus"), 7: dict(led_right="ok", ui="focus"), 8: dict(led_right="ok", drivers="ok")})

F["DVT-THM-003"] = fig(
    "Cool-down from 80 C at the fast / normal / slow commanded rate — damper open, heater fan at 100 %, intake fan modulating; achieved rate per band, undershoot, spread",
    {"heater": "off", "ssr_heater": "off", "wire_heater": "off", "fan_circ": "on", "fan_intake": "on", "damper": "on", "grid": "instr", "chamber_sensor": "instr", "tc08": "instr"},
    {0: dict(chamber_sensor="focus", ref_tc="instr"), 1: dict(ui="focus"), 2: dict(damper="focus", fan_circ="focus"), 3: dict(grid="focus", fan_intake="focus", tc08="focus"),
     4: dict(chamber_sensor="focus"), 5: dict(chamber_sensor="focus", fan_intake="focus"), 6: dict(fan_intake="focus"), 7: dict(chamber_sensor="focus"), 8: dict(grid="focus"),
     9: dict(ui="focus", chamber_sensor="focus"), 10: dict(tc08="focus")})

F["DVT-THM-005"] = fig(
    "Drying from a cold start to 50 C — heater and heater fan on, damper closed until the chamber is close to the set point, then the damper opens and the intake fan blows fresh air; time to 30 / 40 / 50 / 60 C and the highest temperature off the chamber sensor",
    {**HEAT_ON, "fan_intake": "off", "damper": "off", "chamber_sensor": "instr"},
    {0: dict(chamber_sensor="focus", heater="off", ssr_heater="off", wire_heater="off", fan_circ="off"),
     1: dict(ui="focus", chamber_sensor="instr"),
     2: dict(chamber_sensor="focus", ui="focus"),
     3: dict(chamber_sensor="focus", damper="on", fan_intake="on"),
     4: dict(chamber_sensor="focus", damper="on", fan_intake="on"),
     5: dict(damper="focus", fan_intake="focus", chamber_sensor="instr")})

F["DVT-THM-006"] = fig(
    "230 V into the 110 V selector position, HEAT commanded — the heater is over-driven until the 5 A branch fuse opens; the shutdown instant is the rise-to-fall turn on the heater-body thermocouple",
    {**HEAT_ON, **TC, "selector": "fault", "fuse_heater": "focus", "ac_source": "instr", "thermal_cam": "instr"},
    {0: dict(fuse_inlet="focus", fuse_heater="focus", selector="fault", tc_heater="focus", heater=None, ssr_heater=None, wire_heater=None, inlet=None),
     1: dict(inlet="on", controller="on", ui="on", heater="off", ssr_heater="off", wire_heater="off", tc_heater="focus"),
     2: dict(ui="focus", heater="on", tc08="focus"), 3: dict(fuse_heater="fault", **TRACE_TURN, thermal_cam="focus"),
     4: dict(ui="focus", log="instr", fuse_heater="fault", heater="off", ssr_heater="off", wire_heater="off"),
     5: dict(inlet="off", fuse_heater="fault", heater="off", ssr_heater="off", wire_heater="off", enclosure="focus"),
     6: dict(fuse_heater="ok", selector="ok", heater="on", tc08="focus")},
    selector="110", mains="230 V")

F["DVT-GAS-007"] = fig(
    "N2 purge with two oxygen probes (centre and worst corner) — time to 95 % N2 and the lowest O2 reached; then the valve closes and the chamber must hold above 95 % N2 for the longest cure",
    {"n2_valve": "focus", "n2_nozzle": "focus", "n2_supply": "instr", "o2_center": "instr", "o2_corner": "instr", "o2_analyser": "instr", "damper": "off", "bofa": "off", "door": "focus"},
    {0: dict(n2_supply="focus", o2_analyser="focus", chamber_sensor="instr", n2_valve=None, n2_nozzle=None), 1: dict(ui="focus", n2_valve=None, n2_nozzle=None),
     2: dict(n2_valve="on", n2_nozzle="on", damper="off", bofa="off", o2_center="focus", o2_corner="focus", ui="focus"),
     3: dict(n2_valve="on", n2_nozzle="on", o2_center="focus", o2_corner="focus"), 4: dict(n2_valve="on", n2_nozzle="on", o2_center="focus", n2_supply="focus"),
     5: dict(n2_valve="off", n2_nozzle="off", n2_supply="focus", ui="focus"), 6: dict(n2_valve="off", n2_nozzle="off", o2_center="focus", o2_corner="focus", vents="focus", door="focus"),
     7: dict(n2_supply="focus", ui="focus"), 8: m(UV_ON, ui="focus", n2_valve="off", n2_nozzle="off"), 9: dict(o2_analyser="focus", log="instr")})

for _nm, _tid in ((405, "DVT-OPT-001"), (450, "DVT-OPT-002")):
    F[_tid] = fig(
        f"StarBright on the machine's own USB, head at the chamber centre — the machine steps the LEDs 30 → 100 % at {_nm} nm, 10 s per step; irradiance against the command",
        m(UV_ON, ophir_head_c="instr", ophir_usb="instr", controller="focus", door="focus"),
        {0: dict(ophir_head_c="focus", ophir_usb="focus", ssr_led="focus", drivers="focus", controller="focus", log="instr")})


# ---------------------------------------------------------------- SVG primitives
def _t(s: str) -> str:
    return html.escape(s, quote=True)          # drawings stay in English in every console language


# ---- nitrogen: supply, valve, venting, operator (DVT-GAS-001…DVT-GAS-006, after DVT-GAS-007)
N2_IDLE = dict(n2_supply="instr", n2_valve="off", n2_nozzle="off", o2_center="instr", o2_analyser="instr", damper="off", bofa="off")
N2_ON = dict(n2_valve="on", n2_nozzle="on")
F["DVT-GAS-001"] = fig(
    "Nitrogen over-pressure — above 3 bar the valve stays closed, refuses to open and the machine alarms; it closes at once when the pressure rises while it flows",
    m(N2_IDLE, n2_supply="focus", n2_valve="focus", ui="focus"),
    {0: dict(n2_supply="focus", n2_valve="off"),
     1: dict(n2_valve="off", n2_nozzle="off", ui="focus", n2_supply="focus"),
     2: m(N2_ON, n2_supply="focus", ui="focus"),
     3: dict(n2_supply="focus", n2_valve="off", n2_nozzle="off", ui="focus"),
     4: m(N2_ON, n2_supply="focus")})

F["DVT-GAS-002"] = fig(
    "Nitrogen supply low or lost — enable guard without supply, pre-cure check below 6 bar, supply closed mid-purge and mid-cure: the operator must be told it is the N2 line; no cure silently in air",
    m(N2_IDLE, n2_supply="fault", ui="focus"),
    {0: dict(n2_supply="focus"),
     1: dict(n2_supply="fault", ui="focus", controller="focus"),
     2: dict(n2_supply="fault", ui="focus", n2_valve="off"),
     3: m(N2_ON, n2_supply="fault", o2_center="focus", ui="focus", led_left="on", led_right="on", led_back="on", led_door="on"),
     4: dict(ui="focus"),
     5: dict(o2_analyser="focus", log="instr")})
F["DVT-GAS-003"] = fig(
    "Nitrogen line leak-down — line charged to 4 bar and isolated, valve closed; the machine logs the line pressure for 12 hours",
    m(N2_IDLE, n2_supply="focus", n2_valve="off"),
    {0: dict(n2_supply="focus", n2_valve="off"),
     1: dict(n2_supply="instr", n2_valve="off", log="instr"),
     2: dict(n2_supply="focus", n2_valve="focus"),
     3: dict(n2_supply="ok")})

F["DVT-GAS-004"] = fig(
    "Venting after a cure under nitrogen — a program without the Cooling vent is refused; O2 back to 19.5 % before the job completes and the door lock releases",
    m(N2_IDLE, vents="focus", door_lock="focus", o2_center="instr"),
    {0: dict(ui="focus", controller="focus"),
     1: dict(n2_valve="off", n2_nozzle="off", vents="focus", fan_intake="on", damper="on", o2_center="focus", ui="focus"),
     2: dict(door_lock="focus", door="focus", o2_center="focus", operator="instr"),
     3: dict(o2_analyser="focus", log="instr")})
F["DVT-GAS-005"] = fig(
    "Room O2 at the operator — two purges back to back vented into the smallest permitted room, no extraction: breathing-zone O2 must stay above 19.5 %",
    m(N2_IDLE, operator="focus", vents="focus", bofa="off"),
    {0: dict(enclosure="focus", operator="focus"),
     1: m(N2_ON, vents="on", operator="focus", bofa="off"),
     2: dict(operator="focus", n2_valve="off", n2_nozzle="off")})
F["DVT-GAS-006"] = fig(
    "Nitrogen not reaching the chamber — the tube after the valve is blocked; the machine sees no pressure drop, closes the valve and alarms",
    m(N2_IDLE, n2_valve="focus", n2_nozzle="fault", ui="focus"),
    {0: dict(n2_nozzle="fault", n2_valve="off"),
     1: dict(n2_valve="fault", n2_nozzle="fault", ui="focus"),
     2: m(N2_ON, n2_supply="focus")})

F["DVT-NFC-001"] = fig(
    "Build-head NFC identification — a registered build head inserted to its stop is read and bound; a swapped head follows the tag; no tag, an unknown tag, a short seating and a disabled reader are reported to the operator",
    {"build_head": "focus", "nfc_reader": "focus", "door": "focus", "ui": "instr", "log": "instr"},
    {0: dict(build_head="focus"), 1: dict(build_head="focus", door="focus", nfc_reader="on"), 2: dict(nfc_reader="focus", log="focus"),
     3: dict(ui="focus", build_head="focus"), 4: dict(ui="focus", controller="focus"), 5: dict(build_head="off", nfc_reader="focus", ui="focus"), 6: dict(log="focus")})


F["DVT-THM-004"] = fig(
    "LED back-face temperature settled at LED-cooling fan duty 100 / 90 / 80 / 70 %, LEDs at maximum in an 80 C chamber — margin to the 75 C working limit per panel, the lowest duty the design can afford",
    {**HEAT_ON, **UV_ON, "fan_led_left": "focus", "fan_led_right": "focus", "fan_led_back": "focus", "fan_led_door": "focus", "th_left": "instr", "th_right": "instr", "th_back": "instr", "th_door": "instr", "tc08": "instr"},
    {0: dict(chamber_sensor="focus", ui="focus"), 1: dict(fan_led_left="focus", fan_led_right="focus", fan_led_back="focus", fan_led_door="focus", ui="focus"),
     2: dict(tc08="focus", th_left="focus", th_right="focus", th_back="focus", th_door="focus"), 3: dict(led_left="focus", led_right="focus", led_back="focus", led_door="focus"),
     4: dict(th_right="focus", tc08="focus"), 5: dict(ui="focus", ssr_led="focus"), 6: dict(tc08="focus", log="instr")})


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _txt(x, y, s, size=9, anchor="middle", color=INK, bold=False):
    w = ' font-weight="700"' if bold else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{color}"{w}>{_t(s)}</text>'


def _cross(cx, cy, r=6):
    return f'<path d="M{cx - r},{cy - r} L{cx + r},{cy + r} M{cx + r},{cy - r} L{cx - r},{cy + r}" stroke="{BAD}" stroke-width="2.2"/>'


def _draw(eid: str, e: dict, st: str | None, spec: dict) -> str:
    k, s, f = e["kind"], STATE_STROKE[st], STATE_FILL[st]
    lw = 2 if st in ("focus", "fault", "instr", "on") else 1.2
    out = []
    tag = TAGS.get(eid)
    lab = f"{tag} {e['label']}" if tag and k not in ("box",) else e["label"]
    if k == "box":
        dash = ' stroke-dasharray="6 4"' if e.get("dash") else ""
        fill = "none" if eid in ("enclosure", "chamber", "crate") else f
        if eid in ("enclosure", "chamber", "crate") and st is not None:
            fill = f; out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="{e.get("rx", 0)}" fill="{fill}" opacity="0.35"/>'); fill = "none"
        out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="{e.get("rx", 0)}" fill="{fill}" stroke="{s}" stroke-width="{lw}"{dash}/>')
        if eid == "chamber":
            out.append(_txt(e["x"] + 2, e["y"] - 4, lab, 9, "start", s if st else MUTED))
        elif eid in ("enclosure", "crate"):
            out.append(_txt(e["x"] + 6, e["y"] + 12, lab, 9, "start", s if st else MUTED))
        else:
            out.append(_txt(e["x"] + e["w"] / 2, e["y"] + e["h"] / 2 + 3, lab, 8, color=s if st else INK, bold=st == "focus"))
        if st == "fault": out.append(_cross(e["x"] + e["w"] - 8, e["y"] + 8))
        if tag and eid not in ("enclosure", "chamber", "crate"):
            out.append(f'<text x="{e["x"] + 3}" y="{e["y"] + 8}" font-size="6.5" font-family="{MONO}" font-weight="700" fill="{s if st else MUTED}">{_t(tag)}</text>')
    elif k == "panel":
        fill = UV_FILL if st == "on" else f
        stroke = UV if st == "on" else s
        out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" fill="{fill}" stroke="{stroke}" stroke-width="{lw}"/>')
        if st == "on":
            horiz = e["w"] > e["h"]
            for i in range(5):
                if horiz: x = e["x"] + e["w"] * (i + 0.5) / 5; out.append(f'<line x1="{x}" y1="{e["y"] + e["h"] + 2}" x2="{x}" y2="{e["y"] + e["h"] + 10}" stroke="{UV}" stroke-width="1"/>' if e["y"] < 150 else f'<line x1="{x}" y1="{e["y"] - 2}" x2="{x}" y2="{e["y"] - 10}" stroke="{UV}" stroke-width="1"/>')
                else: y = e["y"] + e["h"] * (i + 0.5) / 5; dx = 10 if e["x"] < 200 else -10; out.append(f'<line x1="{e["x"] + (e["w"] if dx > 0 else 0)}" y1="{y}" x2="{e["x"] + (e["w"] if dx > 0 else 0) + dx}" y2="{y}" stroke="{UV}" stroke-width="1"/>')
        if st in ("focus", "fault", "ok"):
            cx, cy = e["x"] + e["w"] / 2, e["y"] + e["h"] / 2
            if st == "fault": out.append(_cross(cx, cy, 7))
            lx, ly, anc = (cx, e["y"] - 4, "middle") if e["w"] > e["h"] and e["y"] < 150 else (cx, e["y"] + e["h"] + 12, "middle") if e["w"] > e["h"] else (e["x"] - 4, cy + 3, "end") if e["x"] < 200 else (e["x"] + e["w"] + 4, cy + 3, "start")
            if e["w"] > e["h"] and e["y"] < 150: ly = e["y"] + e["h"] + 12
            out.append(_txt(lx, ly, lab, 8, anc, s, True))
    elif k == "dot":
        r = e.get("r", 4)
        out.append(f'<circle cx="{e["cx"]}" cy="{e["cy"]}" r="{r + (1 if st else 0)}" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        if st == "fault": out.append(_cross(e["cx"], e["cy"], r + 3))
        if st:
            side = "start" if e["cx"] < 330 else "end"
            dx = 8 if side == "start" else -8
            if eid in ("th_left",): side, dx = "start", 8
            if eid == "th_right": side, dx = "end", -8
            if eid == "th_back": side, dx = "start", 8
            out.append(_txt(e["cx"] + dx, e["cy"] - 6 if eid not in ("th_door",) else e["cy"] - 7, lab, 8, side, s, st == "focus"))
    elif k == "fan":
        r = e["r"]
        out.append(f'<circle cx="{e["cx"]}" cy="{e["cy"]}" r="{r}" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        for a in (0, 120, 240):
            out.append(f'<path d="M{e["cx"]},{e["cy"]} l{r * 0.85},0 a{r * 0.5},{r * 0.5} 0 0 0 -{r * 0.85},-{r * 0.45} z" fill="{s if st else MUTED}" opacity="0.8" transform="rotate({a} {e["cx"]} {e["cy"]})"/>')
        if st == "fault": out.append(_cross(e["cx"], e["cy"], r + 3))
        if st in ("focus", "fault", "ok", "instr"):
            if eid in ("fan_led_left", "fan_led_right", "fan_led_door", "fan_intake"):
                out.append(_txt(e["cx"], e["cy"] + r + 11, lab, 8, "middle", s, st == "focus"))
            else:
                side = "start" if e["cx"] < 330 else "end"
                out.append(_txt(e["cx"] + (r + 4 if side == "start" else -(r + 4)), e["cy"] + 3, lab, 8, side, s, st == "focus"))
    elif k == "door":
        out.append(f'<line x1="{e["x1"]}" y1="{e["y1"]}" x2="{e["x2"]}" y2="{e["y2"]}" stroke="{s}" stroke-width="{4 if st else 3}"/>')
        if st == "fault":   # door open: swing it
            out.append(f'<line x1="{e["x2"]}" y1="{e["y2"]}" x2="{e["x2"] + 34}" y2="{e["y2"] + 38}" stroke="{BAD}" stroke-width="3" stroke-dasharray="5 3"/>')
            out.append(_txt(e["x2"] + 38, e["y2"] + 36, "Door open", 8, "start", BAD, True))
        elif st:
            out.append(_txt(e["x1"] + 4, e["y1"] + 14, lab, 8, "start", s, st == "focus"))
    elif k == "smallbox":
        out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        if st == "fault": out.append(_cross(e["x"] + e["w"] / 2, e["y"] + e["h"] / 2, 6))
        if st:
            cx = e["x"] + e["w"] / 2
            if eid == "door_lock":
                out.append(_txt(e["x"], e["y"] - 4, lab, 8, "start", s, st == "focus"))
            elif eid == "door_sensor":
                out.append(_txt(e["x"] + e["w"], e["y"] - 4, lab, 8, "end", s, st == "focus"))
            elif eid == "magnet":
                out.append(_txt(e["x"] + e["w"] + 3, e["y"] + e["h"] - 2, lab, 8, "start", s, st == "focus"))
            elif eid == "ui":
                out.append(_txt(e["x"] - 3, e["y"] + e["h"] - 3, lab, 8, "end", s, st == "focus"))
            elif eid in ("cutout", "resistor_10k", "ophir_head", "damper", "n2_valve", "bofa", "nfc_reader", "ophir_head_c"):
                out.append(_txt(cx, e["y"] + e["h"] + 10, lab, 8, "middle", s, st == "focus"))
            else:
                out.append(_txt(e["x"] + e["w"] + 3, e["y"] + e["h"] - 2, lab, 8, "start", s, st == "focus"))
    elif k == "heater":
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        pts = " ".join(f'{x + 10 + i * (w - 20) / 12},{y + (8 if i % 2 else h - 8)}' for i in range(13))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{HOT if st == "on" else (s if st else MUTED)}" stroke-width="2"/>')
        out.append(_txt(x + w / 2, y - 4, lab + (" — ON" if st == "on" else " — OFF" if st == "off" else ""), 8, color=s if st else INK, bold=st in ("focus", "on")))
        if st == "on":
            for i in range(4):
                xx = x + 25 + i * 38
                out.append(f'<path d="M{xx},{y - 12} q4,-6 0,-12 q-4,-6 0,-12" fill="none" stroke="{HOT}" stroke-width="1.3" opacity="0.7"/>')
    elif k == "grid":
        if st:
            for i in range(4):
                for j in range(4):
                    out.append(f'<circle cx="{118 + i * 68}" cy="{88 + j * 56}" r="3" fill="{f}" stroke="{s}" stroke-width="1.2"/>')
            out.append(_txt(118, 82, lab, 8, "start", s, st == "focus"))
    elif k == "vents":
        if st:
            for y in (80, 120, 160, 200, 240):
                out.append(f'<line x1="428" y1="{y}" x2="436" y2="{y + 8}" stroke="{s}" stroke-width="2"/>')
            for x in (60, 380):
                out.append(f'<line x1="{x}" y1="286" x2="{x + 8}" y2="294" stroke="{s}" stroke-width="2"/>')
            out.append(_txt(432, 262, lab, 8, "middle", s, True))
    elif k == "plug":
        cx, cy = e["cx"], e["cy"]
        out.append(f'<rect x="{cx - 14}" y="{cy - 10}" width="28" height="20" rx="3" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        out.append(f'<line x1="{cx - 5}" y1="{cy - 4}" x2="{cx - 5}" y2="{cy + 4}" stroke="{s}" stroke-width="2"/><line x1="{cx + 5}" y1="{cy - 4}" x2="{cx + 5}" y2="{cy + 4}" stroke="{s}" stroke-width="2"/>')
        out.append(_txt(cx, cy + 22, lab, 8, color=s if st else INK, bold=st == "focus"))
        out.append(_txt(cx, cy - 15, spec.get("mains", ""), 9, color=s if st else MUTED, bold=True))
        if st == "fault": out.append(_cross(cx, cy, 10))
    elif k == "fuse":
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        if st == "fault":
            out.append(f'<line x1="{x + 4}" y1="{y + h / 2}" x2="{x + w / 2 - 5}" y2="{y + h / 2}" stroke="{BAD}" stroke-width="2"/><line x1="{x + w / 2 + 5}" y1="{y + h / 2}" x2="{x + w - 4}" y2="{y + h / 2}" stroke="{BAD}" stroke-width="2"/>')
            out.append(f'<path d="M{x + w / 2 - 4},{y + 2} l3,5 l-3,4 l4,5" fill="none" stroke="{BAD}" stroke-width="1.5"/>')
            out.append(_txt(x + w / 2, y + h + 11, lab + " — " + "OPEN", 8, color=BAD, bold=True))
        else:
            out.append(f'<line x1="{x + 4}" y1="{y + h / 2}" x2="{x + w - 4}" y2="{y + h / 2}" stroke="{s}" stroke-width="2"/>')
            out.append(_txt(x + w / 2, y - 5 if eid == "fuse_inlet" else y + h + 11, lab, 8, color=s if st else INK, bold=st == "focus"))   # F1 label above: clear of the inlet label
    elif k == "selector":
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        pos = spec.get("selector", "230")
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{f if st else CARD}" stroke="{s}" stroke-width="{lw}"/>')
        out.append(_txt(x + 14, y + h - 6, "110", 8, color=INK, bold=pos == "110")); out.append(_txt(x + w - 14, y + h - 6, "230", 8, color=INK, bold=pos == "230"))
        kx = x + 14 if pos == "110" else x + w - 14 if pos == "230" else x + w / 2
        out.append(f'<circle cx="{kx}" cy="{y + 12}" r="6" fill="{BAD if st == "fault" else (s if st else MUTED)}"/>')
        out.append(f'<line x1="{kx}" y1="{y + 12}" x2="{kx}" y2="{y + 20}" stroke="{CARD}" stroke-width="2"/>')
        out.append(_txt(x + w / 2, y - 5, lab + (" — MID" if pos == "mid" else f" — {pos} V"), 8, color=s if st else INK, bold=st in ("focus", "fault")))
        if st == "fault": out.append(_cross(x + w - 6, y + 6, 4))
    elif k == "earth":
        cx, cy = e["cx"], e["cy"]
        out.append(f'<line x1="{cx}" y1="{cy - 12}" x2="{cx}" y2="{cy}" stroke="{s}" stroke-width="2"/>')
        for i, wd in enumerate((16, 10, 4)):
            out.append(f'<line x1="{cx - wd / 2}" y1="{cy + i * 4}" x2="{cx + wd / 2}" y2="{cy + i * 4}" stroke="{s}" stroke-width="2"/>')
        if st == "fault": out.append(_cross(cx + 12, cy - 6, 5))
        out.append(_txt(cx, cy + 22, lab, 8, color=s if st else INK, bold=st == "focus"))
    elif k == "wire":
        pts = " ".join(f"{x},{y}" for x, y in e["pts"])
        dash = ' stroke-dasharray="4 4"' if st == "off" else ""
        out.append(f'<polyline points="{pts}" fill="none" stroke="{s if st else LINE}" stroke-width="{2 if st else 1.2}"{dash}/>')
        if st in ("focus", "fault"):
            x, y = e["pts"][1]; out.append(_txt(x + 2, y - 4, lab, 8, "start", s, True))
    elif k == "ring":
        out.append(f'<circle cx="{e["cx"]}" cy="{e["cy"]}" r="{e["r"]}" fill="none" stroke="{s}" stroke-width="{lw + 0.5}"/>')
        out.append(_txt(e["cx"], e["cy"] + e["r"] + 10, lab, 8, color=s, bold=st == "focus"))
    elif k == "short":
        cx, cy = e["cx"], e["cy"]
        out.append(f'<path d="M{cx - 4},{cy - 14} l6,8 l-6,4 l7,10" fill="none" stroke="{s}" stroke-width="2.2"/>')
        out.append(_txt(cx + 8, cy - 6, lab, 8, "start", s, st == "fault"))
    elif k == "person":
        cx, cy = e["cx"], e["cy"]
        out.append(f'<circle cx="{cx}" cy="{cy - 10}" r="4" fill="{f}" stroke="{s}" stroke-width="1.5"/><path d="M{cx - 7},{cy + 8} q7,-14 14,0" fill="{f}" stroke="{s}" stroke-width="1.5"/>')
        out.append(_txt(cx, cy + 18, lab, 8, color=s, bold=st == "focus"))
    elif k == "instrument":
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        if e.get("to"):
            tx, ty = e["to"]; out.append(f'<path d="M{x + w / 2},{y} L{x + w / 2},{y - 8} L{tx},{ty}" fill="none" stroke="{s}" stroke-width="1" stroke-dasharray="3 3" opacity="0.8"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{f}" stroke="{s}" stroke-width="{lw}"/>')
        out.append(f'<rect x="{x + 4}" y="{y + 4}" width="{w * 0.35}" height="{h - 8}" rx="2" fill="{CARD}" stroke="{s}" stroke-width="0.8"/>')
        out.append(f'<rect x="{x + 4 + w * 0.35 + 4}" y="{y + 8}" width="{w - w * 0.35 - 16}" height="3" fill="{s}" opacity="0.5"/><rect x="{x + 4 + w * 0.35 + 4}" y="{y + 14}" width="{(w - w * 0.35 - 16) * 0.6}" height="3" fill="{s}" opacity="0.5"/>')
        out.append(_txt(x + w / 2, y + h + 11, lab, 8, color=s, bold=st == "focus"))
    return "".join(out)


ORDER = ("crate", "enclosure", "chamber", "wire_heater", "wire_led", "wire_ctrl", "grid", "led_back", "led_left", "led_right", "led_door", "door", "door_sensor", "door_lock",
         "th_back", "th_left", "th_right", "th_door", "fan_led_back", "fan_led_left", "fan_led_right", "fan_led_door", "heater", "tc_heater", "ntc_heater", "cutout",
         "resistor_10k", "fan_circ", "chamber_sensor", "ref_tc", "fan_intake", "damper", "vents", "ui", "n2_valve", "n2_nozzle", "bofa", "build_head", "nfc_reader", "o2_center", "o2_corner", "ophir_head_c", "inlet", "short", "fuse_inlet", "selector", "fuse_heater",
         "ssr_heater", "ssr_led", "drivers", "psu", "controller", "heartbeat", "pe", "current_probe", "ophir_head", "magnet", "operator",
         "tc08", "ophir", "thermal_cam", "uv_meter", "dmm", "logger", "n2_supply", "o2_analyser", "ophir_usb", "ac_source", "earth_tester", "megger", "hipot", "touch_meter", "power_analyzer", "scope", "truck", "registry", "log")


def states_for(test_id: str, step: int | None = None) -> dict[str, str | None]:
    spec = F.get(test_id)
    if spec is None:
        return {}
    st = dict(spec["el"])
    if step is not None and step in spec["steps"]:
        st.update(spec["steps"][step])
    return st


def figure_svg(test_id: str, step: int | None = None, title: str | None = None, rev: str | None = None, date: str | None = None) -> str:
    """The engineering sheet for a test (step=None: base state) or for one of its
    procedure steps: header, drawing, ISO 7200-style title block with the legend.
    `title` is the test title for the title block (defaults to the test id),
    `rev` the catalog revision, `date` the issue date (default today)."""
    import datetime as _dt
    spec = F.get(test_id) or dict(caption="", el={}, steps={}, selector="230", mains="230 V")
    st = states_for(test_id, step)
    date = date or _dt.date.today().isoformat()
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="{CARD}"/>',
             # header strip
             f'<rect x="0.5" y="0.5" width="{W - 1}" height="{HEAD}" fill="{PAPER}" stroke="{INK}" stroke-width="1"/>',
             _txt(8, 17, "DVT PROCESS FIGURE", 8, "start", MUTED, True),
             _txt(112, 17, _clip(f"{test_id}" + (f" — {title}" if title and title != test_id else ""), 92), 9, "start", INK, True),
             _txt(W - 8, 17, ("BASE STATE" if step is None else f"STEP {step + 1}"), 8.5, "end", ACCENT if step is not None else MUTED, True),
             # drawing area
             f'<rect x="0.5" y="{HEAD + 0.5}" width="{W - 1}" height="{DH}" fill="{PAPER}" stroke="{INK}" stroke-width="1"/>',
             f'<g transform="translate(0,{HEAD})">']
    for eid in ORDER:
        e = E[eid]
        s = st.get(eid)
        if e["group"] == "instrument" and s is None:
            continue                      # instruments appear only when the test uses them
        parts.append(_draw(eid, e, s, spec))
    parts.append(_txt(DW - 8, DH - 6, "Top view · not to scale", 7, "end", MUTED))
    parts.append("</g>")
    # title block (ISO 7200 style): cells left, legend right
    y0 = HEAD + DH
    parts.append(f'<rect x="0.5" y="{y0 + 0.5}" width="{W - 1}" height="{TB - 1}" fill="{CARD}" stroke="{INK}" stroke-width="1"/>')
    cols = [(0, 150, "PROJECT", "sCure / CureBox DVT"), (150, 110, "DOCUMENT", "Process figure"), (260, 70, "TEST", test_id),
            (330, 52, "STEP", "base" if step is None else f"{step + 1}"), (382, 62, "CATALOG", f"v{rev}" if rev else "—"),
            (444, 62, "DATE", date), (506, 56, "SHEET", "1 / 1"), (562, 98, "DRAWN", "generated · NTS")]
    for x, w, k, v in cols:
        parts.append(f'<rect x="{x + 0.5}" y="{y0 + 0.5}" width="{w}" height="26" fill="none" stroke="{LINE}" stroke-width="1"/>')
        parts.append(_txt(x + 4, y0 + 9, k, 5.5, "start", MUTED, True))
        parts.append(f'<text x="{x + 4}" y="{y0 + 21}" font-size="7.5" font-family="{FONT}" font-weight="700" fill="{INK}">{_t(v)}</text>')
    # second row: legend + tag key
    ly = y0 + 26
    parts.append(f'<line x1="0.5" y1="{ly}" x2="{W - 0.5}" y2="{ly}" stroke="{LINE}" stroke-width="1"/>')
    parts.append(_txt(4, ly + 11, "LEGEND", 5.5, "start", MUTED, True))
    lx = 46
    for k, txt in (("focus", "This step"), ("on", "Energised"), ("fault", "Injected fault"), ("instr", "Instrument"), ("ok", "Restored / verified"), ("off", "De-energised")):
        parts.append(f'<rect x="{lx}" y="{ly + 5}" width="10" height="8" fill="{STATE_FILL[k]}" stroke="{STATE_STROKE[k]}" stroke-width="1.2"/>')
        parts.append(_txt(lx + 13, ly + 12, txt, 7, "start", INK)); lx += 14 + 5.2 * len(txt) + 14
    parts.append(_txt(4, ly + 28, "TAGS", 5.5, "start", MUTED, True))
    parts.append(f'<text x="46" y="{ly + 29}" font-size="6.5" font-family="{FONT}" fill="{MUTED}">{_t("F fuse · K SSR · E heater · M fan / motor · RT thermistor · TC thermocouple · SV solenoid valve · QE gas probe · B sensor · Y actuator · H LED panel · A electronics · G PSU · X mains inlet · HMI user interface")}</text>')
    parts.append("</svg>")
    return "".join(parts)


def figure_caption(test_id: str) -> str:
    spec = F.get(test_id)
    return spec["caption"] if spec else ""


def has_figure(test_id: str) -> bool:
    return test_id in F


def check_specs(catalog_tests: dict) -> list[str]:
    """Consistency problems: unknown elements / states, step indexes beyond the procedure, catalog tests without a figure."""
    problems = []
    for tid, spec in F.items():
        if tid not in catalog_tests:
            problems.append(f"{tid}: figure spec for a test that is not in the catalog")
            continue
        n = len(catalog_tests[tid]["procedure_steps"])
        for i, o in spec["steps"].items():
            if not 0 <= i < n:
                problems.append(f"{tid}: step {i} has no procedure step (test has {n})")
            for eid, s in o.items():
                if eid not in E: problems.append(f"{tid} step {i}: unknown element {eid}")
                if s not in STATE_STROKE: problems.append(f"{tid} step {i}: unknown state {s}")
        for eid, s in spec["el"].items():
            if eid not in E: problems.append(f"{tid}: unknown element {eid}")
            if s not in STATE_STROKE: problems.append(f"{tid}: unknown state {s}")
    for tid in catalog_tests:
        if tid not in F:
            problems.append(f"{tid}: no figure spec (add one in dvt_tool/figures.py)")
    return problems


def export_all(catalog_tests: dict, out_dir: str | Path, steps: bool = False, rev: str | None = None) -> list[Path]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); written = []
    for tid, t in catalog_tests.items():
        if tid not in F: continue
        p = out / f"{tid}.svg"; p.write_text(figure_svg(tid, None, t["title"], rev=rev), encoding="utf-8"); written.append(p)
        if steps:
            for i in range(len(t["procedure_steps"])):
                p = out / f"{tid}_step{i + 1}.svg"; p.write_text(figure_svg(tid, i, t["title"], rev=rev), encoding="utf-8"); written.append(p)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export the DVT process figures as SVG")
    ap.add_argument("--catalog", default=str(Path(__file__).resolve().parents[1] / "catalog" / "DVT_test_catalog.yaml"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "docs" / "figures"))
    ap.add_argument("--steps", action="store_true", help="also one SVG per procedure step")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()
    from .catalog import Catalog
    from .ui.i18n import set_language
    set_language(a.lang)
    cat = Catalog.load(a.catalog, a.lang)
    probs = check_specs(cat.tests)
    for pr in probs: print("WARN", pr)
    files = export_all(cat.tests, a.out, a.steps, rev=cat.version)
    print(f"{len(files)} figures written to {a.out}")
