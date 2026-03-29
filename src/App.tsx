import { Routes, Route } from 'react-router-dom'
import TopBar from './components/TopBar'
import HomePage from './pages/HomePage'
import CureProcessPage from './pages/CureProcessPage'
import SettingsPage from './pages/SettingsPage'
import MaterialEditorPage from './pages/MaterialEditorPage'

function App() {
  return (
    <div className="h-screen w-screen bg-[#0a0a0a] flex flex-col overflow-hidden">
      <TopBar />
      <div className="flex-1 overflow-y-auto scroll-hidden">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/cure-process" element={<CureProcessPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/material-editor" element={<MaterialEditorPage />} />
        </Routes>
      </div>
    </div>
  )
}

export default App
