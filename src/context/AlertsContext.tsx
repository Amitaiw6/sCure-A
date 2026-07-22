import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
// Bundled sample catalog — last-resort fallback when offline (single-file design build).
import bundledErrors from '../../public/config/errors.json'

export interface ErrorDef {
  /** Stable, unique, hierarchical number (1xxx daemon · 2xxx backend · 3xxx UI). */
  code: number
  /** Stable machine key (UPPER_SNAKE), e.g. USB_WRITE_FAILED. */
  key: string
  /** Displayed text — CS-editable in the registry without any code change. */
  message: string
  severity: 'critical' | 'warning'
  category: string
  description: string
  troubleshooting: string[]
  supportUrl: string
  /** Pre-2.0 code (E-/W-), kept only for traceability. */
  legacyCode?: string
}

export interface SupportInfo {
  email: string
  phone: string
  chat: string
  docsBase: string
}

export interface ActiveAlert {
  id: string
  code: number
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
  triggerAlert: (code: number) => void
  dismissAlert: (id: string) => void
  clearAll: () => void
  getErrorDef: (code: number) => ErrorDef | undefined
  getQrUrl: (code: number) => string
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
          return
        }
      } catch { /* fall through to bundled */ }
      // Bundled fallback (offline / single-file design build)
      setErrorDefs((bundledErrors.errors as ErrorDef[]) || [])
      setSupport((bundledErrors.support as SupportInfo) || defaultSupport)
    }
    load()
  }, [])

  // Restore persisted alerts; demo alerts are DEV-only so a real machine
  // never shows fabricated problems.
  useEffect(() => {
    if (errorDefs.length === 0) return
    const stored = localStorage.getItem('scure-active-alerts')
    if (stored) {
      const parsed: ActiveAlert[] = JSON.parse(stored)
      // Drop any alert whose code is no longer in the registry (e.g. pre-2.0 E-/W- codes)
      // so a stale localStorage entry can't leave the bell badge counting unresolvable alerts.
      const known = parsed.filter(a => errorDefs.some(e => e.code === a.code))
      const hasActive = known.some(a => !a.dismissed)
      if (hasActive) {
        setActiveAlerts(known)
        return
      }
    }
    if (!import.meta.env.DEV) return
    // Dev only: load demo alerts when no active alerts exist
    localStorage.removeItem('scure-active-alerts')
    const now = new Date()
    setActiveAlerts([
      { id: crypto.randomUUID(), code: 9082, timestamp: new Date(now.getTime() - 120000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 9089, timestamp: new Date(now.getTime() - 60000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 9084, timestamp: new Date(now.getTime() - 300000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 9080, timestamp: new Date(now.getTime() - 180000).toISOString(), dismissed: false },
      { id: crypto.randomUUID(), code: 9085, timestamp: new Date(now.getTime() - 600000).toISOString(), dismissed: false },
    ])
  }, [errorDefs])

  // Persist
  useEffect(() => {
    if (activeAlerts.length > 0) {
      localStorage.setItem('scure-active-alerts', JSON.stringify(activeAlerts))
    }
  }, [activeAlerts])

  const triggerAlert = useCallback((code: number) => {
    setActiveAlerts(prev => {
      // Don't duplicate same code
      if (prev.some(a => a.code === code && !a.dismissed)) return prev
      return [...prev, { id: crypto.randomUUID(), code, timestamp: new Date().toISOString(), dismissed: false }]
    })
  }, [])

  // Hardware layers (HardwareContext poll, cure page) raise alerts by
  // dispatching 'scure-alert' with a registry code — decoupled from provider order.
  useEffect(() => {
    const onAlert = (e: Event) => {
      const code = (e as CustomEvent<{ code?: number }>).detail?.code
      if (typeof code === 'number') triggerAlert(code)
    }
    window.addEventListener('scure-alert', onAlert)
    return () => window.removeEventListener('scure-alert', onAlert)
  }, [triggerAlert])

  const dismissAlert = useCallback((id: string) => {
    setActiveAlerts(prev => prev.map(a => a.id === id ? { ...a, dismissed: true } : a))
  }, [])

  const clearAll = useCallback(() => {
    setActiveAlerts(prev => prev.map(a => ({ ...a, dismissed: true })))
  }, [])

  const getErrorDef = useCallback((code: number) => {
    return errorDefs.find(e => e.code === code)
  }, [errorDefs])

  const getQrUrl = useCallback((code: number) => {
    const def = errorDefs.find(e => e.code === code)
    return def?.supportUrl || `${support.docsBase}/${code}`
  }, [errorDefs, support])

  const undismissed = activeAlerts.filter(a => !a.dismissed)
  const criticalAlerts = undismissed.filter(a => getErrorDef(a.code)?.severity === 'critical')
  const warningAlerts = undismissed.filter(a => getErrorDef(a.code)?.severity === 'warning')
  // Only count alerts that resolve to a registry definition, so the bell badge
  // always matches what the Alerts screen can actually display.
  const alertCount = undismissed.filter(a => getErrorDef(a.code)).length

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
