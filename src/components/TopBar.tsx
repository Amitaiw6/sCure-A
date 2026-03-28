import { useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowLeftRight,
  Clock,
  Bell,
  Settings,
  Wifi,
  Thermometer,
} from 'lucide-react'

export default function TopBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const isHome = location.pathname === '/'

  return (
    <header className="flex items-center justify-between px-6 py-4">
      {/* Left side - Logo + Status */}
      <div className="flex items-center gap-4">
        {!isHome && (
          <button
            onClick={() => navigate(-1)}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={22} />
          </button>
        )}
        <h1 className="text-2xl font-bold text-white tracking-wide">sCure</h1>
        <button className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeftRight size={20} />
        </button>
        <span className="bg-sky-500 text-white text-sm font-medium px-4 py-1.5 rounded-full">
          Door Closed
        </span>
      </div>

      {/* Center - Temperature */}
      <div className="flex items-center gap-2 border border-gray-600 rounded-xl px-5 py-2">
        <div className="text-center">
          <p className="text-xs text-gray-400">Chamber Temperature</p>
          <div className="flex items-center justify-center gap-1.5">
            <Thermometer size={16} className="text-gray-400" />
            <span className="text-white font-semibold text-lg">24.0°C</span>
          </div>
        </div>
      </div>

      {/* Right side - Icons */}
      <div className="flex items-center gap-3">
        <IconButton><Clock size={20} /></IconButton>
        <IconButton><span className="text-sm font-bold">N₂</span></IconButton>
        <IconButton><span className="text-xs font-bold">NFC</span></IconButton>
        <IconButton><Bell size={20} /></IconButton>
        <IconButton onClick={() => navigate('/settings')}>
          <Settings size={20} />
        </IconButton>
        <IconButton><Wifi size={20} /></IconButton>
      </div>
    </header>
  )
}

function IconButton({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-10 h-10 rounded-full bg-gray-700/50 flex items-center justify-center text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
    >
      {children}
    </button>
  )
}
