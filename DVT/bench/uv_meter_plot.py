"""Plot the Ophir irradiance from a uv_intensity_sweep_meter.py run:
top = irradiance vs time with the UV staircase, bottom = settled irradiance
vs commanded intensity (mean of the last 15 s of each step) with a linear fit.

Usage: python uv_meter_plot.py sweep_meter.csv [out.png]
"""
import csv, sys, math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".png"

t, v, uv, ph = [], [], [], []
with open(src, newline="") as f:
    for r in csv.DictReader(f):
        try:
            x = float(r["meter_mw_cm2"])
        except ValueError:
            continue
        if math.isnan(x):
            continue
        t.append(float(r["elapsed_s"])); v.append(x)
        uv.append(int(r["uv_intensity"])); ph.append(r["phase"])

blocks = []
for i in range(len(t)):
    key = (uv[i], ph[i])
    if not blocks or (blocks[-1][0], blocks[-1][1]) != key:
        blocks.append([uv[i], ph[i], t[i], t[i]])
    else:
        blocks[-1][3] = t[i]

rows = []
for inten, phase, a, b in blocks:
    sel = [v[i] for i in range(len(t)) if b - 15 <= t[i] <= b and (uv[i], ph[i]) == (inten, phase)]
    if sel:
        mu = sum(sel) / len(sel)
        sd = math.sqrt(sum((x - mu) ** 2 for x in sel) / len(sel))
        rows.append((phase, inten, mu, sd, len(sel)))

dark = next((r[2] for r in rows if r[0] == "baseline"), 0.0)
print(f"{'phase':9} {'uv%':>4} {'mW/cm2':>9} {'sd':>7} {'n':>4}")
for phase, inten, mu, sd, n in rows:
    print(f"{phase:9} {inten:4d} {mu:9.3f} {sd:7.3f} {n:4d}")

steps = [r for r in rows if r[0] == "step"]
xs = [r[1] for r in steps]; ys = [r[2] - dark for r in steps]
fit = None
if len(steps) >= 2:
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    icpt = my - slope * mx
    ss_res = sum((y - (slope * x + icpt)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    fit = (slope, icpt, r2)
    print(f"linear fit: {slope:.4f} mW/cm2 per %  intercept {icpt:+.3f}  R^2 {r2:.4f}")
    if steps:
        print(f"per-% linearity: " + "  ".join(f"{x}%:{(y / x):.4f}" for x, y in zip(xs, ys)))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 2]})
ax1.plot(t, v, color="#0f766e", lw=1, label="Ophir PD300RM (mW/cm²)")
ax1.set_ylabel("irradiance (mW/cm²)"); ax1.set_xlabel("time (s)"); ax1.grid(alpha=.3)
axu = ax1.twinx()
axu.step(t, uv, where="post", color="#6b7280", ls="--", lw=1, label="UV intensity %")
axu.set_ylabel("UV intensity (%)"); axu.set_ylim(0, 110)
h1, l1 = ax1.get_legend_handles_labels(); h2, l2 = axu.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
ax1.set_title("sCure 450 nm sweep: measured irradiance vs time")

ax2.errorbar(xs, [r[2] for r in steps], yerr=[r[3] for r in steps], marker="o",
             color="#0f766e", ls="none", capsize=3, label="settled (last 15 s of step)")
if fit:
    xx = [0, 100]
    ax2.plot(xx, [fit[0] * x + fit[1] + dark for x in xx], color="#94a3b8", ls="--",
             label=f"fit {fit[0]:.3f} mW/cm²/%  R²={fit[2]:.4f}")
ax2.set_xlim(0, 105); ax2.set_ylim(bottom=0)
ax2.set_xlabel("commanded UV intensity (%)"); ax2.set_ylabel("irradiance (mW/cm²)")
ax2.grid(alpha=.3); ax2.legend(fontsize=9)
ax2.set_title("measured irradiance vs commanded intensity")
fig.tight_layout(); fig.savefig(out, dpi=130)
print(f"saved {out}")
