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

const STORAGE_KEY = 'scure-cure-history'

function loadLogs(): CureLog[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return []
}

const CureHistoryContext = createContext<CureHistoryContextType | null>(null)

export function CureHistoryProvider({ children }: { children: ReactNode }) {
  const [logs, setLogs] = useState<CureLog[]>(loadLogs)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(logs))
  }, [logs])

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
    return id
  }, [])

  const finishCure = useCallback((id: string, status: 'completed' | 'aborted' | 'error', stepsCompleted?: number) => {
    setLogs(prev => prev.map(l => {
      if (l.id !== id) return l
      const endedAt = new Date().toISOString()
      const duration = Math.round((new Date(endedAt).getTime() - new Date(l.startedAt).getTime()) / 1000)
      return { ...l, endedAt, duration, status, stepsCompleted: stepsCompleted ?? l.stepsCompleted }
    }))
  }, [])

  const recordTelemetry = useCallback((id: string, sample: TelemetrySample) => {
    setLogs(prev => prev.map(l => {
      if (l.id !== id) return l
      const telemetry = [...(l.telemetry ?? []), sample]
      return { ...l, telemetry }
    }))
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