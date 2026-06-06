import { useState, useEffect } from 'react'
import SCureLogo from './SCureLogo'

const CHECKS = [
  'CPU & Memory',
  'GPIO Interface',
  'Temperature Sensor',
  'Heater Module',
  'UV LED 405nm',
  'UV LED 450nm',
  'Cooling Fan',
  'Heater Fan',
  'Door Lock Sensor',
  'Damper Motor',
  'N₂ Line Pressure',
  'Network Interface',
  'Storage & Config',
  'API Server',
]

interface BootScreenProps {
  onComplete: () => void
}

export default function BootScreen({ onComplete }: BootScreenProps) {
  const [phase, setPhase] = useState<'logo' | 'checking' | 'done'>('logo')
  const [activeIndex, setActiveIndex] = useState(-1) // currently checking
  const [passedCount, setPassedCount] = useState(0)

  // Phase 1: Logo for 1.5s
  useEffect(() => {
    const t = setTimeout(() => setPhase('checking'), 1500)
    return () => clearTimeout(t)
  }, [])

  // Phase 2: Run checks one by one
  useEffect(() => {
    if (phase !== 'checking') return

    // Start first check
    if (activeIndex === -1) {
      const t = setTimeout(() => setActiveIndex(0), 300)
      return () => clearTimeout(t)
    }

    // Current check is running - complete it after delay
    const duration = 300 + Math.random() * 400
    const t = setTimeout(() => {
      setPassedCount(prev => prev + 1)

      if (activeIndex < CHECKS.length - 1) {
        // Move to next
        setActiveIndex(prev => prev + 1)
      } else {
        // All done
        setActiveIndex(CHECKS.length) // past last
        setPhase('done')
      }
    }, duration)

    return () => clearTimeout(t)
  }, [phase, activeIndex])

  // Phase 3: Done - proceed after 1s
  useEffect(() => {
    if (phase !== 'done') return
    const t = setTimeout(onComplete, 1200)
    return () => clearTimeout(t)
  }, [phase, onComplete])

  const progress = (passedCount / CHECKS.length) * 100

  const getStatus = (i: number) => {
    if (i < passedCount) return 'ok'
    if (i === activeIndex) return 'checking'
    return 'pending'
  }

  return (
    <div className="fixed inset-0 bg-background flex flex-col items-center justify-center z-[9999]">
      {/* Logo */}
      <div className={`transition-all duration-700 ${phase === 'logo' ? 'scale-100 opacity-100' : 'scale-75 opacity-90 -translate-y-8'}`}>
        <SCureLogo size={phase === 'logo' ? 80 : 48} color="#ffffff" />
      </div>

      {phase === 'logo' && (
        <p className="text-cyan-500 text-lg font-bold mt-4 tracking-widest animate-pulse">S-CURE</p>
      )}

      {/* System checks */}
      {phase !== 'logo' && (
        <div className="w-[500px] max-w-[90vw] mt-4 animate-fadeIn">
          <div className="flex items-center justify-between mb-2">
            <span className="text-muted-foreground text-xs uppercase tracking-wider">System Diagnostics</span>
            <span className="text-white text-xs font-mono">{passedCount}/{CHECKS.length}</span>
          </div>

          {/* Progress bar */}
          <div className="w-full h-1 bg-[#1a1a1a] rounded-full mb-4 overflow-hidden">
            <div
              className="h-full bg-white rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* Check list */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            {CHECKS.map((name, i) => {
              const status = getStatus(i)
              return (
                <div key={i} className="flex items-center gap-2 py-0.5">
                  <span className="w-4 h-4 flex items-center justify-center shrink-0">
                    {status === 'pending' && <span className="w-1.5 h-1.5 rounded-full bg-[#333]" />}
                    {status === 'checking' && <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />}
                    {status === 'ok' && <span className="text-green-400 text-sm">&#10003;</span>}
                  </span>
                  <span className={`text-xs transition-colors duration-200 ${
                    status === 'pending' ? 'text-[#444]' :
                    status === 'checking' ? 'text-cyan-400 font-medium' :
                    'text-[#888]'
                  }`}>
                    {name}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Done message */}
          {phase === 'done' && (
            <div className="text-center mt-6 animate-fadeIn">
              <p className="text-green-400 text-sm font-semibold">All systems operational</p>
              <p className="text-muted-foreground text-xs mt-1">Starting sCure...</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
