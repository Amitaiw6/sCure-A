import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

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
  nfcEnabled: boolean           // NFC reader enabled
  networkConnected: boolean     // Ethernet/network available
  apiConnected: boolean         // Python API reachable
  faults: HardwareFaults | null // live faults reported by the IO board
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
  setNfcEnabled: (on: boolean) => void
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
  systemName: localStorage.getItem('scure-system-name') || 'S-Cure',
  nfcEnabled: true,
  networkConnected: navigator.onLine,
  apiConnected: false,
  faults: null,
  ledTemps: null,
  counters: {
    led405: 124.5,
    led450: 87.2,
    coolingFan: 312.8,
    heater: 198.3,
    heaterFan: 245.6,
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
  const alertRef = useRef({ wasConnected: false, heaterFault: null as string | null, coolingFault: null as string | null })
  useEffect(() => {
    const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'

    // Surface hardware problems on the Alerts screen via the central registry
    // codes (AlertsContext listens for this event).
    const raiseAlert = (code: number) =>
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code } }))

    const checkStatus = async () => {
      // Browser online/offline
      setState(prev => ({ ...prev, networkConnected: navigator.onLine }))

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
          // The hardware is authoritative: mirror the real readback so the
          // heating/cooling/UV/target indicators reflect the machine, not
          // the UI's optimistic local state.
          setState(prev => ({
            ...prev,
            apiConnected: true,
            chamberTemp: data.chamberTemp != null ? Math.round(data.chamberTemp * 10) / 10 : prev.chamberTemp,
            doorClosed: data.doorClosed ?? prev.doorClosed,
            doorAborted: data.doorAborted ?? false,
            targetTemp: data.targetTemp !== undefined ? data.targetTemp : prev.targetTemp,
            isHeating: data.isHeating ?? prev.isHeating,
            isCooling: data.isCooling ?? prev.isCooling,
            uvOn: data.uvOn ?? prev.uvOn,
            uvIntensity: data.uvIntensity ?? prev.uvIntensity,
            nitrogenActive: data.nitrogenActive ?? prev.nitrogenActive,
            n2LinePressure: data.n2LinePressure ?? prev.n2LinePressure,
            faults: data.faults ?? prev.faults,
            ledTemps: data.ledTemps ?? prev.ledTemps,
          }))
        } else {
          if (alertRef.current.wasConnected) raiseAlert(9089)  // HW_API_UNREACHABLE
          alertRef.current.wasConnected = false
          setState(prev => ({ ...prev, apiConnected: false }))
        }
      } catch {
        if (alertRef.current.wasConnected) raiseAlert(9089)
        alertRef.current.wasConnected = false
        setState(prev => ({ ...prev, apiConnected: false }))
      }
    }

    checkStatus()
    const interval = setInterval(checkStatus, 2000)

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

  const setNfcEnabled = useCallback((on: boolean) => {
    setState(prev => ({ ...prev, nfcEnabled: on }))
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
