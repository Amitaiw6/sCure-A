"""Plot a uv_intensity_sweep.py CSV: both sensors over time with the UV
intensity staircase, plus settled response vs intensity.

Usage: python uv_sweep_plot.py sweep.csv [out.png]
Prints a per-step table (mean of the last 15 s of each step) to stdout.
"""
import csv, sys, math
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".png"

t, ntc, ldr, uv, phase, chamber, led = [], [], [], [], [], [], []
with open(src, newline="") as f:
    for r in csv.DictReader(f):
        t.append(float(r["elapsed_s"]))
        ntc.append(int(r["ntc_counts"]))
        ldr.append(int(r["ldr_counts"]))
        uv.append(int(r["uv_intensity"]))
        phase.append(r["phase"])
        chamber.append(float(r.get("chamber_c", "nan")))
        led.append(float(r.get("led_max_c", "nan")))

# ---- settled value per step: mean of the last 15 s of each intensity block
blocks = []          # (intensity, phase, t_start, t_end)
for i in range(len(t)):
    key = (uv[i], phase[i])
    if not blocks or (blocks[-1][0], blocks[-1][1]) != key:
        blocks.append([uv[i], phase[i], t[i], t[i]])
    else:
        blocks[-1][3] = t[i]

rows = []
for inten, ph, a, b in blocks:
    sel = [i for i in range(len(t)) if b - 15 <= t[i] <= b and (uv[i], phase[i]) == (inten, ph)]
    if not sel:
        continue
    m = lambda arr: sum(arr[i] for i in sel) / len(sel)
    sd = lambda arr, mu: math.sqrt(sum((arr[i] - mu) ** 2 for i in sel) / len(sel))
    mn, ml = m(ntc), m(ldr)
    rows.append((ph, inten, mn, sd(ntc, mn), ml, sd(ldr, ml), m(chamber), m(led)))

print(f"{'phase':9} {'uv%':>4} {'ntc':>7} {'±':>4} {'ldr':>7} {'±':>4} {'chamber':>8} {'led_max':>8}")
for ph, inten, mn, sn, ml, sl, ch, lm in rows:
    print(f"{ph:9} {inten:4d} {mn:7.1f} {sn:4.1f} {ml:7.1f} {sl:4.1f} {ch:8.1f} {lm:8.1f}")

# ---- figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 2]})
ax1.plot(t, ldr, color="#7c3aed", lw=1, label="photoresistor A1 (counts)")
ax1.plot(t, ntc, color="#dc2626", lw=1, label="thermistor A0 (counts)")
ax1.set_ylabel("ADC counts (0-1023)")
ax1.set_xlabel("time (s)")
ax1.grid(alpha=.3)
axu = ax1.twinx()
axu.step(t, uv, where="post", color="#6b7280", lw=1, ls="--", label="UV intensity %")
axu.set_ylabel("UV intensity (%)")
axu.set_ylim(0, 110)
h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = axu.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
ax1.set_title("sCure UV sweep: raw sensor readings vs time")

steps = [r for r in rows if r[0] == "step"]
xs = [r[1] for r in steps]
ax2.errorbar(xs, [r[4] for r in steps], yerr=[r[5] for r in steps], marker="o",
             color="#7c3aed", label="photoresistor (settled)")
ax2.set_xlabel("UV intensity (%)")
ax2.set_ylabel("photoresistor counts", color="#7c3aed")
ax2.grid(alpha=.3)
ax2b = ax2.twinx()
ax2b.errorbar(xs, [r[2] for r in steps], yerr=[r[3] for r in steps], marker="s",
              color="#dc2626", label="thermistor (settled)")
ax2b.set_ylabel("thermistor counts", color="#dc2626")
ax2.set_title("settled response (mean of last 15 s of each step)")
fig.tight_layout()
fig.savefig(out, dpi=130)
print(f"saved {out}")
