#!/usr/bin/env python3
"""
compare_delta_live.py - live window comparing the delta (actual - reported)
of the current heat-up against a previous reference heat-up.

Both runs are aligned to their ramp start (minimum of the actual-temperature
curve), so the x axis is minutes into the ramp. The reference is drawn once;
the current run's curve grows as its capture log fills.

Usage:
    python compare_delta_live.py --ref <log> [<log> ...] --cur <log> [<log> ...]
"""

import argparse
import matplotlib.pyplot as plt

from live_temp_graph import (read_series, SURFACE, INK, MUTED, GRID, BASELINE,
                             ACTUAL_COLOR, SCURE_COLOR)


def delta_vs_ramp_minutes(logs):
    """(minutes-from-ramp-start, delta) for a capture; ramp start = min actual."""
    times, raws, actuals = read_series(logs)
    if not times:
        return [], []
    i0 = actuals.index(min(actuals))
    t0 = times[i0]
    mins = [(t - t0).total_seconds() / 60.0 for t in times[i0:]]
    deltas = [a - r for a, r in zip(actuals[i0:], raws[i0:])]
    return mins, deltas


def main():
    ap = argparse.ArgumentParser(description="Live delta comparison between heat-ups.")
    ap.add_argument("--ref", nargs="+", required=True, help="previous heat-up log(s)")
    ap.add_argument("--cur", nargs="+", required=True, help="current heat-up log(s)")
    args = ap.parse_args()

    plt.rcParams["toolbar"] = "None"
    fig, ax = plt.subplots(figsize=(11, 6), facecolor=SURFACE)
    fig.canvas.manager.set_window_title("Delta comparison - previous vs current heat-up")

    ref_m, ref_d = delta_vs_ramp_minutes(args.ref)
    while plt.fignum_exists(fig.number):
        cur_m, cur_d = delta_vs_ramp_minutes(args.cur)
        ax.clear()
        ax.set_facecolor(SURFACE)
        ax.axhline(0, color=BASELINE, linewidth=1)
        if ref_m:
            ax.plot(ref_m, ref_d, color=SCURE_COLOR, linewidth=2,
                    label="Previous heat-up (uncorrected)")
            ax.annotate("previous", (ref_m[-1], ref_d[-1]), xytext=(8, 0),
                        textcoords="offset points", color=INK, fontsize=10, va="center")
        if cur_m:
            ax.plot(cur_m, cur_d, color=ACTUAL_COLOR, linewidth=2,
                    label="Current heat-up (corrected)")
            ax.annotate(f"current {cur_d[-1]:+.2f}", (cur_m[-1], cur_d[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        color=INK, fontsize=10, va="center")
            ax.set_title(
                f"Delta vs minutes into ramp - current {cur_d[-1]:+.2f} \N{DEGREE SIGN}C, "
                f"previous ended {ref_d[-1]:+.2f} \N{DEGREE SIGN}C",
                color=INK, fontsize=12, loc="left", pad=12)
        leg = ax.legend(loc="upper right", frameon=False, fontsize=10)
        for text in leg.get_texts():
            text.set_color(INK)
        ax.set_xlabel("minutes since ramp start", color=MUTED)
        ax.set_ylabel("actual \N{MINUS SIGN} reported (\N{DEGREE SIGN}C)", color=MUTED)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BASELINE)
        fig.tight_layout()
        plt.pause(2)


if __name__ == "__main__":
    main()
