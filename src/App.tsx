import { useState, useEffect, useRef, useCallback } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import TopBar from '@/components/TopBar'
import HomePage from '@/pages/HomePage'
import CureProcessPage from '@/pages/CureProcessPage'
import SettingsPage from '@/pages/SettingsPage'
import MaterialEditorPage from '@/pages/MaterialEditorPage'
import NetworkPage from '@/pages/NetworkPage'
import AlertsPage from '@/pages/AlertsPage'
import CureHistoryPage from '@/pages/CureHistoryPage'
import WakeScreen from '@/components/WakeScreen'
import BootScreen from '@/components/BootScreen'
import SetupPage from '@/pages/SetupPage'
import { useSystemConfig } from '@/context/SystemConfigContext'

const SCREENSAVER_TIMEOUT = 2 * 60 * 1000 // 2 minutes

function App() {
  const { config, isLoading } = useSystemConfig()
  const location = useLocation()
  const [asleep, setAsleep] = useState(() => {
    return sessionStorage.getItem('scure-shutdown') === 'true'
  })
  const [booting, setBooting] = useState(true)
  const [screenSaver, setScreenSaver] = useState(false)
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resetIdleTimer = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current)
    idleTimer.current = setTimeout(() => setScreenSaver(true), SCREENSAVER_TIMEOUT)
  }, [])

  // Don't run screensaver during cure process
  const isCuring = location.pathname === '/cure-process'

  useEffect(() => {
    if (asleep || booting || !config.setupComplete || isCuring) return

    const events = ['pointerdown', 'pointermove', 'touchstart'] as const
    const handler = () => resetIdleTimer()

    events.forEach(e => window.addEventListener(e, handler, { passive: true }))
    resetIdleTimer()

    return () => {
      events.forEach(e => window.removeEventListener(e, handler))
      if (idleTimer.current) clearTimeout(idleTimer.current)
    }
  }, [asleep, booting, config.setupComplete, isCuring, resetIdleTimer])

  // Clear screensaver timer when entering cure process
  useEffect(() => {
    if (isCuring && idleTimer.current) {
      clearTimeout(idleTimer.current)
      idleTimer.current = null
    }
  }, [isCuring])

  if (isLoading) return null

  if (asleep) {
    return <WakeScreen onWake={() => { sessionStorage.removeItem('scure-shutdown'); setAsleep(false) }} />
  }

  if (booting) {
    return <BootScreen onComplete={() => { sessionStorage.setItem('scure-booted', 'true'); setBooting(false) }} />
  }

  if (!config.setupComplete) {
    return <SetupPage />
  }

  if (screenSaver) {
    return <WakeScreen onWake={() => { setScreenSaver(false); resetIdleTimer() }} />
  }

  return (
    <div className="w-full h-full bg-background flex flex-col overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-y-auto scroll-hidden">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/cure-process" element={<CureProcessPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/material-editor" element={<MaterialEditorPage />} />
          <Route path="/network" element={<NetworkPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/cure-history" element={<CureHistoryPage />} />
        </Routes>
      </div>
    </div>
  )
}

export default App
