/**
 * Developer Mode API service
 *
 * Same architecture as hardware-api.ts:
 *   React UI → Python Flask API (port 3001) → io bridge / PicoLog TC-08
 *
 * All Developer Mode hardware access (LED zone calibration, calibrated
 * system power test drive, PicoLog TC-08 status, HDT calibration state
 * machine) lives behind /api/dev/*.
 */

const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'
const IS_DEV = import.meta.env.DEV

/** Calibration factor / physical output per LED zone. */
export interface LedZoneValues {
  back: number
  door: number
  left: number
  right: number
}

export const LED_ZONES = ['back', 'door', 'left', 'right'] as const
export type LedZone = (typeof LED_ZONES)[number]
export const LED_ZONE_LABELS: Record<LedZone, string> = {
  back: 'Back',
  door: 'Door',
  left: 'Left',
  right: 'Right',
}

export const DEFAULT_LED_FACTORS: LedZoneValues = { back: 1, door: 1, left: 1, right: 1 }

/** Requested system power × per-zone factor, clamped to the hardware range. */
export function applyLedFactors(requestedPower: number, factors: LedZoneValues): LedZoneValues {
  const clamp = (v: number) => Math.min(100, Math.max(0, v))
  return {
    back: clamp(requestedPower * factors.back),
    door: clamp(requestedPower * factors.door),
    left: clamp(requestedPower * factors.left),
    right: clamp(requestedPower * factors.right),
  }
}

export interface PicologStatus {
  connected: boolean
  ch1Available: boolean
  /** Latest raw CH1 temperature (°C), null when unavailable/invalid. */
  temperature: number | null
  deviceInfo?: string
  error?: string
}

/** One temperature sample recorded by the HDT controller. */
export interface HdtSample {
  /** Elapsed seconds since calibration start. */
  t: number
  raw: number | null
  avg: number | null
  /** Requested calibrated system LED power at this moment. */
  power: number
  /** Test step index (0-based; -1 while idle/cooling before step 1). */
  step: number
}

export interface HdtStepResult {
  power: number
  status: 'PASS' | 'NOT_CONVERGED' | 'HDT_LIMIT' | 'NOT_TESTED' | 'RUNNING' | 'ABORTED'
  startTemp: number | null
  stableTemp: number | null
  minTemp: number | null
  maxTemp: number | null
  timeToStabilitySec: number | null
  rateCPerMin?: number | null
  durationSec: number | null
  startedAt: string | null
  endedAt: string | null
  /** Physical zone outputs commanded during this step. */
  outputs: LedZoneValues
}

export interface HdtConfig {
  samplingIntervalSec: number
  movingAverageWindowSec: number
  stabilityBandC: number
  stabilityTimeMin: number
  stabilityMaxRateCPerMin: number
  maxStabilizationTimeMin: number
  hdtSafetyMarginC: number
  nextStepMaxTempDeltaC: number
  powerLevels: number[]
}

export interface HdtStatus {
  state: string
  running: boolean
  /** Final status once finished: COMPLETED / HDT_LIMIT_REACHED / ABORTED_BY_USER / SENSOR_ERROR / NOT_CONVERGED */
  finalStatus: string | null
  message: string
  hdtC: number | null
  safetyMarginC: number
  currentPower: number | null
  stepIndex: number
  totalSteps: number
  rawTemp: number | null
  avgTemp: number | null
  rateCPerMin?: number | null
  stepElapsedSec: number
  totalElapsedSec: number
  startedAt: string | null
  endedAt: string | null
  picolog: PicologStatus
  factors: LedZoneValues
  outputs: LedZoneValues
  results: HdtStepResult[]
  recommendedPower: number | null
  maxMeasuredTemp: number | null
  config: HdtConfig
  /** Total samples recorded so far (for incremental sample fetch). */
  sampleCount: number
  /** Samples from `samplesFrom` onward (only when requested). */
  samples?: HdtSample[]
}

async function getJson<T>(endpoint: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, { signal: AbortSignal.timeout(5000) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    if (!IS_DEV) console.error(`[DEV-API] GET ${endpoint} failed:`, err)
    return null
  }
}

async function postJson<T>(endpoint: string, body?: unknown): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    if (!IS_DEV) console.error(`[DEV-API] POST ${endpoint} failed:`, err)
    return null
  }
}

/* ---------- Developer Mode event log (best-effort, never blocks the UI) ---------- */

export function devLog(event: string, detail?: Record<string, unknown>) {
  postJson('/dev/log', { event, detail: detail ?? {} })
}

/* ---------- LED calibration ---------- */

export async function getLedCalibration(): Promise<LedZoneValues | null> {
  const res = await getJson<{ ok: boolean; factors: LedZoneValues }>('/dev/led-calibration')
  return res?.factors ?? null
}

export async function saveLedCalibration(factors: LedZoneValues): Promise<boolean> {
  const res = await postJson<{ ok: boolean }>('/dev/led-calibration', { factors })
  return res?.ok ?? false
}

export async function resetLedCalibration(): Promise<LedZoneValues | null> {
  const res = await postJson<{ ok: boolean; factors: LedZoneValues }>('/dev/led-calibration/reset')
  return res?.factors ?? null
}

/**
 * Drive the LEDs at a calibrated system power for calibration test purposes.
 * The backend translates through the saved (or provided preview) factors.
 * power = 0 turns the zones off.
 */
export async function setDevLedPower(
  power: number,
  previewFactors?: LedZoneValues,
): Promise<{ ok: boolean; outputs?: LedZoneValues } | null> {
  return postJson('/dev/led-power', { power, factors: previewFactors })
}

/** All four LED zones to the safe OFF state. */
export async function devLedOff(): Promise<boolean> {
  const res = await postJson<{ ok: boolean }>('/dev/led-power', { power: 0 })
  return res?.ok ?? false
}

/* ---------- PicoLog TC-08 ---------- */

export async function getPicologStatus(): Promise<PicologStatus> {
  const res = await getJson<PicologStatus>('/dev/picolog/status')
  return res ?? { connected: false, ch1Available: false, temperature: null, error: 'API unreachable' }
}

/* ---------- HDT calibration ---------- */

export async function hdtStart(params: {
  hdtC: number
  safetyMarginC?: number
  stabilityBandC?: number
  stabilityTimeMin?: number
  stabilityMaxRateCPerMin?: number
  showOutputs?: boolean
}): Promise<{ ok: boolean; message?: string } | null> {
  return postJson('/dev/hdt/start', params)
}

export async function hdtAbort(): Promise<boolean> {
  const res = await postJson<{ ok: boolean }>('/dev/hdt/abort')
  return res?.ok ?? false
}

/** Clear a finished run back to IDLE (results stay exportable until the next start). */
export async function hdtReset(): Promise<boolean> {
  const res = await postJson<{ ok: boolean }>('/dev/hdt/reset')
  return res?.ok ?? false
}

/**
 * Poll the HDT state machine. `samplesFrom` fetches only samples not yet
 * seen by this client (incremental, keeps long runs cheap to poll).
 */
export async function getHdtStatus(samplesFrom?: number): Promise<HdtStatus | null> {
  const q = samplesFrom !== undefined ? `?samplesFrom=${samplesFrom}` : ''
  return getJson<HdtStatus>(`/dev/hdt/status${q}`)
}

/** Direct download URL for the HDT calibration CSV report (full or partial). */
export function hdtCsvUrl(): string {
  return `${API_BASE}/dev/hdt/report.csv`
}

/** Fetch the CSV content (for browser download fallback / USB export reuse). */
export async function fetchHdtCsv(): Promise<string | null> {
  try {
    const res = await fetch(hdtCsvUrl(), { signal: AbortSignal.timeout(10000) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.text()
  } catch (err) {
    console.error('[DEV-API] CSV fetch failed:', err)
    return null
  }
}
