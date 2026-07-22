import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft,
  Bell,
  Settings,
  Globe,
  Thermometer,
  Nfc,
  DoorOpen,
  DoorClosed,
  History,
} from 'lucide-react'
import { useHardware } from '@/context/HardwareContext'
import { useAlerts } from '@/context/AlertsContext'
import SCureLogo from '@/components/SCureLogo'
import { doorOpen } from '@/services/hardware-api'

export default function TopBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const isHome = location.pathname === '/'
  const isCuring = location.pathname === '/cure-process'
  const { state: hw, setDoorClosed } = useHardware()
  const { alertCount, criticalAlerts } = useAlerts()
  const [heatingLong, setHeatingLong] = useState(false)

  // Track if heating has been on for more than 10 seconds
  useEffect(() => {
    if (!hw.isHeating || !hw.heatingStartTime) {
      setHeatingLong(false)
      return
    }
    const remaining = 10000 - (Date.now() - hw.heatingStartTime)
    if (remaining <= 0) {
      setHeatingLong(true)
      return
    }
    const timer = setTimeout(() => setHeatingLong(true), remaining)
    return () => clearTimeout(timer)
  }, [hw.isHeating, hw.heatingStartTime])

  return (
    <header className="flex items-center justify-between px-3 py-2 bg-secondary shrink-0">
      {/* Left side - Logo + Status */}
      <div className="flex items-center gap-2">
        {!isHome && !isCuring && (
          <button
            onClick={() => navigate(-1)}
            className="w-11 h-11 rounded-xl flex items-center justify-center text-muted-foreground hover:text-white active:bg-accent transition-colors touch-manipulation"
          >
            <ArrowLeft size={22} />
          </button>
        )}
        <SCureLogo size={28} color="#ffffff" />
        <h1 className="text-xl font-bold text-white tracking-wide">{hw.systemName}</h1>
      </div>

      {/* Center - Door + Temperature */}
      <div className="flex items-center gap-2">
        {/* Door + Temperature combined */}
        <div className="flex items-center bg-secondary rounded-xl overflow-hidden">
          {/* The door cannot be opened during a cure — hide the control while curing (safety) */}
          {!isCuring && (
            <button
              onClick={() => {
                if (!hw.doorClosed) return
                doorOpen()               // release the real door magnet
                setDoorClosed(false)     // optimistic; the /api/state poll re-syncs
              }}
              disabled={!hw.doorClosed}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors touch-manipulation border-r border-border ${
                !hw.doorClosed
                  ? 'bg-orange-500/15 text-orange-400'
                  : 'text-foreground hover:bg-accent active:scale-95'
              }`}
            >
              {hw.doorClosed ? <DoorClosed size={24} /> : <DoorOpen size={24} />}
              {hw.doorClosed ? 'Open Door' : 'Door Open'}
            </button>
          )}
          <div className="flex items-center gap-2 px-4 py-1.5">
            <Thermometer size={22} className={heatingLong ? 'text-red-500' : 'text-muted-foreground'} />
            <div className="flex flex-col items-end">
              <span className={`font-bold text-base leading-tight ${heatingLong ? 'text-red-500' : 'text-white'}`}>{hw.chamberTemp.toFixed(1)}°C</span>
              {hw.targetTemp !== null && (
                <span className="text-orange-400 text-[10px] leading-tight">Target: {hw.targetTemp}°C</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Icons (min 44x44 touch targets) */}
      <div className="flex items-center gap-1.5">
        {hw.nitrogenMode && (
          <button className="w-12 h-12 rounded-xl flex items-center justify-center touch-manipulation relative">
            <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center transition-colors ${
              hw.nitrogenActive
                ? 'border-white bg-white/20 text-white animate-pulse'
                : 'border-white text-white'
            }`}>
              <span className="text-xs font-bold leading-none">N₂</span>
            </div>
            <span className={`absolute top-1 right-1 w-2 h-2 rounded-full ${hw.nitrogenActive ? 'bg-green-400 animate-pulse' : 'bg-white'}`} />
          </button>
        )}
        {hw.nfcEnabled && <CircledIcon><Nfc size={22} /></CircledIcon>}
        <TouchIcon active={location.pathname === '/cure-history'} onClick={() => { if (!isCuring && location.pathname !== '/cure-history') navigate('/cure-history', { replace: location.pathname !== '/' }) }}>
          <History size={24} className={isCuring ? 'opacity-30' : undefined} />
        </TouchIcon>
        <TouchIcon active={location.pathname === '/alerts'} onClick={() => { if (!isCuring && location.pathname !== '/alerts') navigate('/alerts', { replace: location.pathname !== '/' }) }}>
          <div className="relative">
            <Bell size={24} className={isCuring ? 'opacity-30' : criticalAlerts.length > 0 ? 'text-red-500' : alertCount > 0 ? 'text-orange-400' : undefined} />
            {alertCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-red-500 rounded-full text-[9px] font-bold text-white flex items-center justify-center">
                {alertCount}
              </span>
            )}
          </div>
        </TouchIcon>
        <TouchIcon active={location.pathname === '/settings'} onClick={() => { if (!isCuring && location.pathname !== '/settings') navigate('/settings', { replace: location.pathname !== '/' }) }}><Settings size={24} className={isCuring ? 'opacity-30' : undefined} /></TouchIcon>
        <TouchIcon active={location.pathname === '/network'} onClick={() => { if (!isCuring && location.pathname !== '/network') navigate('/network', { replace: location.pathname !== '/' }) }}>
          <Globe size={24} className={
            isCuring ? 'opacity-30'
              : !hw.networkConnected ? 'text-destructive'
              : location.pathname === '/network' ? undefined /* active → inherit primary (blue) */
              : 'text-white'
          } />
        </TouchIcon>
      </div>
    </header>
  )
}

function TouchIcon({ children, onClick, active }: { children: React.ReactNode; onClick?: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors touch-manipulation ${
        active
          ? 'bg-primary/15 text-primary'
          : 'text-muted-foreground hover:text-white active:bg-accent'
      }`}
    >
      {children}
    </button>
  )
}

function CircledIcon({ children }: { children: React.ReactNode }) {
  return (
    <button className="w-12 h-12 rounded-xl flex items-center justify-center touch-manipulation">
      <div className="w-10 h-10 rounded-full border-2 border-[#444] flex items-center justify-center text-muted-foreground">
        {children}
      </div>
    </button>
  )
}
