import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import TopBar from '@/components/TopBar'
import HomePage from '@/pages/HomePage'
import CureProcessPage from '@/pages/CureProcessPage'
import SettingsPage from '@/pages/SettingsPage'
import MaterialEditorPage from '@/pages/MaterialEditorPage'
import NetworkPage from '@/pages/NetworkPage'
import AlertsPage from '@/pages/AlertsPage'
import CureHistoryPage from '@/pages/CureHistoryPage'
import WakeScreen from '@/components/WakeScreen'
import SetupPage from '@/pages/SetupPage'
import { useSystemConfig } from '@/context/SystemConfigContext'

function App() {
  const { config, isLoading } = useSystemConfig()
  const [asleep, setAsleep] = useState(() => {
    return sessionStorage.getItem('scure-shutdown') === 'true'
  })

  if (isLoading) return null

  if (asleep) {
    return <WakeScreen onWake={() => { sessionStorage.removeItem('scure-shutdown'); setAsleep(false) }} />
  }

  if (!config.setupComplete) {
    return <SetupPage />
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
