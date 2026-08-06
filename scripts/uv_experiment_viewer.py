#!/usr/bin/env python3
"""
uv_experiment_viewer.py - live window for the UV/LED experiment.

Tails the uv_led_experiment.py log: LED temperature (TC-08 average) on top,
the commanded UV intensity staircase below, shared time axis.

Usage:
    python uv_experiment_viewer.py <experiment-log>
"""

import datetime as dt
import re
import sys

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SURFACE, INK, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
TEMP_COLOR, UV_COLOR = "#2a78d6", "#eb6834"

LINE = re.compile(r"(\d\d:\d\d:\d\d)\s+uv\s+(\d+)\s+temp\s+(-?\d+\.?\d*)")
STEP = re.compile(r"STEP (\d+)% -> (-?\d+\.?\d*) C")


def read_log(path):
    rows, steps = [], []
    today = dt.date.today()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.search(line)
                if m:
                    t = dt.datetime.combine(
                        today, dt.datetime.strptime(m.group(1), "%H:%M:%S").time())
                    rows.append((t, int(m.group(2)), float(m.group(3))))
                    continue
                s = STEP.search(line)
                if s:
                    steps.append((int(s.group(1)), float(s.group(2))))
    except OSError:
        pass
    return rows, steps


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: uv_experiment_viewer.py <experiment-log>")
    path = sys.argv[1]

    plt.rcParams["toolbar"] = "None"
    fig, (ax_t, ax_u) = plt.subplots(
        2, 1, figsize=(11, 7.5), sharex=True, facecolor=SURFACE,
        gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.12})
    fig.canvas.manager.set_window_title("LED temp vs UV intensity - live")

    while plt.fignum_exists(fig.number):
        rows, steps = read_log(path)
        ax_t.clear()
        ax_u.clear()
        style(ax_t)
        style(ax_u)
        if rows:
            ts = [r[0] for r in rows]
            uv = [r[1] for r in rows]
            temp = [r[2] for r in rows]
            ax_t.plot(ts, temp, color=TEMP_COLOR, linewidth=2)
            ax_t.annotate("LED temp", (ts[-1], temp[-1]), xytext=(8, 0),
                          textcoords="offset points", color=INK, fontsize=10,
                          va="center")
            done = f", {len(steps)} steps settled" if steps else ""
            ax_t.set_title(
                f"UV {uv[-1]}%   LED temp {temp[-1]:.2f} \N{DEGREE SIGN}C   "
                f"({len(rows)} samples{done})",
                color=INK, fontsize=12, loc="left", pad=12)
            ax_u.plot(ts, uv, color=UV_COLOR, linewidth=2, drawstyle="steps-post")
            ax_u.annotate("UV %", (ts[-1], uv[-1]), xytext=(8, 0),
                          textcoords="offset points", color=INK, fontsize=10,
                          va="center")
            ax_u.set_ylim(0, 105)
            ax_u.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        else:
            ax_t.text(0.5, 0.5, "waiting for samples...", transform=ax_t.transAxes,
                      ha="center", color=MUTED)
        ax_t.set_ylabel("\N{DEGREE SIGN}C", color=MUTED)
        ax_u.set_ylabel("UV %", color=MUTED)
        fig.tight_layout()
        plt.pause(2)


if __name__ == "__main__":
    main()
