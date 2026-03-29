import { createContext, useContext, useState, useEffect, useCallback } from 'react'
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

const STORAGE_KEY = 'scure-print-history-v3'

function loadFromStorage(): PrintLog[] | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return null
}

async function loadFromJson(): Promise<PrintLog[]> {
  try {
    const res = await fetch('/materials/print_history.json')
    if (!res.ok) return []
    return await res.json()
  } catch {
    return []
  }
}

const PrintHistoryContext = createContext<PrintHistoryContextType | null>(null)

export function PrintHistoryProvider({ children }: { children: ReactNode }) {
  const [logs, setLogs] = useState<PrintLog[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const stored = loadFromStorage()
      if (stored && stored.length > 0) {
        setLogs(stored)
      } else {
        const fromJson = await loadFromJson()
        setLogs(fromJson)
      }
      setIsLoading(false)
    }
    load()
  }, [])

  useEffect(() => {
    if (!isLoading) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(logs))
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
