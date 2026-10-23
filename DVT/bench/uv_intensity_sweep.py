"""UV intensity sweep: log thermistor (A0) + photoresistor (A1) raw counts from
the Arduino while stepping the sCure LED power through a list of intensities.

Usage:
  python uv_intensity_sweep.py [--host 192.168.x.y] [--port COM3]
                               [--steps 30,40,50,60,70,80,90,100]
                               [--dwell 60] [--baseline 30] [--tail 60]
                               [--wavelength 405] [--out sweep.csv]

Sequence: baseline (UV off) -> each step held for --dwell seconds -> UV off,
--tail seconds of cool-down. UV is always switched off on exit, including
Ctrl+C or an API error. --host omitted = scan the local /24 for port 3001.
Requires uv_sensors.ino on the Uno (115200 baud, "ms,ntc,ldr").
"""
import argparse, socket, sys, threading, time, urllib.request, urllib.error
import concurrent.futures as cf
from collections import deque

import serial

API_PORT = 3001


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- sCure API
def discover_host():
    """Return the first host on this PC's /24 with port 3001 open."""
    me = socket.gethostbyname(socket.gethostname())
    base = me.rsplit(".", 1)[0]

    def probe(h):
        s = socket.socket()
        s.settimeout(0.6)
        try:
            s.connect((h, API_PORT))
            return h
        except OSError:
            return None
        finally:
            s.close()

    with cf.ThreadPoolExecutor(64) as ex:
        for h in ex.map(probe, [f"{base}.{i}" for i in range(1, 255)]):
            if h:
                return h
    return None


def api_post(host, path):
    req = urllib.request.Request(f"http://{host}:{API_PORT}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        body = r.read().decode()
    if '"ok": true' not in body and '"ok":true' not in body:
        raise RuntimeError(f"API refused {path}: {body[:200]}")
    return body


def uv_on(host, intensity, wavelength):
    return api_post(host, f"/api/uv?on=1&intensity={intensity}&wavelength={wavelength}")


def uv_off(host):
    try:
        api_post(host, "/api/uv?on=0")
        log("UV OFF")
    except Exception as e:  # noqa: BLE001 - report but never raise on the way out
        log(f"!! failed to switch UV off: {e}")


class StatePoller(threading.Thread):
    """Polls /api/state every 2 s for chamber temp and the hottest LED zone."""

    def __init__(self, host):
        super().__init__(daemon=True)
        self.host = host
        self.chamber = float("nan")
        self.led_max = float("nan")
        self.stop = threading.Event()

    def run(self):
        import json
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen(
                        f"http://{self.host}:{API_PORT}/api/state", timeout=4) as r:
                    d = json.load(r)
                self.chamber = float(d.get("chamberTemp", "nan"))
                temps = [v for v in (d.get("ledTemps") or {}).values()
                         if isinstance(v, (int, float))]
                self.led_max = max(temps) if temps else float("nan")
            except Exception:  # noqa: BLE001 - keep last values on a hiccup
                pass
            self.stop.wait(2)


# ------------------------------------------------------------- serial reader
class Reader(threading.Thread):
    """Reads "ms,ntc,ldr" lines and hands them to a callback with the current
    intensity stamped in. Keeps the last few seconds for step summaries."""

    def __init__(self, port, on_row):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, 115200, timeout=1)
        self.on_row = on_row
        self.intensity = 0
        self.phase = "baseline"
        self.recent = deque(maxlen=25)   # ~5 s at 200 ms
        self.stop = threading.Event()
        self.rows = 0

    def run(self):
        time.sleep(2)                    # Uno resets when the port opens
        self.ser.reset_input_buffer()
        while not self.stop.is_set():
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line or line.startswith("ms"):
                continue
            try:
                ms, ntc, ldr = (int(x) for x in line.split(","))
            except ValueError:
                continue
            self.recent.append((ntc, ldr))
            self.rows += 1
            self.on_row(time.time(), ms, ntc, ldr, self.intensity, self.phase)

    def summary(self):
        if not self.recent:
            return "no data"
        n = len(self.recent)
        ntc = sum(r[0] for r in self.recent) / n
        ldr = sum(r[1] for r in self.recent) / n
        return f"NTC {ntc:6.1f}  LDR {ldr:6.1f}  (mean of last {n} samples)"


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--steps", default="30,40,50,60,70,80,90,100")
    ap.add_argument("--dwell", type=float, default=60)
    ap.add_argument("--baseline", type=float, default=30)
    ap.add_argument("--tail", type=float, default=60)
    ap.add_argument("--wavelength", type=int, default=405)
    ap.add_argument("--out", default=time.strftime("uv_sweep_%Y%m%d_%H%M%S.csv"))
    a = ap.parse_args()
    steps = [int(s) for s in a.steps.split(",") if s.strip()]

    host = a.host or discover_host()
    if not host:
        sys.exit("sCure API not found on the local network - pass --host")
    log(f"sCure at {host}, Arduino on {a.port}, steps {steps}, dwell {a.dwell:.0f} s")
    log(f"writing {a.out}")

    f = open(a.out, "w", newline="")
    f.write("host_time,elapsed_s,arduino_ms,ntc_counts,ldr_counts,uv_intensity,phase,"
            "chamber_c,led_max_c\n")
    t0 = time.time()
    lock = threading.Lock()
    st = StatePoller(host)
    st.start()

    def on_row(t, ms, ntc, ldr, inten, phase):
        with lock:
            f.write(f"{t:.3f},{t - t0:.1f},{ms},{ntc},{ldr},{inten},{phase},"
                    f"{st.chamber:.1f},{st.led_max:.1f}\n")
            f.flush()   # keep the file current for live viewers / a crash

    rd = Reader(a.port, on_row)
    rd.start()

    def hold(seconds, label):
        end = time.time() + seconds
        next_print = time.time() + 10
        while time.time() < end:
            time.sleep(0.5)
            if time.time() >= next_print:
                next_print += 10
                log(f"  {label:>10}  {end - time.time():4.0f} s left  {rd.summary()}"
                    f"  chamber {st.chamber:.1f} C  LED max {st.led_max:.1f} C")

    try:
        uv_off(host)                       # known state before baseline
        rd.intensity, rd.phase = 0, "baseline"
        log(f"baseline (UV off) for {a.baseline:.0f} s")
        hold(a.baseline, "baseline")
        log(f"  baseline done: {rd.summary()}")

        for inten in steps:
            uv_on(host, inten, a.wavelength)
            rd.intensity, rd.phase = inten, "step"
            log(f"UV {a.wavelength} nm @ {inten}% for {a.dwell:.0f} s")
            hold(a.dwell, f"{inten}%")
            log(f"  {inten}% done: {rd.summary()}")

        uv_off(host)
        rd.intensity, rd.phase = 0, "tail"
        log(f"cool-down (UV off) for {a.tail:.0f} s")
        hold(a.tail, "tail")
        log(f"  tail done: {rd.summary()}")
    except KeyboardInterrupt:
        log("interrupted")
    except Exception as e:  # noqa: BLE001
        log(f"!! {e}")
    finally:
        uv_off(host)
        rd.stop.set()
        st.stop.set()
        with lock:
            f.close()
        log(f"saved {a.out} ({rd.rows} rows)")


if __name__ == "__main__":
    main()
