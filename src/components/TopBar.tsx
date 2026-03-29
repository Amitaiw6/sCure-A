import { useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowLeftRight,
  Clock,
  Bell,
  Settings,
  Wifi,
  Thermometer,
  Nfc,
} from 'lucide-react'

export default function TopBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const isHome = location.pathname === '/'

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-[#1a1a1a] shrink-0">
      {/* Left side - Logo + Status */}
      <div className="flex items-center gap-3">
        {!isHome && (
          <button
            onClick={() => navigate(-1)}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
        )}
        <h1 className="text-xl font-bold text-white tracking-wide">sCure</h1>
        <button className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeftRight size={18} />
        </button>
      </div>

      {/* Center - Door Status + Temperature */}
      <div className="flex items-center gap-3">
        <span className="bg-sky-500 text-white text-xs font-medium px-3 py-1 rounded-full">
          Door Closed
        </span>
        <div className="flex items-center gap-2 border border-[#333] rounded-xl px-4 py-1.5">
          <div className="text-center">
            <p className="text-[10px] text-gray-400">Chamber Temperature</p>
            <div className="flex items-center justify-center gap-1">
              <Thermometer size={14} className="text-gray-400" />
              <span className="text-white font-semibold text-base">24.0°C</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Icons */}
      <div className="flex items-center gap-2">
        <PlainIcon><Clock size={18} /></PlainIcon>
        <CircledIcon><span className="text-xs font-bold">N₂</span></CircledIcon>
        <CircledIcon><Nfc size={16} /></CircledIcon>
        <PlainIcon><Bell size={18} /></PlainIcon>
        <PlainIcon onClick={() => navigate('/settings')}>
          <Settings size={18} />
        </PlainIcon>
        <PlainIcon><Wifi size={18} /></PlainIcon>
      </div>
    </header>
  )
}

function PlainIcon({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
    >
      {children}
    </button>
  )
}

function CircledIcon({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-8 h-8 rounded-full border border-[#444] flex items-center justify-center text-gray-400">
      {children}
    </div>
  )
}
