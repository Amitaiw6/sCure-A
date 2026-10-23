"""Single-zone sensitivity test: run all four LED zones at 100% until the
thermistor reaches steady state, drop ONLY one zone to a lower level, hold,
restore 100%, hold, then UV off. Logs both Arduino sensors at 200 ms.

Usage:
  python uv_zone_test.py [--host H] [--port COM3] [--zone right] [--low 50]
                         [--min-hold 180] [--max-hold 600] [--steady 2.0]
                         [--low-hold 180] [--restore-hold 120] [--tail 60]
                         [--out zone.csv]

Uses POST /api/dev/led-power with unsaved preview factors (nothing is written
to the machine's calibration). UV is always switched off on exit.
"""
import argparse, json, sys, threading, time, urllib.request
from collections import deque

sys.path.insert(0, __import__("os").path.dirname(__file__))
from uv_intensity_sweep import (API_PORT, Reader, StatePoller, discover_host,   # noqa: E402
                                log, uv_off)

ZONES = ("back", "door", "left", "right")


def led_power(host, power, factors):
    body = json.dumps({"power": power, "factors": factors}).encode()
    req = urllib.request.Request(f"http://{host}:{API_PORT}/api/dev/led-power",
                                 data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = json.load(r)
    if not d.get("ok"):
        raise RuntimeError(f"led-power refused: {d.get('message')}")
    log(f"LED outputs: {d.get('outputs')}")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--zone", default="right", choices=ZONES)
    ap.add_argument("--low", type=float, default=50)
    ap.add_argument("--min-hold", type=float, default=180)
    ap.add_argument("--max-hold", type=float, default=600)
    ap.add_argument("--steady", type=float, default=2.0,
                    help="steady when |mean(last 30 s) - mean(prior 30 s)| < this (counts)")
    ap.add_argument("--low-hold", type=float, default=180)
    ap.add_argument("--restore-hold", type=float, default=120)
    ap.add_argument("--tail", type=float, default=60)
    ap.add_argument("--out", default=time.strftime("uv_zone_%Y%m%d_%H%M%S.csv"))
    a = ap.parse_args()

    host = a.host or discover_host()
    if not host:
        sys.exit("sCure API not found - pass --host")
    log(f"sCure at {host}, Arduino on {a.port}, zone {a.zone} -> {a.low:.0f}%")
    log(f"writing {a.out}")

    f = open(a.out, "w", newline="")
    f.write("host_time,elapsed_s,arduino_ms,ntc_counts,ldr_counts,uv_intensity,phase,"
            f"chamber_c,led_max_c,{a.zone}_pct\n")
    t0 = time.time()
    lock = threading.Lock()
    st = StatePoller(host)
    st.start()
    zone_pct = {"v": 0}
    history = deque()       # (t, ntc) for steady-state detection

    def on_row(t, ms, ntc, ldr, inten, phase):
        history.append((t, ntc))
        while history and history[0][0] < t - 60:
            history.popleft()
        with lock:
            f.write(f"{t:.3f},{t - t0:.1f},{ms},{ntc},{ldr},{inten},{phase},"
                    f"{st.chamber:.1f},{st.led_max:.1f},{zone_pct['v']}\n")
            f.flush()

    rd = Reader(a.port, on_row)
    rd.start()

    def status(label, left):
        log(f"  {label:>12}  {left:4.0f} s left  {rd.summary()}"
            f"  chamber {st.chamber:.1f} C  LED max {st.led_max:.1f} C")

    def hold(seconds, label):
        end = time.time() + seconds
        nxt = time.time() + 10
        while time.time() < end:
            time.sleep(0.5)
            if time.time() >= nxt:
                nxt += 10
                status(label, end - time.time())

    def ntc_drift():
        """mean(last 30 s) - mean(30 s before that), in counts."""
        now = time.time()
        a_ = [v for t, v in history if t >= now - 30]
        b_ = [v for t, v in history if now - 60 <= t < now - 30]
        if len(a_) < 20 or len(b_) < 20:
            return float("nan")
        return sum(a_) / len(a_) - sum(b_) / len(b_)

    full = {z: 1.0 for z in ZONES}
    low = dict(full, **{a.zone: a.low / 100.0})

    try:
        uv_off(host)
        rd.intensity, rd.phase, zone_pct["v"] = 0, "baseline", 0
        log("baseline (UV off) 20 s")
        hold(20, "baseline")

        led_power(host, 100, full)
        rd.intensity, rd.phase, zone_pct["v"] = 100, "all100", 100
        log(f"all zones 100% - waiting for thermistor steady state "
            f"(min {a.min_hold:.0f} s, max {a.max_hold:.0f} s, drift < {a.steady} counts/30 s)")
        t_start = time.time()
        nxt = time.time() + 10
        while True:
            time.sleep(0.5)
            el = time.time() - t_start
            d = ntc_drift()
            if time.time() >= nxt:
                nxt += 10
                log(f"  all100  {el:4.0f} s  drift {d:+.1f}  {rd.summary()}"
                    f"  LED max {st.led_max:.1f} C")
            if el >= a.min_hold and d == d and abs(d) < a.steady:
                log(f"  steady after {el:.0f} s (drift {d:+.1f})")
                break
            if el >= a.max_hold:
                log(f"  max hold reached (drift {d:+.1f}) - continuing anyway")
                break
        log(f"  all100 settled: {rd.summary()}")

        led_power(host, 100, low)
        rd.intensity, rd.phase, zone_pct["v"] = 100, f"{a.zone}{a.low:.0f}", int(a.low)
        log(f"{a.zone} zone -> {a.low:.0f}%, others 100%, hold {a.low_hold:.0f} s")
        hold(a.low_hold, f"{a.zone}{a.low:.0f}")
        log(f"  {a.zone}{a.low:.0f} settled: {rd.summary()}")

        led_power(host, 100, full)
        rd.intensity, rd.phase, zone_pct["v"] = 100, "restore100", 100
        log(f"all zones back to 100%, hold {a.restore_hold:.0f} s")
        hold(a.restore_hold, "restore100")
        log(f"  restore100 settled: {rd.summary()}")

        uv_off(host)
        rd.intensity, rd.phase, zone_pct["v"] = 0, "tail", 0
        log(f"cool-down (UV off) {a.tail:.0f} s")
        hold(a.tail, "tail")
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
