"""Ophir StarBright over USB with pyusb (libusb) — for the Raspberry Pi.

The meter answers Ophir's ASCII user commands ("$XX" -> "*reply" / "?error")
carried in two vendor control transfers, exactly what Ophir's own driver and
the UV Jig's WinUSB driver do:

    OUT  bmRequestType 0x40, bRequest 2 : "$XX\\r\\n"
    IN   bmRequestType 0xC0, bRequest 4 : the reply (up to 4096 bytes)

No Ophir software is involved (StarLab refuses this meter's firmware anyway).
Needs pyusb + libusb; the sCure service runs as root, so no udev rule is
required for the Flask server. A plain user gets "Access denied" — use the
/api/dvt/meter endpoint, or add a udev rule for VID 0bd3.

    from starbright_usb import StarBright, find_meter
    with StarBright() as m:
        m.identify(); m.wavelength_nm(); m.power_mw_cm2()
"""

from __future__ import annotations

import time

VID_OPHIR = 0x0BD3
UNIT_NAMES = {"w": "W/cm2", "W": "W", "j": "J/cm2", "J": "J", "d": "dBm", "X": "(passive)", "l": "lux", "c": "fc", "u": "lm"}


class StarBrightError(RuntimeError):
    pass


def _usb():
    try:
        import usb.core  # type: ignore
        import usb.util  # type: ignore  # noqa: F401
        return usb
    except ImportError as e:
        raise StarBrightError("pyusb is not installed (pip install pyusb) — the StarBright needs it over USB") from e


def find_meter():
    """The first Ophir USB device present, or None."""
    usb = _usb()
    return usb.core.find(idVendor=VID_OPHIR)


class StarBright:
    def __init__(self, timeout_ms: int = 6000):
        usb = _usb()
        dev = usb.core.find(idVendor=VID_OPHIR)
        if dev is None:
            raise StarBrightError("no Ophir StarBright on USB — plug the meter into the machine and switch it on")
        self.dev, self.timeout = dev, timeout_ms
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except Exception:  # noqa: BLE001 - no kernel driver bound, or not supported: fine
            pass
        try:
            dev.set_configuration()
        except Exception as e:  # noqa: BLE001
            if "denied" in str(e).lower() or "permission" in str(e).lower():
                raise StarBrightError(f"USB access denied ({e}) — the server must run as root or a udev rule must allow VID 0bd3") from e
            # already configured by a previous open: usable anyway
        self.path = f"usb:{dev.bus}-{dev.address}"
        self.transport = "usb"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        try:
            import usb.util  # type: ignore
            usb.util.dispose_resources(self.dev)
        except Exception:  # noqa: BLE001
            pass

    # ---- protocol
    def query(self, cmd: str) -> str:
        data = (f"${cmd}\r\n").encode("ascii")
        try:
            self.dev.ctrl_transfer(0x40, 2, 0, 0, data, timeout=self.timeout)
            raw = self.dev.ctrl_transfer(0xC0, 4, 0, 0, 4096, timeout=self.timeout)
        except Exception as e:  # noqa: BLE001
            raise StarBrightError(f"'{cmd}': USB transfer failed ({e})") from e
        reply = bytes(raw).decode("ascii", "replace").strip("\r\n \x00")
        if reply.startswith("*"):
            return reply[1:].strip()
        raise StarBrightError(f"'{cmd}' -> {reply!r}")

    # ---- convenience
    def identify(self) -> dict:
        info = {"transport": "usb", "path": self.path}
        for key, cmd in (("firmware", "VE"), ("instrument", "II"), ("head", "HI"), ("head_type", "HT"), ("units", "SI"),
                         ("ranges", "AR"), ("range_in_use", "GU"), ("wavelengths", "AW"), ("measurement_mode", "MM")):
            try:
                info[key] = self.query(cmd)
            except StarBrightError as e:
                info[key] = None; info.setdefault("errors", []).append(str(e))
        info["unit_name"] = UNIT_NAMES.get(info.get("units") or "", info.get("units"))
        info["wavelength_nm"] = self.wavelength_nm()
        return info

    def wavelength_nm(self) -> int | None:
        """The wavelength the meter is set to (from the AW favourites list)."""
        try:
            f = self.query("AW").split()
        except StarBrightError:
            return None
        if f and f[0] == "CONTINUOUS":
            try:
                return int(f[3 + int(f[3])])          # 1-based index into the favourites after lo/hi/idx
            except (IndexError, ValueError):
                return None
        try:
            return int(f[int(f[0])]) if f else None  # discrete list: "<idx> <wl1> <wl2> ..."
        except (IndexError, ValueError):
            return None

    def set_wavelength(self, nm: int) -> None:
        self.query(f"WL {int(nm)}")

    def set_range(self, index: int) -> None:
        """-1 = AUTO, 0 = highest numeric range, 1 = next lower, ..."""
        self.query(f"WN {int(index)}")

    def power_raw(self) -> float | None:
        """One reading in the meter's units (SI); None while the meter says 'over'/auto-ranges."""
        try:
            return float(self.query("SP"))
        except (StarBrightError, ValueError):
            return None

    def power_mw_cm2(self) -> float | None:
        """Reading converted to mW/cm2 when the head reports W/cm2 (PD300RM); otherwise the raw value x 1000 (W -> mW)."""
        v = self.power_raw()
        return None if v is None else v * 1000.0


if __name__ == "__main__":
    with StarBright() as m:
        for k, v in m.identify().items():
            print(f"{k:16}: {v}")
        for _ in range(5):
            print(time.strftime("%H:%M:%S"), m.power_mw_cm2(), "mW/cm2"); time.sleep(0.5)
