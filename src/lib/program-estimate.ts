/**
 * program-estimate.ts - REAL program duration estimates.
 *
 * The step list only carries the hold minutes the user typed. What the machine
 * really spends is holds + heating ramps + cooling time. The rates below come
 * from the phase timings collected on the test machine (server/data/
 * phase_timings.json, 141 records, 2026-08-12 .. 2026-09-07, reviewed on
 * 2026-09-07):
 *
 *   Heating ramp (seconds per degree, measured from ~20-28 C ambient):
 *     targets 30-45 C   ~8-16 s/deg, median ~13         (n = 47)
 *     target  50 C      ~17 s/deg                        (n = 1)
 *     target  70 C      ~40 s/deg for the whole climb    (n = 3)
 *     target  80 C      ~66 s/deg from 55 C              (n = 1)
 *   -> piecewise model: 13 s/deg up to 45 C, 50 s/deg between 45 and 75 C,
 *      80 s/deg above 75 C. The heater visibly runs out of steam above ~45 C.
 *
 *   Cooling to 30 C (deg per minute, n = 45; the cooling MODE was not recorded
 *   before v0.8.37, so the clusters are assigned by the fan-duty setpoints):
 *     ~1.5 C/min  (most runs, 40-45 -> 30 C)  -> medium (60 % fan)
 *     ~2.5 C/min  (65-70 -> 30 C and a few short ones) -> fast (100 % fan)
 *     ~0.4 C/min  (2026-08-31 / 09-01 runs)   -> NOT used: those are the days
 *                 of the damper short-travel bug fixed in v0.8.2. No clean
 *                 slow-mode run exists yet, so slow (30 % fan) is interpolated
 *                 from fast/medium at 0.8 C/min until it is measured.
 *
 * Everything is linear on purpose: simple, explainable, and within ~25 % of
 * every measured run. Re-tune here when the next month of timings is in.
 */
import type { CoolingMode, CureStep } from '@/context/MaterialContext'

/** Chamber temperature a program is assumed to start from (C). */
export const AMBIENT_TEMP = 25

/** Heating ramp: seconds per degree, per temperature band (upper bound C). */
export const HEAT_RATE_BANDS: ReadonlyArray<{ upTo: number; secPerDeg: number }> = [
  { upTo: 45, secPerDeg: 13 },
  { upTo: 75, secPerDeg: 50 },
  { upTo: Infinity, secPerDeg: 80 },
]

/** Cooling: degrees per minute per cooling mode (measured, see header). */
export const COOL_RATE_C_PER_MIN: Record<CoolingMode, number> = { fast: 2.5, medium: 1.5, slow: 0.8 }

/** Seconds the chamber needs to climb from `fromC` to `toC` (0 if not climbing). */
export function estimateHeatSeconds(fromC: number, toC: number): number {
  if (toC <= fromC) return 0
  let t = fromC
  let seconds = 0
  for (const band of HEAT_RATE_BANDS) {
    if (t >= toC) break
    const top = Math.min(toC, band.upTo)
    if (top > t) {
      seconds += (top - t) * band.secPerDeg
      t = top
    }
  }
  return Math.round(seconds)
}

/** Seconds the chamber needs to fall from `fromC` to `toC` in `mode` (0 if not falling). */
export function estimateCoolSeconds(fromC: number, toC: number, mode: CoolingMode = 'medium'): number {
  if (toC >= fromC) return 0
  const rate = COOL_RATE_C_PER_MIN[mode] ?? COOL_RATE_C_PER_MIN.medium
  return Math.round(((fromC - toC) / rate) * 60)
}

/** Heating-rate for the simulated ramp (seconds per degree at temperature `atC`). */
export function heatSecPerDeg(atC: number): number {
  return (HEAT_RATE_BANDS.find(b => atC < b.upTo) ?? HEAT_RATE_BANDS[HEAT_RATE_BANDS.length - 1]).secPerDeg
}

export interface ProgramEstimate {
  /** Hold minutes the steps ask for (what the step list shows today). */
  holdSeconds: number
  /** Heating ramps not covered by the holds. */
  rampSeconds: number
  /** Cooling time to the cooling steps' targets. */
  coolSeconds: number
  /** Nitrogen purge time (from the system config, 0 when unknown). */
  nitrogenSeconds: number
  /** Everything together. */
  totalSeconds: number
}

/**
 * Walk a program and estimate what it really takes, starting at `startC`.
 * Timer mode 'on-ramp' means the hold timer already runs through the ramp,
 * so the ramp is not added on top for that step.
 */
export function estimateProgram(steps: readonly CureStep[], opts: { startC?: number; nitrogenSeconds?: number } = {}): ProgramEstimate {
  let temp = opts.startC ?? AMBIENT_TEMP
  const n2 = opts.nitrogenSeconds ?? 0
  const est: ProgramEstimate = { holdSeconds: 0, rampSeconds: 0, coolSeconds: 0, nitrogenSeconds: 0, totalSeconds: 0 }
  for (const s of steps) {
    const hold = Math.max(0, (s.time || 0) * 60)
    switch (s.process) {
      case 'Heating':
      case 'Drying':
      case 'Cure':
      case 'Bleacher': {
        if (s.temperature != null) {
          const ramp = estimateHeatSeconds(temp, s.temperature)
          if (s.timerMode === 'on-ramp') est.rampSeconds += Math.max(0, ramp - hold)
          else est.rampSeconds += ramp
          temp = Math.max(temp, s.temperature)
        }
        est.holdSeconds += hold
        break
      }
      case 'Cooling': {
        const target = s.temperature ?? AMBIENT_TEMP
        est.coolSeconds += estimateCoolSeconds(temp, target, s.coolingMode ?? 'medium')
        temp = Math.min(temp, target)
        break
      }
      case 'Nitrogen':
        est.nitrogenSeconds += n2
        break
    }
  }
  est.totalSeconds = est.holdSeconds + est.rampSeconds + est.coolSeconds + est.nitrogenSeconds
  return est
}

/** Whole minutes, rounded up, for the estimate. */
export function estimateProgramMinutes(steps: readonly CureStep[], opts?: { startC?: number; nitrogenSeconds?: number }): number {
  return Math.ceil(estimateProgram(steps, opts).totalSeconds / 60)
}
