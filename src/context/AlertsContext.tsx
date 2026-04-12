import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'

export interface ErrorDef {
  code: string
  title: string
  severity: 'critical' | 'warning'
  category: string
  description: string
  troubleshooting: string[]
  supportUrl: string
}

export interface SupportInfo {
  email: string
  phone: string
  chat: string
  docsBase: string
}

export interface ActiveAlert {
  id: string
  code: string
  timestamp: string
  dismissed: boolean
}

interface AlertsContextType {
  errorDefs: ErrorDef[]
  support: SupportInfo
  activeAlerts: ActiveAlert[]
  criticalAlerts: ActiveAlert[]
  warningAlerts: ActiveAlert[]
  alertCount: number
  triggerAlert: (code: string) => void
  dismissAlert: (id: string) => void
  clearAll: () => void
  getErrorDef: (code: string) => ErrorDef | undefined
  getQrUrl: (code: string) => string
}

const defaultSupport: SupportInfo = {
  email: 'support@scure.com',
  phone: '+1-800-123-4567',
  chat: 'https://scure.com/support/chat',
  docsBase: 'https://docs.scure.com/errors',
}

const AlertsContext = createContext<AlertsContextType | null>(null)

export function AlertsProvider({ children }: { children: ReactNode }) {
  const [errorDefs, setErrorDefs] = useState<ErrorDef[]>([])
  const [support, setSupport] = useState<SupportInfo>(defaultSupport)
  const [activeAlerts, setActiveAlerts] = useState<ActiveAlert[]>([])

  // Load error definitions from JSON
  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/config/errors.json')
        if (res.ok) {
          const data = await res.json()
          setErrorDefs(data.errors || [])
          setSupport(data.support || defaultSupport)
        }
      } catch { /* use empty */ }
    }
    load()
  }, [])

  // Demo: trigger some alerts on load
  useEffect(() => {
    if (errorDefs.length === 0) return
    const stored = localStorage.getItem('scure-active-alerts')
    if (stored) {
      const parsed: ActiveAlert[] = JSON.parse(stored)
      const hasActive = parsed.some(a => !a.dismissed)
      if (hasActive) {
        setActiveAlerts(parsed)
        return
      }
    }
    // Load demo alerts when no active alerts exist
    localStorage.removeItem('scure-active-alerts')
    const now = new Date()
    setActiveAlerts([
      { id: crypto.randomUUID(), code: 'E-101', timestamp: new Date(now.getTime() - 120000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 'E-102', timestamp: new Date(now.getTime() - 60000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 'W-301', timestamp: new Date(now.getTime() - 300000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 'W-305', timestamp: new Date(now.getTime() - 180000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 'W-302', timestamp: new Date(now.getTime() - 600000).toISOString(), dismissed: false },
    ])
  }, [errorDefs])

  // Persist
  useEffect(() => {
    if (activeAlerts.length > 0) {
      localStorage.setItem('scure-active-alerts', JSON.stringify(activeAlerts))
    }
  }, [activeAlerts])

  const triggerAlert = useCallback((code: string) => {
    setActiveAlerts(prev => {
      // Don't duplicate same code
      if (prev.some(a => a.code === code && !a.dismissed)) return prev
      return [...prev, { id: crypto.randomUUID(), code, timestamp: new Date().toISOString(), dismissed: false }]
    })
  }, [])

  const dismissAlert = useCallback((id: string) => {
    setActiveAlerts(prev => prev.map(a => a.id === id ? { ...a, dismissed: true } : a))
  }, [])

  const clearAll = useCallback(() => {
    setActiveAlerts(prev => prev.map(a => ({ ...a, dismissed: true })))
  }, [])

  const getErrorDef = useCallback((code: string) => {
    return errorDefs.find(e => e.code === code)
  }, [errorDefs])

  const getQrUrl = useCallback((code: string) => {
    const def = errorDefs.find(e => e.code === code)
    return def?.supportUrl || `${support.docsBase}/${code}`
  }, [errorDefs, support])

  const undismissed = activeAlerts.filter(a => !a.dismissed)
  const criticalAlerts = undismissed.filter(a => getErrorDef(a.code)?.severity === 'critical')
  const warningAlerts = undismissed.filter(a => getErrorDef(a.code)?.severity === 'warning')
  const alertCount = undismissed.length

  return (
    <AlertsContext.Provider value={{
      errorDefs, support, activeAlerts: undismissed, criticalAlerts, warningAlerts,
      alertCount, triggerAlert, dismissAlert, clearAll, getErrorDef, getQrUrl,
    }}>
      {children}
    </AlertsContext.Provider>
  )
}

export function useAlerts() {
  const ctx = useContext(AlertsContext)
  if (!ctx) throw new Error('useAlerts must be used within AlertsProvider')
  return ctx
}
