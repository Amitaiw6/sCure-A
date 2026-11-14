#!/usr/bin/env python3
"""Live log of the sCure N2 line pressure (SMC ISE20 analog output, /api/state.n2Pressure).

    python scripts/pressure_log.py                      # machine on localhost:3001
    python scripts/pressure_log.py --host 192.168.154.142
    python scripts/pressure_log.py --csv pressure.csv   # also append rows to a CSV

One line per second: time, ADC volts on U7 AIN3, MPa / bar (or CLAMPED when the
ADC input is above its 3.3 V supply), line OK/LOW against the set point, and
the N2 valve state. Needs a server build >= 0.8.59.
"""
import argparse
import csv
import json
import sys
import time
import urllib.request


def fetch(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description="live N2 line pressure log")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3001)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between readings")
    ap.add_argument("--csv", help="append readings to this CSV file")
    a = ap.parse_args()
    url = "http://%s:%d/api/state" % (a.host, a.port)
    writer = None
    if a.csv:
        f = open(a.csv, "a", newline="")
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(["time", "volts", "mpa", "bar", "on", "saturated", "nitrogen_valve"])
    print("N2 pressure log from %s  (Ctrl+C to stop)" % url)
    try:
        while True:
            stamp = time.strftime("%H:%M:%S")
            try:
                st = fetch(url)
            except Exception as e:            # noqa: BLE001
                print("%s  API unreachable: %s" % (stamp, e))
                time.sleep(a.interval)
                continue
            n2 = "N2 valve OPEN" if st.get("nitrogenActive") else "N2 valve closed"
            p = st.get("n2Pressure", "missing")
            if p == "missing":
                print("%s  server has no n2Pressure field (needs build >= 0.8.59)   %s" % (stamp, n2))
            elif p is None:
                print("%s  ADC read failed (U7 AIN3)   %s" % (stamp, n2))
            else:
                if p.get("mpa") is None:
                    value = "CLAMPED (above the ADC range, fit a divider)" if p.get("saturated") else "no value (%s mode)" % p.get("mode")
                else:
                    value = "%6.3f MPa = %5.2f bar" % (p["mpa"], p["bar"])
                state = "line OK" if p.get("on") else "line LOW"
                print("%s  %6.3f V   %s   %s (set point %s MPa)   %s" % (stamp, p["volts"], value, state, p.get("setPointMPa"), n2))
                if writer:
                    writer.writerow([stamp, p["volts"], p.get("mpa"), p.get("bar"), p.get("on"), p.get("saturated"), st.get("nitrogenActive")])
            sys.stdout.flush()
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
