import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'

export interface TelemetrySample {
  t: number                     // seconds since start
  chamberTemp: number
  uvOn: boolean
  uvType?: '405nm' | '450nm' | null  // Cure=405nm, Bleacher=450nm
  ledTemps?: { right: number; left: number; door: number; back: number }
}

export interface CureLog {
  id: string
  materialName: string
  steps: number
  stepsCompleted: number
  startedAt: string
  endedAt: string | null
  duration: number | null       // seconds
  status: 'running' | 'completed' | 'aborted' | 'error'
  phases: string[]              // e.g. ["Drying", "Heating", "Cure", "Cooling"]
  targetTemp: number | null
  serialNumber?: string
  telemetry?: TelemetrySample[]
}

interface CureHistoryContextType {
  logs: CureLog[]
  activeLog: CureLog | null
  startCure: (materialName: string, steps: number, phases: string[], targetTemp: number | null, serialNumber?: string) => string
  completeCure: (id: string) => void
  abortCure: (id: string, stepsCompleted: number) => void
  errorCure: (id: string, stepsCompleted: number) => void
  recordTelemetry: (id: string, sample: TelemetrySample) => void
}

const API_BASE = 'http://localhost:3001'

// Cure history is managed in PostgreSQL via the backend (§10) — API only.
async function apiGetCureHistory(): Promise<CureLog[] | null> {
  try {
    const res = await fetch(`${API_BASE}/api/cure-history`)
    if (res.ok) return await res.json()
  } catch { /* backend not available */ }
  return null
}

function apiPost(path: string, body: unknown) {
  fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => { /* fire-and-forget; localStorage keeps the record */ })
}

const CureHistoryContext = createContext<CureHistoryContextType | null>(null)

export function CureHistoryProvider({ children }: { children: ReactNode }) {
  const [logs, setLogs] = useState<CureLog[]>([])

  // Load the canonical history from the database (API only).
  useEffect(() => {
    apiGetCureHistory().then(r => { if (r) setLogs(r) })
  }, [])

  const activeLog = logs.find(l => l.status === 'running') ?? null

  const startCure = useCallback((materialName: string, steps: number, phases: string[], targetTemp: number | null, serialNumber?: string) => {
    const id = crypto.randomUUID()
    const log: CureLog = {
      id,
      materialName,
      steps,
      stepsCompleted: 0,
      startedAt: new Date().toISOString(),
      endedAt: null,
      duration: null,
      status: 'running',
      phases,
      targetTemp,
      serialNumber,
    }
    setLogs(prev => [log, ...prev])
    apiPost(`/api/cure-runs/${id}/start`, { materialName, steps, phases, targetTemp, serialNumber })
    return id
  }, [])

  const finishCure = useCallback((id: string, status: 'completed' | 'aborted' | 'error', stepsCompleted?: number) => {
    setLogs(prev => prev.map(l => {
      if (l.id !== id) return l
      const endedAt = new Date().toISOString()
      const duration = Math.round((new Date(endedAt).getTime() - new Date(l.startedAt).getTime()) / 1000)
      return { ...l, endedAt, duration, status, stepsCompleted: stepsCompleted ?? l.stepsCompleted }
    }))
    apiPost(`/api/cure-runs/${id}/finish`, { status, stepsCompleted })
  }, [])

  const recordTelemetry = useCallback((id: string, sample: TelemetrySample) => {
    setLogs(prev => prev.map(l => {
      if (l.id !== id) return l
      const telemetry = [...(l.telemetry ?? []), sample]
      return { ...l, telemetry }
    }))
    apiPost(`/api/cure-runs/${id}/telemetry`, sample)
  }, [])

  const completeCure = useCallback((id: string) => {
    const log = logs.find(l => l.id === id)
    finishCure(id, 'completed', log?.steps ?? 0)
  }, [finishCure, logs])
  const abortCure = useCallback((id: string, stepsCompleted: number) => finishCure(id, 'aborted', stepsCompleted), [finishCure])
  const errorCure = useCallback((id: string, stepsCompleted: number) => finishCure(id, 'error', stepsCompleted), [finishCure])

  return (
    <CureHistoryContext.Provider value={{ logs, activeLog, startCure, completeCure, abortCure, errorCure, recordTelemetry }}>
      {children}
    </CureHistoryContext.Provider>
  )
}

export function useCureHistory() {
  const ctx = useContext(CureHistoryContext)
  if (!ctx) throw new Error('useCureHistory must be used within CureHistoryProvider')
  return ctx
}