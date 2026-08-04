"""sCure chamber-temperature correction, calibrated against a Pico TC-08
inside the chamber (2026-08-04, 724 paired samples: 31->80 C heat-up, 80 C
hold, and fan cool-down; scripts/calibrate_scure_temp.py).

Model (mirrors io_controller.py CHAMBER_CAL_*):

  static (exact at steady state, raw 31.5-76.6 C):
      actual = 1.0979 * raw - 3.9813
  rate compensation (rate = slope of the raw reading, C/min, ~45 s window):
      heating  (rate > +0.3):  += 2.1873 * (rate - 0.3)     lag; RMS 3.4->1.1 C
      cooling  (rate < -1.0):  += 0.0956 * (raw - 25.0)     intake-air bias
                                                            RMS 3.6->2.7 C

Measured accuracy: 80 C hold mean error -0.04 C (RMS 0.09); heat ramp RMS
1.1 C; fan cool-down RMS 2.7 C. Re-run the calibration if the sensor, its
placement, or the chamber changes.

Use ChamberTempCorrector when readings arrive periodically (it estimates the
rate itself); use actual_chamber_temp() only for steady-state one-shots.
"""

import time
from collections import deque

CAL_GAIN = 1.0979
CAL_OFFSET = -3.9813
CAL_LEAD = 2.1873          # C per C/min of heating rate above the deadband
CAL_LEAD_DEADBAND = 0.3    # C/min - holds/steady state stay untouched
CAL_COOL_COEF = 0.0956     # C per C above ambient during fan cooling
CAL_COOL_GATE = -1.0       # C/min - faster cooling than this = fan active
CAL_AMBIENT = 25.0
RATE_WINDOW_SEC = 45.0
CAL_RAW_RANGE = (31.5, 76.6)


def actual_chamber_temp(raw_c):
    """Steady-state correction only (no rate term). None-safe."""
    if raw_c is None:
        return None
    return CAL_GAIN * float(raw_c) + CAL_OFFSET


class ChamberTempCorrector:
    """Feed every raw reading through update(); returns the actual temp (C).

    corrector = ChamberTempCorrector()
    ...
    actual = corrector.update(raw_reading)   # call once per sample
    """

    def __init__(self):
        self._hist = deque()

    def update(self, raw_c, now=None):
        if raw_c is None:
            return None
        raw_c = float(raw_c)
        now = time.monotonic() if now is None else now
        self._hist.append((now, raw_c))
        while self._hist and now - self._hist[0][0] > RATE_WINDOW_SEC:
            self._hist.popleft()
        est = CAL_GAIN * raw_c + CAL_OFFSET
        rate = self._rate_per_min()
        if rate is None:
            return est
        if rate > CAL_LEAD_DEADBAND:
            est += CAL_LEAD * (rate - CAL_LEAD_DEADBAND)
        elif rate < CAL_COOL_GATE:
            est += CAL_COOL_COEF * (raw_c - CAL_AMBIENT)
        return est

    def _rate_per_min(self):
        pts = list(self._hist)
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 10.0:
            return None
        n = len(pts)
        mt = sum(p[0] for p in pts) / n
        mv = sum(p[1] for p in pts) / n
        den = sum((p[0] - mt) ** 2 for p in pts)
        if den <= 0:
            return None
        return sum((p[0] - mt) * (p[1] - mv) for p in pts) / den * 60.0
