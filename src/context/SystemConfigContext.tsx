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
}

interface SystemConfigContextType {
  config: SystemConfig
  isLoading: boolean
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
          setConfig(data)
        }
      } catch { /* use defaults */ }
      setIsLoading(false)
    }
    load()
  }, [])

  return (
    <SystemConfigContext.Provider value={{ config, isLoading }}>
      {children}
    </SystemConfigContext.Provider>
  )
}

export function useSystemConfig() {
  const ctx = useContext(SystemConfigContext)
  if (!ctx) throw new Error('useSystemConfig must be used within SystemConfigProvider')
  return ctx
}
