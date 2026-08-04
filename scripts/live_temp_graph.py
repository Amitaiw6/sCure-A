#!/usr/bin/env python3
"""
live_temp_graph.py - live window tracking sCure sensor vs actual (TC-08) temps,
with the heater PWM in a panel below (same time axis, separate scale).

Temperatures are NOT read from the TC-08 directly - the viewer tails the log
that calibrate_scure_temp.py is already writing (the device allows one
connection), so it can run alongside the calibration. PWM is polled live from
the sCure API by the viewer itself.

Usage:
    python live_temp_graph.py <calibration-log> [<another-log> ...]
        [--host 192.168.154.141]
    (multiple logs are merged and sorted by time - e.g. a restarted run)
"""

import argparse
import datetime as dt
import json
import re
import urllib.request

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SURFACE, INK, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
ACTUAL_COLOR, SCURE_COLOR = "#2a78d6", "#eb6834"      # categorical slots 1-2
PWM_COLOR, COOL_COLOR = "#1baf7a", "#4a3aa7"          # slots 3 and 7
DELTA_COLOR = "#e87ba4"                               # slot 5

LINE = re.compile(r"(\d\d:\d\d:\d\d)\s+raw\s+(-?\d+\.?\d*)\s+actual\s+(-?\d+\.?\d*)")


def read_series(paths):
    if isinstance(paths, str):
        paths = [paths]
    rows = []
    today = dt.date.today()
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = LINE.search(line)
                    if m:
                        t = dt.datetime.combine(
                            today, dt.datetime.strptime(m.group(1), "%H:%M:%S").time())
                        rows.append((t, float(m.group(2)), float(m.group(3))))
        except OSError:
            pass
    rows.sort(key=lambda r: r[0])
    times = [r[0] for r in rows]
    raws = [r[1] for r in rows]
    actuals = [r[2] for r in rows]
    return times, raws, actuals


def poll_pwm(host):
    """(heater %, cooling fan %) - 0 when the API reports none; None on error."""
    try:
        with urllib.request.urlopen(f"http://{host}:3001/api/state", timeout=4) as r:
            d = json.load(r)
            heat = d.get("heaterPwm")
            cool = d.get("coolingFanPwm")
            return (float(heat) if heat is not None else 0.0,
                    float(cool) if cool is not None else 0.0)
    except Exception:
        return None


def style_axis(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)


def main():
    ap = argparse.ArgumentParser(description="Live sCure vs actual temps + heater PWM.")
    ap.add_argument("logs", nargs="+", help="calibration output log(s)")
    ap.add_argument("--host", default="192.168.154.141")
    args = ap.parse_args()

    plt.rcParams["toolbar"] = "None"
    fig, (ax_t, ax_d, ax_p) = plt.subplots(
        3, 1, figsize=(11, 9), sharex=True, facecolor=SURFACE,
        gridspec_kw={"height_ratios": [3, 1.3, 1], "hspace": 0.14})
    fig.canvas.manager.set_window_title("sCure vs actual temperature - live")

    pwm_hist = []   # (datetime, heater %, cooling fan %)
    while plt.fignum_exists(fig.number):
        times, raws, actuals = read_series(args.logs)
        pwm = poll_pwm(args.host)
        if pwm is not None:
            pwm_hist.append((dt.datetime.now(),) + pwm)

        ax_t.clear()
        ax_d.clear()
        ax_p.clear()
        style_axis(ax_t)
        style_axis(ax_d)
        style_axis(ax_p)

        if times:
            ax_t.plot(times, actuals, color=ACTUAL_COLOR, linewidth=2,
                      label="Actual (PicoLog avg)")
            ax_t.plot(times, raws, color=SCURE_COLOR, linewidth=2, label="sCure sensor")
            delta = actuals[-1] - raws[-1]
            if pwm_hist:
                pwm_now = f"heat {pwm_hist[-1][1]:.0f}%  cool {pwm_hist[-1][2]:.0f}%"
            else:
                pwm_now = "-"
            ax_t.set_title(
                f"Actual {actuals[-1]:.2f} \N{DEGREE SIGN}C   "
                f"sCure {raws[-1]:.2f} \N{DEGREE SIGN}C   "
                f"delta {delta:+.2f} \N{DEGREE SIGN}C   "
                f"PWM {pwm_now}   ({len(times)} samples)",
                color=INK, fontsize=12, loc="left", pad=12)
            ax_t.annotate("Actual", (times[-1], actuals[-1]), xytext=(8, 0),
                          textcoords="offset points", color=INK, fontsize=10, va="center")
            ax_t.annotate("sCure", (times[-1], raws[-1]), xytext=(8, 0),
                          textcoords="offset points", color=INK, fontsize=10, va="center")
            leg = ax_t.legend(loc="upper left", frameon=False, fontsize=10)
            for text in leg.get_texts():
                text.set_color(INK)
        else:
            ax_t.text(0.5, 0.5, "waiting for samples...", transform=ax_t.transAxes,
                      ha="center", color=MUTED)
        ax_t.set_ylabel("\N{DEGREE SIGN}C", color=MUTED)

        if times:
            deltas = [a - r for a, r in zip(actuals, raws)]
            ax_d.axhline(0, color=BASELINE, linewidth=1)
            ax_d.plot(times, deltas, color=DELTA_COLOR, linewidth=2)
            ax_d.annotate(f"delta {deltas[-1]:+.2f}", (times[-1], deltas[-1]),
                          xytext=(8, 0), textcoords="offset points",
                          color=INK, fontsize=10, va="center")
        ax_d.set_ylabel("actual \N{MINUS SIGN} sCure (\N{DEGREE SIGN}C)", color=MUTED)

        if pwm_hist:
            pt, heat, cool = zip(*pwm_hist)
            ax_p.plot(pt, heat, color=PWM_COLOR, linewidth=2)
            ax_p.plot(pt, cool, color=COOL_COLOR, linewidth=2)
            ax_p.annotate("Heater", (pt[-1], heat[-1]), xytext=(8, 0),
                          textcoords="offset points", color=INK, fontsize=10, va="center")
            ax_p.annotate("Cooling fan", (pt[-1], cool[-1]), xytext=(8, -12),
                          textcoords="offset points", color=INK, fontsize=10, va="center")
        ax_p.set_ylabel("PWM %", color=MUTED)
        ax_p.set_ylim(-5, 105)
        ax_p.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

        fig.tight_layout()
        plt.pause(2)


if __name__ == "__main__":
    main()
