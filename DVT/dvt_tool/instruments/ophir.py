"""Ophir StarBright power / energy meter — three interchangeable backends.

    SimulatedMeter   reads the in-process simulated machine (sim://) and
                     returns an irradiance that follows the UV drive with a
                     short optical/thermal lag — for rehearsing the procedure
    OphirStarLab     the vendor's COM object ("OphirLMMeasurement.CoLMMeasurement",
                     installed with StarLab) over USB — streams timestamped
                     readings; the preferred path on a Windows bench
    OphirSerial      RS-232 / USB-serial "$"-command protocol polled with $SP;
                     needs pyserial

All three expose the same tiny interface used by `uvoff.UvOffRunner`:

    connect() -> dict            instrument / head info (logged with the run)
    read_all() -> list[(t, v)]   every new reading since the last call,
                                 t = time.monotonic() seconds, v in `unit`
    unit                         "W", "mW", "mW/cm2" … as configured
    close()

`open_meter(spec)` builds one from a short text spec that the console stores
in the campaign meta:  "sim" | "starlab" | "starlab:<serial-no>" |
"serial:COM3" | "serial:COM3:9600".

CONFIRM (Ophir manual, "StarBright RS232 / USB commands"): the serial command
set below ($VE, $HI, $SP, $WL, $RN) and the 9600-8-N-1 default follow the
classic Ophir Nova/Vega/StarBright user-command protocol — replies start with
'*' (ok) or '?' (error). Verify against the meter's firmware before relying
on it; the StarLab COM path is the vendor-supported one and needs no protocol
assumptions.
"""

from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field

_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


class MeterError(RuntimeError):
    pass


@dataclass
class MeterInfo:
    backend: str
    model: str = ""
    serial: str = ""
    head: str = ""
    wavelength_nm: int | None = None
    unit: str = "W"
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"backend": self.backend, "model": self.model, "serial": self.serial, "head": self.head,
                "wavelength_nm": self.wavelength_nm, "unit": self.unit, **self.extra}


def _scale(value_w: float, unit: str, aperture_cm2: float | None) -> float:
    """Convert a reading in watts to the requested display unit."""
    if unit == "W":
        return value_w
    if unit == "mW":
        return value_w * 1e3
    if unit == "mW/cm2":
        if not aperture_cm2:
            raise MeterError("mW/cm2 needs the sensor aperture area (aperture_cm2)")
        return value_w * 1e3 / aperture_cm2
    raise MeterError(f"unknown unit {unit}")


# --------------------------------------------------------------------------
#  simulated meter
# --------------------------------------------------------------------------
class SimulatedMeter:
    """Irradiance that follows the simulated machine's UV drive.

    Full-scale irradiance at 100 % is `full_scale` (default 45 mW/cm2 at the
    door opening, the order of magnitude of a 4-panel 405 nm chamber), with a
    first-order lag `tau_s` (LED + photodiode head response), 0.5 % noise and
    a small dark offset. When the door opens the machine cuts UV, so the
    reading collapses — exactly what SAF-012 measures.
    """

    def __init__(self, full_scale: float = 45.0, tau_s: float = 0.03, unit: str = "mW/cm2", dark: float = 0.02):
        self.full_scale, self.tau_s, self.unit, self.dark = full_scale, tau_s, unit, dark
        self._y = 0.0; self._t = None
        self.name = "Simulated meter"

    def connect(self) -> dict:
        from ..ui.sim import get_sim
        self.sim = get_sim(); self._t = time.monotonic()
        return MeterInfo("sim", "Simulated StarBright", "SIM-0001", "Simulated PD300-UV", 405, self.unit).as_dict()

    def _target(self) -> float:
        s = self.sim
        with s.lock:
            on, pct = s.uv_on, s.uv_pct
        return self.full_scale * pct / 100.0 if on else 0.0

    def read_all(self) -> list[tuple[float, float]]:
        now = time.monotonic(); dt = max(0.0, now - (self._t or now)); self._t = now
        target = self._target()
        self._y += (target - self._y) * (1 - math.exp(-dt / self.tau_s))
        v = self._y + self.dark + random.gauss(0, 0.005 * max(self._y, 0.2))
        return [(now, max(0.0, v))]

    def close(self):
        pass


# --------------------------------------------------------------------------
#  Ophir StarLab COM object (USB)
# --------------------------------------------------------------------------
class OphirStarLab:
    """OphirLMMeasurement COM object — ships with StarLab. Streams readings with
    the meter's own timestamps (ms); `read_all` drains the stream buffer."""

    def __init__(self, serial_no: str | None = None, channel: int = 0, unit: str = "W", aperture_cm2: float | None = None):
        self.serial_no, self.channel, self.unit, self.aperture_cm2 = serial_no, channel, unit, aperture_cm2
        self._lm = None; self._h = None; self._t0 = None; self._ts0 = None
        self.name = "Ophir StarBright (StarLab USB)"

    def connect(self) -> dict:
        try:
            import win32com.client  # type: ignore
        except ImportError as e:
            raise MeterError("StarLab COM path needs pywin32 (pip install pywin32) and Ophir StarLab installed") from e
        try:
            lm = win32com.client.Dispatch("OphirLMMeasurement.CoLMMeasurement")
        except Exception as e:  # noqa: BLE001
            raise MeterError(f"OphirLMMeasurement COM object not available — is StarLab installed? ({e})") from e
        lm.StopAllStreams(); lm.CloseAll()
        devices = list(lm.ScanUSB() or [])
        if not devices:
            raise MeterError("no Ophir USB device found (StarLab ScanUSB returned nothing)")
        target = self.serial_no or devices[0]
        if target not in devices:
            raise MeterError(f"Ophir device {target} not found; present: {', '.join(devices)}")
        h = lm.OpenUSBDevice(target)
        info = lm.GetDeviceInfo(h)            # (name, romVersion, serial)
        head = lm.GetSensorInfo(h, self.channel)   # (serial, type, name)
        try:
            wl_idx, wls = lm.GetWavelengths(h, self.channel)
            wl = wls[wl_idx] if wls else None
        except Exception:  # noqa: BLE001
            wl = None
        lm.StartStream(h, self.channel)
        self._lm, self._h = lm, h; self._t0 = time.monotonic(); self._ts0 = None
        return MeterInfo("starlab", str(info[0]), str(info[2]), f"{head[2]} ({head[0]})", int(_NUM.search(str(wl)).group()) if wl and _NUM.search(str(wl)) else None,
                         self.unit, {"rom": str(info[1])}).as_dict()

    def read_all(self) -> list[tuple[float, float]]:
        vals, ts, _status = self._lm.GetData(self._h, self.channel)
        out = []
        for v, t_ms in zip(vals, ts):
            if self._ts0 is None:
                self._ts0 = t_ms; self._t0 = time.monotonic()
            out.append((self._t0 + (t_ms - self._ts0) / 1000.0, _scale(float(v), self.unit, self.aperture_cm2)))
        return out

    def close(self):
        if self._lm is not None:
            try:
                self._lm.StopStream(self._h, self.channel); self._lm.Close(self._h)
            except Exception:  # noqa: BLE001
                pass
        self._lm = self._h = None


# --------------------------------------------------------------------------
#  Ophir serial protocol
# --------------------------------------------------------------------------
class OphirSerial:
    CMD_VERSION, CMD_HEAD, CMD_POWER, CMD_WAVELENGTH, CMD_RANGE = "$VE", "$HI", "$SP", "$WL", "$RN"

    def __init__(self, port: str, baud: int = 9600, unit: str = "W", aperture_cm2: float | None = None, timeout: float = 0.5):
        self.port, self.baud, self.unit, self.aperture_cm2, self.timeout = port, int(baud), unit, aperture_cm2, timeout
        self._ser = None
        self.name = f"Ophir StarBright (serial {port})"

    def connect(self) -> dict:
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise MeterError("serial path needs pyserial (pip install pyserial)") from e
        try:
            self._ser = serial.Serial(self.port, self.baud, bytesize=8, parity="N", stopbits=1, timeout=self.timeout)
        except Exception as e:  # noqa: BLE001
            raise MeterError(f"cannot open {self.port}: {e}") from e
        ver = self.query(self.CMD_VERSION); head = self.query(self.CMD_HEAD)
        wl = self.query(self.CMD_WAVELENGTH, allow_error=True)
        m = _NUM.search(wl or "")
        return MeterInfo("serial", ver or "StarBright", "", head or "", int(float(m.group())) if m else None, self.unit, {"port": self.port, "baud": self.baud}).as_dict()

    def query(self, cmd: str, allow_error: bool = False) -> str | None:
        self._ser.reset_input_buffer(); self._ser.write((cmd + "\r").encode("ascii"))
        raw = self._ser.read_until(b"\r").decode("ascii", "replace").strip()
        if raw.startswith("*"):
            return raw[1:].strip()
        if allow_error:
            return None
        raise MeterError(f"{cmd}: meter replied {raw!r}")

    def read_all(self) -> list[tuple[float, float]]:
        r = self.query(self.CMD_POWER)
        m = _NUM.search(r or "")
        if not m:
            raise MeterError(f"unparseable power reading {r!r}")
        return [(time.monotonic(), _scale(float(m.group()), self.unit, self.aperture_cm2))]

    def close(self):
        if self._ser is not None:
            try: self._ser.close()
            except Exception: pass  # noqa: BLE001
        self._ser = None


# --------------------------------------------------------------------------
#  factory + discovery
# --------------------------------------------------------------------------
def list_serial_ports() -> list[tuple[str, str]]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []
    return [(p.device, p.description) for p in list_ports.comports()]


def open_meter(spec: str, unit: str = "W", aperture_cm2: float | None = None, **kw):
    """Build a meter from its spec; the caller still calls connect()."""
    spec = (spec or "sim").strip()
    kind, _, rest = spec.partition(":")
    kind = kind.lower()
    if kind == "sim":
        return SimulatedMeter(unit=kw.get("sim_unit", "mW/cm2"))
    if kind == "starlab":
        return OphirStarLab(rest or None, unit=unit, aperture_cm2=aperture_cm2)
    if kind == "serial":
        port, _, baud = rest.partition(":")
        if not port:
            raise MeterError("serial spec needs a port: serial:COM3[:9600]")
        return OphirSerial(port, int(baud or 9600), unit=unit, aperture_cm2=aperture_cm2)
    raise MeterError(f"unknown meter spec {spec!r} (sim | starlab[:serial] | serial:PORT[:baud])")
