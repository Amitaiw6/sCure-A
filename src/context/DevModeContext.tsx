import { createContext, useContext, useState, useRef, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { devLog } from '@/services/dev-api'

// Hidden Developer Mode gate: 10 presses on the Settings gear open the
// password screen. Developer Mode itself is session-only state — a restart
// always comes back in normal mode (only the saved LED calibration factors
// persist, on the backend).
const PRESSES_TO_UNLOCK = 10
const DEV_PASSWORD = '8176'

interface DevModeContextType {
  devMode: boolean
  authOpen: boolean
  /** Called on every Settings-gear press; opens the auth screen on the 10th. */
  registerSettingsPress: () => void
  /** Returns true and enters Developer Mode when the password matches. */
  tryPassword: (password: string) => boolean
  closeAuth: () => void
  exitDevMode: () => void
}

const DevModeContext = createContext<DevModeContextType | null>(null)

export function DevModeProvider({ children }: { children: ReactNode }) {
  const [devMode, setDevMode] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const pressCount = useRef(0)
  const navigate = useNavigate()

  const registerSettingsPress = useCallback(() => {
    if (devMode) return
    pressCount.current += 1
    if (pressCount.current >= PRESSES_TO_UNLOCK) {
      pressCount.current = 0
      devLog('Developer Mode requested')
      setAuthOpen(true)
    }
  }, [devMode])

  const tryPassword = useCallback((password: string) => {
    if (password === DEV_PASSWORD) {
      devLog('Developer Mode authentication successful')
      devLog('Developer Mode entered')
      setDevMode(true)
      setAuthOpen(false)
      navigate('/dev')
      return true
    }
    devLog('Developer Mode authentication failed')
    return false
  }, [navigate])

  const closeAuth = useCallback(() => setAuthOpen(false), [])

  const exitDevMode = useCallback(() => {
    devLog('Developer Mode exited')
    setDevMode(false)
    navigate('/')
  }, [navigate])

  return (
    <DevModeContext.Provider value={{ devMode, authOpen, registerSettingsPress, tryPassword, closeAuth, exitDevMode }}>
      {children}
    </DevModeContext.Provider>
  )
}

export function useDevMode() {
  const ctx = useContext(DevModeContext)
  if (!ctx) throw new Error('useDevMode must be used within DevModeProvider')
  return ctx
}
