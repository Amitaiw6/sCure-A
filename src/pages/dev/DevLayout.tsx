import { Navigate, Outlet, Link, useLocation } from 'react-router-dom'
import { LogOut, TerminalSquare } from 'lucide-react'
import { useDevMode } from '@/context/DevModeContext'

/**
 * Shell for every Developer Mode screen: guards the /dev routes (normal
 * mode → straight back to the app), shows the persistent DEVELOPER MODE
 * banner and the always-available Exit Developer Mode action.
 */
export default function DevLayout() {
  const { devMode, exitDevMode } = useDevMode()
  const location = useLocation()
  const onMenu = location.pathname === '/dev'

  if (!devMode) return <Navigate to="/" replace />

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-1.5 bg-amber-500/15 border-y border-amber-500/40 shrink-0">
        <div className="flex items-center gap-2">
          <TerminalSquare size={16} className="text-amber-400" />
          <span className="text-amber-400 text-xs font-bold tracking-[0.2em]">DEVELOPER MODE</span>
          {!onMenu && (
            <Link to="/dev" className="text-muted-foreground text-[11px] underline underline-offset-2 hover:text-foreground ml-2 touch-manipulation">
              Dev Menu
            </Link>
          )}
        </div>
        <button
          onClick={exitDevMode}
          className="flex items-center gap-1.5 text-[11px] font-medium text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 rounded-lg px-2.5 py-1 transition-colors touch-manipulation"
        >
          <LogOut size={12} />
          Exit Developer Mode
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scroll-hidden">
        <Outlet />
      </div>
    </div>
  )
}
