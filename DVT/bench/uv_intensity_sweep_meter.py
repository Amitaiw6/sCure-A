"""UV intensity sweep with the Ophir StarBright logged alongside the Arduino
sensors. Same staircase as uv_intensity_sweep.py; adds a meter thread that
polls the head (PD300RM, W/cm2) and writes a "meter_mw_cm2" column on every
Arduino row, plus a separate *_meter.csv with every meter sample.

The meter is driven by the UV Jig's direct WinUSB driver
(GitHub/UV Jig/tools/starbright.py). Ophir's own COM object refuses this
meter's firmware (StarLab: "Device Firmware Upgrade Required"), so ScanUSB
returns nothing - don't go that way.

Usage:
  python uv_intensity_sweep_meter.py [--host H] [--port COM3]
        [--meter usb | serial:COM5 | sim] [--meter-hz 5] [--auto-range]
        [--steps 30,...,100] [--dwell 60] [--baseline 30] [--tail 60]
        [--wavelength 450] [--out sweep.csv]
"""
import argparse, os, sys, threading, time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, r"C:\Users\User\Documents\GitHub\UV Jig\tools")
from uv_intensity_sweep import (Reader, StatePoller, discover_host, log,  # noqa: E402
                                uv_off, uv_on)
import starbright  # noqa: E402  (UV Jig driver)


class MeterThread(threading.Thread):
    """Polls meter.power() at a fixed rate; keeps the latest value (mW/cm2)."""

    def __init__(self, meter, path, hz, get_ctx):
        super().__init__(daemon=True)
        self.meter, self.path, self.period, self.get_ctx = meter, path, 1.0 / hz, get_ctx
        self.latest = float("nan")
        self.samples = 0
        self.errors = 0
        self.stop = threading.Event()
        self.t0 = time.time()

    def run(self):
        with open(self.path, "w", newline="") as f:
            f.write("host_time,elapsed_s,meter_mw_cm2,uv_intensity,phase\n")
            nxt = time.time()
            while not self.stop.is_set():
                try:
                    v = self.meter.power() * 1000.0        # W/cm2 -> mW/cm2
                except Exception as e:  # noqa: BLE001
                    self.errors += 1
                    if self.errors <= 5 or self.errors % 50 == 0:
                        log(f"!! meter read failed ({self.errors}): {e}")
                    v = float("nan")
                t = time.time()
                inten, phase = self.get_ctx()
                self.latest = v
                self.samples += 1
                f.write(f"{t:.3f},{t - self.t0:.1f},{v:.5g},{inten},{phase}\n")
                if self.samples % 10 == 0:
                    f.flush()
                nxt += self.period
                self.stop.wait(max(0.0, nxt - time.time()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--meter", default="usb")
    ap.add_argument("--meter-hz", type=float, default=5)
    ap.add_argument("--auto-range", action="store_true",
                    help="put the meter on AUTO range (default: leave as set)")
    ap.add_argument("--steps", default="30,40,50,60,70,80,90,100")
    ap.add_argument("--dwell", type=float, default=60)
    ap.add_argument("--baseline", type=float, default=30)
    ap.add_argument("--tail", type=float, default=60)
    ap.add_argument("--wavelength", type=int, default=450)
    ap.add_argument("--out", default=time.strftime("uv_sweep_%Y%m%d_%H%M%S.csv"))
    a = ap.parse_args()
    steps = [int(s) for s in a.steps.split(",") if s.strip()]

    host = a.host or discover_host()
    if not host:
        sys.exit("sCure API not found on the local network - pass --host")

    meter = starbright.open_meter(a.meter)
    info = meter.identify()
    log(f"meter: {info['instrument']} fw {info['firmware']} head {info['head']} units {info['units']}")
    if info["units"] != "w":
        log(f"!! meter units are {info['units']!r}, expected 'w' (W/cm2) - mW/cm2 column will be wrong")
    wl = meter.wavelength_nm()
    if wl != a.wavelength:
        log(f"meter wavelength {wl} nm -> setting {a.wavelength} nm")
        meter.set_wavelength(a.wavelength)
        wl = meter.wavelength_nm()
    log(f"meter wavelength {wl} nm, range {info['range_in_use']} of [{info['ranges']}]")
    if a.auto_range:
        meter.set_range(-1)
        log("meter range -> AUTO")

    log(f"sCure at {host}, Arduino on {a.port}, {a.wavelength} nm, steps {steps}, dwell {a.dwell:.0f} s")
    meter_csv = a.out.rsplit(".", 1)[0] + "_meter.csv"
    log(f"writing {a.out} and {meter_csv}")

    f = open(a.out, "w", newline="")
    f.write("host_time,elapsed_s,arduino_ms,ntc_counts,ldr_counts,uv_intensity,phase,"
            "chamber_c,led_max_c,meter_mw_cm2\n")
    t0 = time.time()
    lock = threading.Lock()
    st = StatePoller(host)
    st.start()
    ctx = {"inten": 0, "phase": "baseline"}
    mt = MeterThread(meter, meter_csv, a.meter_hz, lambda: (ctx["inten"], ctx["phase"]))
    mt.start()

    def on_row(t, ms, ntc, ldr, inten, phase):
        with lock:
            f.write(f"{t:.3f},{t - t0:.1f},{ms},{ntc},{ldr},{inten},{phase},"
                    f"{st.chamber:.1f},{st.led_max:.1f},{mt.latest:.5g}\n")
            f.flush()

    rd = Reader(a.port, on_row)
    rd.start()

    def set_ctx(inten, phase):
        rd.intensity, rd.phase = inten, phase
        ctx["inten"], ctx["phase"] = inten, phase

    def hold(seconds, label):
        end = time.time() + seconds
        nxt = time.time() + 10
        while time.time() < end:
            time.sleep(0.5)
            if time.time() >= nxt:
                nxt += 10
                log(f"  {label:>10}  {end - time.time():4.0f} s left  {rd.summary()}"
                    f"  meter {mt.latest:.3f} mW/cm2  LED max {st.led_max:.1f} C")

    try:
        uv_off(host)
        set_ctx(0, "baseline")
        log(f"baseline (UV off) for {a.baseline:.0f} s")
        hold(a.baseline, "baseline")
        for inten in steps:
            uv_on(host, inten, a.wavelength)
            set_ctx(inten, "step")
            log(f"UV {a.wavelength} nm @ {inten}% for {a.dwell:.0f} s")
            hold(a.dwell, f"{inten}%")
            log(f"  {inten}% done: {rd.summary()}  meter {mt.latest:.3f} mW/cm2")
        uv_off(host)
        set_ctx(0, "tail")
        log(f"cool-down (UV off) for {a.tail:.0f} s")
        hold(a.tail, "tail")
    except KeyboardInterrupt:
        log("interrupted")
    except Exception as e:  # noqa: BLE001
        log(f"!! {e}")
    finally:
        uv_off(host)
        rd.stop.set()
        st.stop.set()
        mt.stop.set()
        mt.join(3)
        meter.close()
        with lock:
            f.close()
        log(f"saved {a.out} ({rd.rows} rows) and {meter_csv} "
            f"({mt.samples} meter samples, {mt.errors} read errors)")


if __name__ == "__main__":
    main()
