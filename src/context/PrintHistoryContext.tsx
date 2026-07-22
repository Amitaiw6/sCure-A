import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'

export interface PrintLog {
  id: string
  printName: string
  materialName: string
  printerName: string
  date: string
  duration: number
  status: 'completed' | 'aborted' | 'error'
  steps: number
  csvFile: string
}

interface PrintHistoryContextType {
  logs: PrintLog[]
  addLog: (log: Omit<PrintLog, 'id' | 'date'>) => void
  removeLogs: (ids: string[]) => void
  recentLogs: PrintLog[]
  isLoading: boolean
}

const API_BASE = 'http://localhost:3001'

// Print history is managed in PostgreSQL and read via the backend API.
// When the backend is unreachable (dev / offline), fall back to bundled demo prints.
import { DEMO_PRINTS } from '@/data/demo-data'

async function loadPrintHistory(): Promise<PrintLog[]> {
  try {
    const res = await fetch(`${API_BASE}/api/print-history`)
    if (res.ok) return await res.json()
  } catch { /* backend not available */ }
  return DEMO_PRINTS
}

async function savePrintHistory(logs: PrintLog[]) {
  try {
    await fetch(`${API_BASE}/api/print-history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(logs),
    })
  } catch { /* API not available in dev mode */ }
}

const PrintHistoryContext = createContext<PrintHistoryContextType | null>(null)

export function PrintHistoryProvider({ children }: { children: ReactNode }) {
  const [logs, setLogs] = useState<PrintLog[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const saveRef = useRef(false)

  useEffect(() => {
    async function load() {
      const data = await loadPrintHistory()
      setLogs(data)
      setIsLoading(false)
    }
    load()
  }, [])

  useEffect(() => {
    if (!isLoading) {
      if (!saveRef.current) { saveRef.current = true; return }
      savePrintHistory(logs)
    }
  }, [logs, isLoading])

  const addLog = useCallback((data: Omit<PrintLog, 'id' | 'date'>) => {
    const newLog: PrintLog = {
      ...data,
      id: crypto.randomUUID(),
      date: new Date().toISOString(),
    }
    setLogs(prev => [newLog, ...prev])
  }, [])

  const removeLogs = useCallback((ids: string[]) => {
    const idSet = new Set(ids)
    setLogs(prev => prev.filter(l => !idSet.has(l.id)))
  }, [])

  const recentLogs = logs.slice(0, 3)

  return (
    <PrintHistoryContext.Provider value={{ logs, addLog, removeLogs, recentLogs, isLoading }}>
      {children}
    </PrintHistoryContext.Provider>
  )
}

export function usePrintHistory() {
  const ctx = useContext(PrintHistoryContext)
  if (!ctx) throw new Error('usePrintHistory must be used within PrintHistoryProvider')
  return ctx
}
