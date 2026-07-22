/**
 * Hardware API service
 *
 * Architecture:
 *   React UI → Python Flask API (port 3001) → C++ driver (pybind11)
 *
 * In production on RPi CM5, Python server runs on same device.
 * In development, calls are simulated.
 */

import { sha256Hex } from '@/lib/compliance'

const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'
const IS_DEV = import.meta.env.DEV

async function apiCall(endpoint: string, method = 'POST'): Promise<{ ok: boolean; message: string }> {
  if (IS_DEV) {
    console.log(`[HW-API] ${method} ${endpoint} (simulated)`)
    return { ok: true, message: 'Simulated in dev mode' }
  }

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, { method })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error(`[HW-API] Error calling ${endpoint}:`, err)
    return { ok: false, message: String(err) }
  }
}

/** Reboot the Raspberry Pi CM5 */
export async function systemReboot() {
  return apiCall('/system/reboot')
}

/** Shutdown the Raspberry Pi CM5 */
export async function systemShutdown() {
  return apiCall('/system/shutdown')
}

/** Open the door (actuator) */
export async function doorOpen() {
  return apiCall('/door/open')
}

/** Set chamber target temperature */
export async function setTargetTemperature(tempC: number) {
  return apiCall(`/chamber/temperature?target=${tempC}`)
}

/** Set fan speed (0-100%) */
export async function setFanSpeed(fan: string, percent: number) {
  return apiCall(`/fans/${fan}?speed=${percent}`)
}

/** Set damper state */
export async function setDamper(open: boolean) {
  return apiCall(`/damper/${open ? 'open' : 'close'}`)
}

/** Run fan test */
export async function runFanTest() {
  return apiCall('/diagnostics/fan-test')
}

/** Run LED diagnostic */
export async function runLedDiagnostic() {
  return apiCall('/diagnostics/led-test')
}

/** Export logs to USB */
export async function exportLogs() {
  return apiCall('/system/export-logs')
}

// ---- Cure operation functions (one per recipe process) ----
// Each step is defined only by process + parameters (target temp / UV
// intensity / UV wavelength / cooling mode). There is NO user-configured
// time — each function decides when its process is complete.

/** 1. Heat the chamber to a target temperature (°C). Ends when reached. */
export async function heatToTargetTemperature(targetC: number) {
  return apiCall(`/cure/heat?target=${targetC}`)
}

/** 2. Cure: UV 405 nm at intensity (%) with a target temperature (°C). */
export async function cureUv405(targetC: number, intensityPct: number) {
  return apiCall(`/cure/cure-405?target=${targetC}&intensity=${intensityPct}`)
}

/** 3. Bleaching: UV 450 nm at intensity (%) with a target temperature (°C). */
export async function cureUv450(targetC: number, intensityPct: number) {
  return apiCall(`/cure/cure-450?target=${targetC}&intensity=${intensityPct}`)
}

/** 4. Cool the chamber to a target temperature (°C) in a mode. Ends when reached. */
export async function coolToTargetTemperature(targetC: number, mode: 'fast' | 'medium' | 'slow') {
  return apiCall(`/cure/cool?target=${targetC}&mode=${mode}`)
}

/** 5. Dry toward a target temperature (°C); the process logic stops it. */
export async function dryToTargetTemperature(targetC: number) {
  return apiCall(`/cure/dry?target=${targetC}`)
}

/** Stop all cure outputs (heater, UV, cooling). */
export async function stopCureOutputs() {
  return apiCall('/cure/stop')
}

/**
 * Write a generated CSV to the USB drive connected to the machine.
 * In dev (no Pi/USB) this returns ok:false so the caller can fall back to a
 * normal browser download.
 */
export async function exportCsvToUsb(
  filename: string,
  content: string,
): Promise<{ ok: boolean; message: string; path?: string }> {
  if (IS_DEV) {
    console.log(`[HW-API] export-csv ${filename} (simulated — no USB in dev)`)
    return { ok: false, message: 'No USB in dev mode' }
  }
  try {
    const res = await fetch(`${API_BASE}/system/export-csv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, content }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error('[HW-API] Error calling /system/export-csv:', err)
    return { ok: false, message: String(err) }
  }
}

/**
 * Persist a generated cure report to the backend database (PostgreSQL).
 * Best-effort and non-blocking: the report is still downloaded locally either way.
 * `cureRunId` is the app cure-log id (cure_runs.ext_id).
 */
export async function saveCureReport(
  cureRunId: string,
  content: string,
  summary: Record<string, unknown>,
): Promise<{ ok: boolean; message?: string; reportId?: string }> {
  if (IS_DEV) {
    console.log(`[HW-API] saveCureReport ${cureRunId} (simulated — no backend in dev)`)
    return { ok: false, message: 'No backend in dev mode' }
  }
  try {
    const res = await fetch(`${API_BASE}/cure-runs/${encodeURIComponent(cureRunId)}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, summary, format: 'html' }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error('[HW-API] saveCureReport failed:', err)
    return { ok: false, message: String(err) }
  }
}

export interface UpdatePackage {
  version: string
  /** Raw package bytes to be integrity-checked before install. */
  bytes: Uint8Array
  /** Expected SHA-256 digest supplied alongside the package (manifest/sidecar). */
  expectedSha256: string
}

/**
 * Locate the update package on USB and return its bytes + expected checksum.
 * In production this reads the package and its manifest from the local service.
 * In development a package is synthesized with a *real* matching SHA-256 so the
 * integrity verification step (see compliance.verifyUpdatePackage) runs for real.
 */
export async function fetchUpdatePackage(): Promise<{
  ok: boolean
  message: string
  package?: UpdatePackage
}> {
  if (IS_DEV) {
    const version = '1.0.1'
    const bytes = new TextEncoder().encode(`scure-update:${version}`)
    const expectedSha256 = await sha256Hex(bytes)
    return { ok: true, message: 'Update package found on USB', package: { version, bytes, expectedSha256 } }
  }

  try {
    const [manifestRes, pkgRes] = await Promise.all([
      fetch(`${API_BASE}/system/update/manifest`),
      fetch(`${API_BASE}/system/update/package`),
    ])
    if (!manifestRes.ok) throw new Error(`manifest HTTP ${manifestRes.status}`)
    if (!pkgRes.ok) throw new Error(`package HTTP ${pkgRes.status}`)
    const manifest = await manifestRes.json()
    const bytes = new Uint8Array(await pkgRes.arrayBuffer())
    return {
      ok: true,
      message: 'Update package found on USB',
      package: { version: manifest.version ?? '', bytes, expectedSha256: manifest.sha256 ?? '' },
    }
  } catch (err) {
    return { ok: false, message: `No update package found (${String(err)})` }
  }
}

/** Update software from USB - returns detailed steps */
export async function updateSoftware(): Promise<{
  ok: boolean
  message: string
  version?: string
  steps?: { step: string; status: string }[]
}> {
  if (IS_DEV) {
    console.log('[HW-API] POST /system/update (simulated)')
    return {
      ok: true,
      message: 'Updated to version 1.0.1 (simulated)',
      version: '1.0.1',
      steps: [
        { step: 'Finding USB drive', status: 'ok' },
        { step: 'Looking for update package', status: 'ok' },
        { step: 'Verifying signature', status: 'ok' },
        { step: 'Version: 1.0.1', status: 'ok' },
        { step: 'Installing update', status: 'ok' },
      ]
    }
  }

  try {
    const res = await fetch(`${API_BASE}/system/update`, { method: 'POST' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    return { ok: false, message: String(err) }
  }
}
