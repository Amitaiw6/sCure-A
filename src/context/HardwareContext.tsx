import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'

export interface HardwareState {
  chamberTemp: number
  targetTemp: number | null
  doorClosed: boolean
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
  isHeating: false,
  heatingStartTime: null,
  isCooling: false,
  uvOn: false,
  uvIntensity: 0,
  nitrogenMode: false,
  nitrogenActive: false,
  nitrogenDuration: 60,
  n2LinePressure: 6.0,          // simulated, from sensor in production
  systemName: localStorage.getItem('scure-system-name') || 'sCure',
  nfcEnabled: true,
  networkConnected: navigator.onLine,
  apiConnected: false,
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

  // Poll network + API status every 5 seconds
  useEffect(() => {
    const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'

    const checkStatus = async () => {
      // Browser online/offline
      setState(prev => ({ ...prev, networkConnected: navigator.onLine }))

      // API health check
      try {
        const res = await fetch(`${API_BASE}/state`, { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          const data = await res.json()
          setState(prev => ({
            ...prev,
            apiConnected: true,
            chamberTemp: data.chamberTemp ?? prev.chamberTemp,
            doorClosed: data.doorClosed ?? prev.doorClosed,
            n2LinePressure: data.n2LinePressure ?? prev.n2LinePressure,
          }))
        } else {
          setState(prev => ({ ...prev, apiConnected: false }))
        }
      } catch {
        setState(prev => ({ ...prev, apiConnected: false }))
      }
    }

    checkStatus()
    const interval = setInterval(checkStatus, 5000)

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
