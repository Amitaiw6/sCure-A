"""Live viewer for a uv_intensity_sweep.py CSV that is still being written.
Usage: python uv_sweep_live.py sweep.csv
Re-reads the file every 2 s and redraws both sensors + the UV staircase."""
import csv, sys
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

src = sys.argv[1]
title = sys.argv[2] if len(sys.argv) > 2 else "UV sweep"
label_a0 = sys.argv[3] if len(sys.argv) > 3 else "thermistor A0 (counts)"
label_a1 = sys.argv[4] if len(sys.argv) > 4 else "photoresistor A1 (counts)"
zoom = len(sys.argv) > 5 and sys.argv[5] == "zoom"   # y-axis follows the UV-on data
fixed = None                                          # or "900:1100" for a fixed y-axis
if len(sys.argv) > 5 and ":" in sys.argv[5]:
    fixed = tuple(float(x) for x in sys.argv[5].split(":"))


def load():
    t, ntc, ldr, uv = [], [], [], []
    try:
        with open(src, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    t.append(float(r["elapsed_s"]))
                    ntc.append(int(r["ntc_counts"]))
                    ldr.append(int(r["ldr_counts"]))
                    uv.append(int(r["uv_intensity"]))
                except (KeyError, ValueError, TypeError):
                    pass          # last line may be half-written
    except FileNotFoundError:
        pass
    return t, ntc, ldr, uv


fig, ax = plt.subplots(figsize=(11, 6))
axu = ax.twinx()
l_ldr, = ax.plot([], [], color="#7c3aed", lw=1.2, label=label_a1)
if label_a1 == "-":
    l_ldr.set_visible(False)
l_ntc, = ax.plot([], [], color="#dc2626", lw=1.2, label=label_a0)
l_uv, = axu.step([], [], where="post", color="#6b7280", ls="--", lw=1, label="UV intensity %")
ax.set_xlabel("time (s)")
ax.set_ylabel("ADC counts (0-1023)")
ax.set_ylim(*(fixed or (0, 1050)))
axu.set_ylabel("UV intensity (%)")
axu.set_ylim(0, 110)
ax.grid(alpha=.3)
h1, n1 = ax.get_legend_handles_labels()
h2, n2 = axu.get_legend_handles_labels()
ax.legend([h for h in h1 if h.get_visible()] + h2, [n for h, n in zip(h1, n1) if h.get_visible()] + n2, loc="upper left")
fig.canvas.manager.set_window_title(f"{title} - Arduino sensors")


def update(_):
    t, ntc, ldr, uv = load()
    if not t:
        return
    l_ldr.set_data(t, ldr)
    l_ntc.set_data(t, ntc)
    l_uv.set_data(t, uv)
    ax.set_xlim(0, max(t[-1] + 5, 60))
    if zoom:
        on = [ntc[i] for i in range(len(t)) if uv[i] > 0] + ([] if label_a1 == "-" else [ldr[i] for i in range(len(t)) if uv[i] > 0])
        if len(on) > 5:
            lo, hi = min(on), max(on)
            pad = max(3, (hi - lo) * 0.15)
            ax.set_ylim(lo - pad, hi + pad)
            ton = [t[i] for i in range(len(t)) if uv[i] > 0]
            ax.set_xlim(ton[0] - 3, max(ton[-1], t[-1] if uv[-1] > 0 else ton[-1]) + 3)
    ax.set_title(f"{title}  t={t[-1]:.0f}s  UV {uv[-1]}%  A0 {ntc[-1]}" + ("" if label_a1 == "-" else f"  A1 {ldr[-1]}"))


ani = FuncAnimation(fig, update, interval=2000, cache_frame_data=False)
plt.show()
