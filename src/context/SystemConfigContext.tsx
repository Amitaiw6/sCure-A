import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'

export interface SystemConfig {
  serialNumber: string
  firmware: string
  lastBoot: string
  deviceName: string
  leadOnTimeHours: number
  model: string
  hardwareRevision: string
  manufacturer: string
  organizationId: string
  setupComplete: boolean
}

const defaultConfig: SystemConfig = {
  serialNumber: '------',
  firmware: '------',
  lastBoot: '------',
  deviceName: '------',
  leadOnTimeHours: 0,
  model: '------',
  hardwareRevision: '------',
  manufacturer: '------',
  organizationId: '',
  setupComplete: false,
}

interface SystemConfigContextType {
  config: SystemConfig
  isLoading: boolean
  setOrganization: (orgId: string) => void
  completeSetup: () => void
  resetSetup: () => void
}

const SystemConfigContext = createContext<SystemConfigContextType | null>(null)

export function SystemConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<SystemConfig>(defaultConfig)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/config/system.json')
        if (res.ok) {
          const data = await res.json()
          // Load system.json first, then override with localStorage (user settings win)
          const saved = localStorage.getItem('scure-org')
          const userSettings = saved ? JSON.parse(saved) : {}
          setConfig(prev => ({
            ...prev,
            ...data,
            organizationId: userSettings.organizationId ?? data.organizationId ?? prev.organizationId,
            setupComplete: userSettings.setupComplete ?? data.setupComplete ?? prev.setupComplete,
          }))
        } else {
          const saved = localStorage.getItem('scure-org')
          if (saved) {
            const parsed = JSON.parse(saved)
            setConfig(prev => ({
              ...prev,
              organizationId: parsed.organizationId ?? prev.organizationId,
              setupComplete: parsed.setupComplete ?? prev.setupComplete,
            }))
          }
        }
      } catch { /* use defaults */ }
      setIsLoading(false)
    }
    load()
  }, [])

  const setOrganization = (orgId: string) => {
    setConfig(prev => {
      const next = { ...prev, organizationId: orgId }
      localStorage.setItem('scure-org', JSON.stringify({ organizationId: next.organizationId, setupComplete: next.setupComplete }))
      return next
    })
  }

  const completeSetup = () => {
    setConfig(prev => {
      const next = { ...prev, setupComplete: true }
      localStorage.setItem('scure-org', JSON.stringify({ organizationId: next.organizationId, setupComplete: next.setupComplete }))
      return next
    })
  }

  const resetSetup = () => {
    localStorage.removeItem('scure-org')
    setConfig(prev => ({ ...prev, organizationId: '', setupComplete: false }))
  }

  return (
    <SystemConfigContext.Provider value={{ config, isLoading, setOrganization, completeSetup, resetSetup }}>
      {children}
    </SystemConfigContext.Provider>
  )
}

export function useSystemConfig() {
  const ctx = useContext(SystemConfigContext)
  if (!ctx) throw new Error('useSystemConfig must be used within SystemConfigProvider')
  return ctx
}
