"""Live viewer for the Ophir *_meter.csv written by uv_intensity_sweep_meter.py.
Usage: python uv_meter_live.py sweep_meter.csv ["450 sweep"]
Re-reads the file every 2 s: irradiance (mW/cm2) vs time + the UV staircase."""
import csv, sys, math
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

src = sys.argv[1]
title = sys.argv[2] if len(sys.argv) > 2 else "UV sweep"


def load():
    t, v, uv = [], [], []
    try:
        with open(src, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    x = float(r["meter_mw_cm2"])
                    if math.isnan(x):
                        continue
                    t.append(float(r["elapsed_s"])); v.append(x); uv.append(int(r["uv_intensity"]))
                except (KeyError, ValueError, TypeError):
                    pass
    except FileNotFoundError:
        pass
    return t, v, uv


fig, ax = plt.subplots(figsize=(11, 6))
axu = ax.twinx()
l_v, = ax.plot([], [], color="#0f766e", lw=1.2, label="Ophir PD300RM irradiance (mW/cm²)")
l_uv, = axu.step([], [], where="post", color="#6b7280", ls="--", lw=1, label="UV intensity %")
ax.set_xlabel("time (s)"); ax.set_ylabel("irradiance (mW/cm²)"); ax.grid(alpha=.3)
axu.set_ylabel("UV intensity (%)"); axu.set_ylim(0, 110)
h1, n1 = ax.get_legend_handles_labels(); h2, n2 = axu.get_legend_handles_labels()
ax.legend(h1 + h2, n1 + n2, loc="upper left")
fig.canvas.manager.set_window_title(f"{title} - UV intensity (Ophir)")


def update(_):
    t, v, uv = load()
    if not t:
        return
    l_v.set_data(t, v); l_uv.set_data(t, uv)
    ax.set_xlim(0, max(t[-1] + 5, 60)); ax.set_ylim(0, max(v) * 1.1 + 0.1)
    ax.set_title(f"{title}  t={t[-1]:.0f}s  UV {uv[-1]}%  meter {v[-1]:.2f} mW/cm²")


ani = FuncAnimation(fig, update, interval=2000, cache_frame_data=False)
plt.show()
