/**
 * Hardware API service
 *
 * Architecture:
 *   React UI → Python Flask API (port 3001) → C++ driver (pybind11)
 *
 * In production on RPi CM5, Python server runs on same device.
 * In development, calls are simulated.
 */

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
