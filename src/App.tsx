import { Routes, Route } from 'react-router-dom'
import TopBar from './components/TopBar'
import HomePage from './pages/HomePage'
import CureProcessPage from './pages/CureProcessPage'
import SettingsPage from './pages/SettingsPage'
import MaterialEditorPage from './pages/MaterialEditorPage'

function App() {
  return (
    <div className="min-h-screen bg-[#1a1a2e]">
      <div className="max-w-5xl mx-auto">
        <TopBar />
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
