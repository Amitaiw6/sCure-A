import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { setNfcEnabled as apiSetNfcEnabled } from '@/services/hardware-api'

export interface HardwareFaults {
  heater: string | null
  cooling: string | null
  led: string | null
}

export interface HardwareState {
  chamberTemp: number
  targetTemp: number | null
  doorClosed: boolean
  /** True while the server's door watchdog has aborted a process (Err 6016) */
  doorAborted: boolean
  isHeating: boolean
  heatingStartTime: number | null
  isCooling: boolean
  uvOn: boolean
  uvIntensity: number
  nitrogenMode: boolean
  nitrogenActive: boolean       // N2 currently flowing
  nitrogenDuration: number      // seconds of N2 flow after drying
  n2LinePressure: number        // N2 input pressure in bar
  systemName: string            // Display name (shown in TopBar)
  nfcEnabled: boolean           // NFC reader enabled (server-persisted; ON only with a reader detected)
  /** USB NFC reader presence as seen by the server (null until the first /api/state) */
  nfcReader: { detected: boolean; port: string | null; model: string | null; serial: string | null } | null
  networkConnected: boolean     // Ethernet/network available
  apiConnected: boolean         // Python API reachable
  faults: HardwareFaults | null // live faults reported by the IO board
  /** Temperature-sensor supervision from the IO board: per NTC ok / seconds open / critical */
  sensors: Record<string, { sensor: string; ok: boolean; openSec: number | null; critical: boolean }> | null
  /** Fan wear supervision: per fan commanded duty, measured / expected RPM, deficit and status */
  fanHealth: Record<string, { duty: number; rpm: number | null; expected: number | null; deficitPct: number | null; status: string; since: number | null }> | null
  /** Registry codes the machine keeps active right now (one per component since 1.0.106: 9010-9014 sensors, 902x fan stop, 903x fan not spinning, ...; 9001-9005 / 9050 / 9051 on older machines) and their details */
  hwAlerts: number[]
  alertDetails: Record<string, string>
  /** Fans the operator chose to continue without ("continue anyway") */
  fanOverride: string[]
  ledTemps: Record<string, number | null> | null  // per-LED-module thermistors
  counters: {
    led405: number              // hours of 405nm LED usage
    led450: number              // hours of 450nm LED usage
    coolingFan: number          // hours of cooling fan usage
    heater: number              // hours of heater usage
    heaterFan: number           // hours of heater fan usage
  }
}

interface HardwareContextType {
  state: HardwareState
  setChamberTemp: (temp: number) => void
  setTargetTemp: (temp: number | null) => void
  setDoorClosed: (closed: boolean) => void
  setHeating: (on: boolean) => void
  setCooling: (on: boolean) => void
  setUv: (on: boolean, intensity?: number) => void
  setNitrogenMode: (on: boolean) => void
  setNitrogenActive: (on: boolean) => void
  setNitrogenDuration: (seconds: number) => void
  /** Asks the server; resolves ok:false (code 9052) when no reader is connected */
  setNfcEnabled: (on: boolean) => Promise<{ ok: boolean; message: string; code?: number }>
  setSystemName: (name: string) => void
}

const defaultState: HardwareState = {
  chamberTemp: 24.0,
  targetTemp: null,
  doorClosed: true,
  doorAborted: false,
  isHeating: false,
  heatingStartTime: null,
  isCooling: false,
  uvOn: false,
  uvIntensity: 0,
  nitrogenMode: false,
  nitrogenActive: false,
  nitrogenDuration: 120,
  n2LinePressure: 6.0,          // simulated, from sensor in production
  systemName: localStorage.getItem('scure-system-name') || 'sCure',
  // Off until the server reports the persisted setting - it can only be ON
  // when an NFC reader was detected at the time it was switched on.
  nfcEnabled: false,
  nfcReader: null,
  networkConnected: navigator.onLine,
  apiConnected: false,
  faults: null,
  sensors: null,
  fanHealth: null,
  hwAlerts: [],
  alertDetails: {},
  fanOverride: [],
  ledTemps: null,
  // Real accumulated ON-hours, counted and persisted by the server
  // (ComponentCounters in app.py); zeros until the first /api/state arrives.
  counters: {
    led405: 0.0,
    led450: 0.0,
    coolingFan: 0.3,
    heater: 0.5,
    heaterFan: 0.6,
  },
}

const HardwareContext = createContext<HardwareContextType | null>(null)

export function HardwareProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<HardwareState>(defaultState)

  const setChamberTemp = useCallback((temp: number) => {
    setState(prev => ({ ...prev, chamberTemp: Math.round(temp * 10) / 10 }))
  }, [])

  const setTargetTemp = useCallback((temp: number | null) => {
    setState(prev => ({ ...prev, targetTemp: temp }))
  }, [])

  const setDoorClosed = useCallback((closed: boolean) => {
    setState(prev => ({ ...prev, doorClosed: closed }))
  }, [])

  const setHeating = useCallback((on: boolean) => {
    setState(prev => ({ ...prev, isHeating: on, heatingStartTime: on ? Date.now() : null }))
  }, [])

  const setCooling = useCallback((on: boolean) => {
    setState(prev => ({ ...prev, isCooling: on }))
  }, [])

  const setUv = useCallback((on: boolean, intensity = 0) => {
    setState(prev => ({ ...prev, uvOn: on, uvIntensity: intensity }))
  }, [])

  const setNitrogenMode = useCallback((on: boolean) => {
    setState(prev => ({ ...prev, nitrogenMode: on }))
  }, [])

  const setNitrogenActive = useCallback((on: boolean) => {
    setState(prev => ({ ...prev, nitrogenActive: on }))
  }, [])

  const setNitrogenDuration = useCallback((seconds: number) => {
    setState(prev => ({ ...prev, nitrogenDuration: seconds }))
  }, [])

  // Poll network + API status (real chamber temp, door, etc.) every 2 seconds
  const alertRef = useRef({ wasConnected: false, heaterFault: null as string | null, coolingFault: null as string | null, hwAlerts: new Set<number>() })
  useEffect(() => {
    const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'

    // Surface hardware problems on the Alerts screen via the central registry
    // codes (AlertsContext listens for this event).
    const raiseAlert = (code: number, detail?: string) =>
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code, detail } }))

    const checkStatus = async () => {
      // API health check
      try {
        const res = await fetch(`${API_BASE}/state`, { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          const data = await res.json()
          alertRef.current.wasConnected = true
          // New heater/cooling fault since the last poll → temp-stall alert (7004)
          const hf = data.faults?.heater ?? null
          const cf = data.faults?.cooling ?? null
          if ((hf && hf !== alertRef.current.heaterFault) ||
              (cf && cf !== alertRef.current.coolingFault)) {
            raiseAlert(7004)
          }
          alertRef.current.heaterFault = hf
          alertRef.current.coolingFault = cf
          // Registry codes the hardware service itself keeps active (e.g.
          // 9010-9014 temperature sensor disconnected): raise each once
          // while it is active; it may fire again after it clears.
          const hwAlerts: number[] = Array.isArray(data.alerts) ? data.alerts : []
          const details: Record<string, string> = data.alertDetails ?? {}
          for (const code of hwAlerts) {
            if (!alertRef.current.hwAlerts.has(code)) { alertRef.current.hwAlerts.add(code); raiseAlert(code, details[String(code)]) }
          }
          for (const code of Array.from(alertRef.current.hwAlerts)) {
            if (!hwAlerts.includes(code)) alertRef.current.hwAlerts.delete(code)
          }
          // The hardware is authoritative: mirror the real readback so the
          // heating/cooling/UV/target indicators reflect the machine, not
          // the UI's optimistic local state.
          setState(prev => {
            const isHeating = data.isHeating ?? prev.isHeating
            return {
            ...prev,
            apiConnected: true,
            // Real reachability from the machine's background internet watch
            // (TCP 443 every 5s) — NOT navigator.onLine, which is always true
            // on the kiosk because the UI talks to localhost.
            networkConnected: data.internetOk ?? prev.networkConnected,
            chamberTemp: data.chamberTemp != null ? Math.round(data.chamberTemp * 10) / 10 : prev.chamberTemp,
            doorClosed: data.doorClosed ?? prev.doorClosed,
            doorAborted: data.doorAborted ?? false,
            targetTemp: data.targetTemp !== undefined ? data.targetTemp : prev.targetTemp,
            isHeating,
            // keep the heating stopwatch honest when heating starts/stops
            // outside this UI (Settings slider, API, diagnostics)
            heatingStartTime: isHeating
              ? (prev.isHeating ? prev.heatingStartTime : Date.now())
              : null,
            isCooling: data.isCooling ?? prev.isCooling,
            coolingRate: data.isCooling ? (data.coolingRate ?? null) : null,
            uvOn: data.uvOn ?? prev.uvOn,
            uvIntensity: data.uvIntensity ?? prev.uvIntensity,
            nitrogenActive: data.nitrogenActive ?? prev.nitrogenActive,
            n2LinePressure: data.n2LinePressure ?? prev.n2LinePressure,
            faults: data.faults ?? prev.faults,
            ledTemps: data.ledTemps ?? prev.ledTemps,
            sensors: data.sensors ?? prev.sensors,
            fanHealth: data.fanHealth ?? prev.fanHealth,
            hwAlerts,
            alertDetails: details,
            fanOverride: Array.isArray(data.fanOverride) ? data.fanOverride : prev.fanOverride,
            nfcEnabled: typeof data.nfcEnabled === 'boolean' ? data.nfcEnabled : prev.nfcEnabled,
            nfcReader: data.nfcReader ?? prev.nfcReader,
            counters: data.counters ?? prev.counters,
          }})
        } else {
          if (alertRef.current.wasConnected) raiseAlert(9089)  // HW_API_UNREACHABLE
          alertRef.current.wasConnected = false
          // No API to ask — the browser's own flag is the only signal left
          setState(prev => ({ ...prev, apiConnected: false, networkConnected: navigator.onLine }))
        }
      } catch {
        if (alertRef.current.wasConnected) raiseAlert(9089)
        alertRef.current.wasConnected = false
        setState(prev => ({ ...prev, apiConnected: false, networkConnected: navigator.onLine }))
      }
    }

    checkStatus()
    // 1 s sampling: every hardware reading (temps, door, UV, faults) is at
    // most one second old in the UI.
    const interval = setInterval(checkStatus, 1000)

    // Browser online/offline events
    const onOnline = () => setState(prev => ({ ...prev, networkConnected: true }))
    const onOffline = () => setState(prev => ({ ...prev, networkConnected: false }))
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    return () => {
      clearInterval(interval)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [])

  // The server owns the NFC setting: it refuses ON while no reader is on USB
  // (Err 9052), which is surfaced on the Alerts screen like any other fault.
  const setNfcEnabled = useCallback(async (on: boolean) => {
    const res = await apiSetNfcEnabled(on)
    if (res.ok) {
      setState(prev => ({ ...prev, nfcEnabled: on }))
    } else {
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: res.code ?? 9052, detail: res.message } }))
    }
    return res
  }, [])

  const setSystemName = useCallback((name: string) => {
    setState(prev => ({ ...prev, systemName: name }))
    localStorage.setItem('scure-system-name', name)
  }, [])

  return (
    <HardwareContext.Provider value={{
      state, setChamberTemp, setTargetTemp, setDoorClosed,
      setHeating, setCooling, setUv, setNitrogenMode, setNitrogenActive, setNitrogenDuration, setNfcEnabled, setSystemName,
    }}>
      {children}
    </HardwareContext.Provider>
  )
}

export function useHardware() {
  const ctx = useContext(HardwareContext)
  if (!ctx) throw new Error('useHardware must be used within HardwareProvider')
  return ctx
}
