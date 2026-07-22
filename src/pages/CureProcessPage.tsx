import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { ArrowRight, DoorOpen, CheckCircle, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import PhaseCard from '@/components/PhaseCard'
import AbortModal from '@/components/AbortModal'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useMaterials } from '@/context/MaterialContext'
import { useHardware } from '@/context/HardwareContext'
import { useCureHistory } from '@/context/CureHistoryContext'
import { useSystemConfig } from '@/context/SystemConfigContext'
import type { PhaseType } from '@/components/PhaseCard'

const phaseColorMap: Record<string, string> = {
  Heating: 'text-orange-400',
  Drying: 'text-blue-400',
  Cure: 'text-purple-400',
  Cooling: 'text-teal-400',
  Nitrogen: 'text-white',
}

const dotColorMap: Record<string, string> = {
  Heating: 'bg-orange-500',
  Drying: 'bg-blue-500',
  Cure: 'bg-purple-500',
  Cooling: 'bg-teal-500',
  Nitrogen: 'bg-white',
}

function formatTime(totalSeconds: number) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// Simulate ramp time: ~2 seconds per degree from 25°C to target
const RAMP_RATE = 2 // seconds per degree
const AMBIENT_TEMP = 25

export default function CureProcessPage() {
  const navigate = useNavigate()
  const { removeLogs } = usePrintHistory()
  const { materials, selectedMaterialId } = useMaterials()
  const { state: hw, setChamberTemp, setTargetTemp, setHeating, setCooling, setUv, setDoorClosed, setNitrogenActive } = useHardware()
  const { startCure, completeCure, abortCure, recordTelemetry } = useCureHistory()
  const { config: sysConfig } = useSystemConfig()
  const [cureLogId, setCureLogId] = useState<string | null>(null)
  const [activePhase, setActivePhase] = useState(0)
  const [showAbort, setShowAbort] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [isComplete, setIsComplete] = useState(false)

  // Ramp state for heating phase
  const [isRamping, setIsRamping] = useState(false)
  const [rampElapsed, setRampElapsed] = useState(0)

  // Nitrogen purge state (runs after drying if enabled)
  const [n2Purging, setN2Purging] = useState(false)
  const [n2Elapsed, setN2Elapsed] = useState(0)

  // Temperature stall detection (heating + cooling)
  const [tempRetries, setTempRetries] = useState(0)
  const lastCheckTemp = useRef(0)
  const stallCheckRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [showTempWarning, setShowTempWarning] = useState(false)
  const MAX_TEMP_RETRIES = 5
  const STALL_CHECK_INTERVAL = 300000 // 5 minutes

  // Elapsed seconds per phase (only counts AFTER ramp)
  const [phaseElapsed, setPhaseElapsed] = useState<number[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [pendingLogIds] = useState<string[]>(() => {
    try {
      const stored = sessionStorage.getItem('scure-pending-cure-logs')
      if (stored) return JSON.parse(stored)
    } catch { /* ignore */ }
    return []
  })

  const selectedMaterial = materials.find(m => m.id === selectedMaterialId)
  const steps = useMemo(() => selectedMaterial?.steps ?? [], [selectedMaterial])

  const phases = useMemo(() => {
    if (steps.length === 0) {
      return [
        { name: 'Heating', type: 'heating' as PhaseType, temp: 80, intensity: null, time: 1 },
        { name: 'Drying', type: 'drying' as PhaseType, temp: 80, intensity: 30, time: 1 },
        { name: 'Cure', type: 'cure' as PhaseType, temp: null, intensity: 50, time: 1 },
        { name: 'Cooling', type: 'cooling' as PhaseType, temp: 25, intensity: null, time: 1 },
      ]
    }
    // Skip Nitrogen steps if nitrogen is not enabled on the system
    return steps
      .filter(s => s.process !== 'Nitrogen' || hw.nitrogenMode)
      .map(s => ({
        name: s.process,
        type: s.process.toLowerCase() as PhaseType,
        temp: s.temperature,
        intensity: s.intensity,
        time: s.time,
      }))
  }, [steps, hw.nitrogenMode])

  // Ramp start temperature (where ramp begins from)
  const [rampStartTemp, setRampStartTemp] = useState(AMBIENT_TEMP)

  // Calculate ramp for current active phase
  const currentPhaseTemp = phases[activePhase]?.temp ?? 80
  const rampDuration = Math.max(1, Math.abs(currentPhaseTemp - rampStartTemp) * RAMP_RATE)
  const rampProgress = Math.min(100, (rampElapsed / rampDuration) * 100)
  const targetTemp = currentPhaseTemp

  useEffect(() => {
    setPhaseElapsed(new Array(phases.length).fill(0))
  }, [phases.length])

  const totalSteps = phases.length
  const currentPhaseElapsed = phaseElapsed[activePhase] ?? 0

  // Overall progress (includes N2 duration)
  const totalSeconds = phases.reduce((sum, p) => sum + (p.type === 'nitrogen' ? hw.nitrogenDuration : p.time * 60), 0)
  const totalElapsed = phaseElapsed.reduce((sum, e, i) => sum + (phases[i]?.type === 'nitrogen' ? n2Elapsed : e), 0)
  const overallProgress = totalSeconds > 0 ? Math.min(100, Math.round((totalElapsed / totalSeconds) * 100)) : 0

  // Timer tick
  const tick = useCallback(() => {
    // Ramp phase
    if (isRamping) {
      setRampElapsed(prev => {
        const next = prev + 1
        if (next >= rampDuration) {
          setIsRamping(false)
          setChamberTemp(targetTemp)
          setHeating(false)
          return rampDuration
        }
        const progress = next / rampDuration
        const temp = Math.round(rampStartTemp + (targetTemp - rampStartTemp) * progress)
        setChamberTemp(temp)
        return next
      })
      return
    }

    // N2 purge phase (after drying)
    if (n2Purging) {
      setN2Elapsed(prev => {
        const next = prev + 1
        if (next >= hw.nitrogenDuration) {
          setN2Purging(false)
          setNitrogenActive(false)
          return hw.nitrogenDuration
        }
        return next
      })
      return
    }

    // Normal phase timer
    setPhaseElapsed(prev => {
      const next = [...prev]
      const phaseIdx = activePhase
      const maxSec = (phases[phaseIdx]?.time ?? 1) * 60

      if (next[phaseIdx] < maxSec) {
        next[phaseIdx] = next[phaseIdx] + 1
      }
      return next
    })
  }, [activePhase, phases, isRamping, rampDuration, rampStartTemp, targetTemp, n2Purging, hw.nitrogenDuration, setChamberTemp, setHeating, setNitrogenActive])

  // Temperature stall detection: every 1 min during ramp or cooling, check progress
  const isInTempPhase = isRamping || (isRunning && phases[activePhase]?.type === 'cooling')
  useEffect(() => {
    if (!isInTempPhase || showTempWarning) {
      if (stallCheckRef.current) { clearInterval(stallCheckRef.current); stallCheckRef.current = null }
      return
    }
    lastCheckTemp.current = hw.chamberTemp
    stallCheckRef.current = setInterval(() => {
      const isCooling = phases[activePhase]?.type === 'cooling'
      const diff = isCooling
        ? lastCheckTemp.current - hw.chamberTemp   // cooling: should drop ≥1°C
        : hw.chamberTemp - lastCheckTemp.current    // heating: should rise ≥1°C
      const progressed = diff >= 1
      if (!progressed) {
        setTempRetries(prev => {
          const next = prev + 1
          if (next >= MAX_TEMP_RETRIES) {
            setShowTempWarning(true)
            // Pause the process while warning is shown
          }
          return next
        })
      } else {
        setTempRetries(0)
      }
      lastCheckTemp.current = hw.chamberTemp
    }, STALL_CHECK_INTERVAL)
    return () => { if (stallCheckRef.current) { clearInterval(stallCheckRef.current); stallCheckRef.current = null } }
  }, [isInTempPhase, showTempWarning, hw.chamberTemp, activePhase, phases])

  const handleTempWarningContinue = () => {
    setShowTempWarning(false)
    setTempRetries(0)
    // Process continues from where it was
  }

  const handleTempWarningAbort = () => {
    setShowTempWarning(false)
    setIsRunning(false)
    setIsRamping(false)
    setHeating(false)
    setCooling(false)
    setUv(false)
    if (cureLogId) abortCure(cureLogId, activePhase)
    navigate('/')
  }

  // When entering a new phase, start ramp if needed or N2 purge
  useEffect(() => {
    if (!isRunning || isComplete || isRamping || n2Purging) return
    const currentPhase = phases[activePhase]
    if (!currentPhase) return

    // Nitrogen phase → start purge
    if (currentPhase.type === 'nitrogen') {
      setN2Purging(true)
      setN2Elapsed(0)
      setNitrogenActive(true)
      return
    }

    // Phases with temperature that need ramp (not cooling, not nitrogen, not first phase which is handled on mount)
    if (activePhase > 0 && currentPhase.temp != null && currentPhase.type !== 'cooling') {
      const currentTemp = hw.chamberTemp
      if (currentPhase.temp > currentTemp) {
        setIsRamping(true)
        setRampElapsed(0)
        setRampStartTemp(currentTemp)
        setTargetTemp(currentPhase.temp)
        setHeating(true)
      }
    }
  }, [activePhase, isRunning, isComplete, isRamping, n2Purging, phases])

  // Check if current phase is done → advance
  useEffect(() => {
    if (!isRunning || isComplete || isRamping || n2Purging) return

    const currentPhase = phases[activePhase]
    // Nitrogen phases are handled by N2 purge logic, skip here
    if (currentPhase?.type === 'nitrogen') return

    const maxSec = (currentPhase?.time ?? 1) * 60

    if (currentPhaseElapsed >= maxSec) {
      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      } else {
        setIsRunning(false)
        setIsComplete(true)
        setNitrogenActive(false)
        if (cureLogId) completeCure(cureLogId)

        if (pendingLogIds.length > 0) {
          removeLogs(pendingLogIds)
          sessionStorage.removeItem('scure-pending-cure-logs')
        }
      }
    }
  }, [currentPhaseElapsed, activePhase, totalSteps, phases, isRunning, isComplete, isRamping, n2Purging, hw.nitrogenMode, pendingLogIds, removeLogs, setNitrogenActive])

  // After N2 purge finishes → advance to next phase or complete
  useEffect(() => {
    if (!n2Purging && n2Elapsed > 0 && n2Elapsed >= hw.nitrogenDuration) {
      setN2Elapsed(0)
      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      } else {
        setIsRunning(false)
        setIsComplete(true)
        setNitrogenActive(false)
        if (cureLogId) completeCure(cureLogId)
        if (pendingLogIds.length > 0) {
          removeLogs(pendingLogIds)
          sessionStorage.removeItem('scure-pending-cure-logs')
        }
      }
    }
  }, [n2Purging, n2Elapsed, hw.nitrogenDuration, activePhase, totalSteps, cureLogId, completeCure, pendingLogIds, removeLogs, setNitrogenActive])

  // Start/stop timer
  useEffect(() => {
    if (isRunning && !isComplete) {
      timerRef.current = setInterval(tick, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isRunning, isComplete, tick])

  // Telemetry recording every 5 seconds
  const telemetryStartRef = useRef<number>(0)
  useEffect(() => {
    if (!isRunning || isComplete || !cureLogId) return
    telemetryStartRef.current = Date.now()
    const interval = setInterval(() => {
      const elapsed = Math.round((Date.now() - telemetryStartRef.current) / 1000)
      const currentPhase = phases[activePhase]
      const isCure = currentPhase?.type === 'cure'
      const isBleacher = currentPhase?.type === 'bleacher'
      const uvOn = isCure || isBleacher
      const uvType = isCure ? '405nm' as const : isBleacher ? '450nm' as const : null
      // Simulate LED temps based on chamber temp
      const base = hw.chamberTemp
      recordTelemetry(cureLogId, {
        t: elapsed,
        chamberTemp: hw.chamberTemp,
        uvOn,
        uvType,
        ledTemps: {
          right: base + Math.round(Math.random() * 4 - 2),
          left: base + Math.round(Math.random() * 4 - 2),
          door: base + Math.round(Math.random() * 3 - 1),
          back: base + Math.round(Math.random() * 3 - 1),
        }
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [isRunning, isComplete, cureLogId, hw.chamberTemp, activePhase, phases, recordTelemetry])

  // Auto-start on mount
  useEffect(() => {
    if (!isRunning && !isComplete && phases.length > 0 && phaseElapsed.length > 0 && !cureLogId) {
      setIsRunning(true)
      // Log cure start
      const id = startCure(
        selectedMaterial?.name ?? 'Unknown',
        phases.length,
        phases.map(p => p.name),
        phases[0]?.temp ?? null,
        sysConfig.serialNumber
      )
      setCureLogId(id)
      const firstPhase = phases[0]
      if (firstPhase?.temp != null && firstPhase.type !== 'cooling' && firstPhase.type !== 'nitrogen') {
        setIsRamping(true)
        setRampElapsed(0)
        setRampStartTemp(AMBIENT_TEMP)
        setChamberTemp(AMBIENT_TEMP)
        setTargetTemp(firstPhase.temp ?? 80)
        setHeating(true)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseElapsed.length])

  const handleAbort = () => {
    setIsRunning(false)
    setIsRamping(false)
    setN2Purging(false)
    setShowAbort(false)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    if (cureLogId) abortCure(cureLogId, activePhase)
    setTargetTemp(null)
    navigate('/')
  }

  const getPhaseStatus = (index: number) => {
    if (isComplete) return 'completed' as const
    if (index < activePhase) return 'completed' as const
    if (index === activePhase && isRunning) return 'active' as const
    return 'pending' as const
  }

  const nextPhase = activePhase + 1 < totalSteps ? phases[activePhase + 1] : null

  const getNextPhaseDesc = () => {
    if (!nextPhase) return 'Process complete'
    const parts = []
    if (nextPhase.temp) parts.push(`Hold at ${nextPhase.temp}°C`)
    if (nextPhase.intensity) parts.push(`Intensity ${nextPhase.intensity}%`)
    parts.push(`for ${nextPhase.time} min`)
    return parts.join(' ')
  }

  const getGaugeInfo = (phase: typeof phases[0], index: number) => {
    const status = getPhaseStatus(index)
    const elapsed = phaseElapsed[index] ?? 0
    const progress = Math.min(100, (elapsed / (phase.time * 60)) * 100)

    if (phase.type === 'heating' || phase.type === 'drying') {
      const isActiveRamping = status === 'active' && isRamping
      const isActiveHolding = status === 'active' && !isRamping
      const label = phase.type === 'heating' ? 'Heating' : 'Drying'
      // During HOLD (target reached) the gauge shows the remaining time; during ramp it shows temperature
      const remaining = Math.max(0, phase.time * 60 - elapsed)
      return {
        gaugeValue: isActiveRamping ? `${hw.chamberTemp}` : isActiveHolding ? formatTime(remaining) : status === 'completed' ? `${phase.temp}` : '0',
        gaugeLabel: isActiveRamping ? 'RAMP °C' : isActiveHolding ? 'REMAINING' : 'HOLD °C',
        gaugeProgress: isActiveRamping ? rampProgress : status === 'completed' ? 100 : progress,
        rangeStart: `${isActiveRamping ? rampStartTemp : AMBIENT_TEMP}°C`,
        rangeEnd: `${phase.temp ?? 80}°C`,
        statusText: isActiveRamping ? `Ramping ...` : status === 'active' ? `${label} ...` : status === 'completed' ? 'Done' : 'Waiting ...',
      }
    }
    if (phase.type === 'cure') {
      return {
        gaugeValue: '',
        gaugeLabel: '',
        gaugeProgress: status === 'completed' ? 100 : progress,
        rangeStart: '0%',
        rangeEnd: `${phase.intensity ?? 100}%`,
        statusText: status === 'active' ? `UV curing at ${phase.intensity}% ...` : status === 'completed' ? 'Done' : 'Waiting ...',
      }
    }
    if (phase.type === 'nitrogen') {
      const n2Progress = n2Purging ? Math.min(100, (n2Elapsed / hw.nitrogenDuration) * 100) : status === 'completed' ? 100 : 0
      return {
        gaugeValue: n2Purging ? `${hw.nitrogenDuration - n2Elapsed}` : status === 'completed' ? '0' : '',
        gaugeLabel: 'SEC',
        gaugeProgress: n2Progress,
        rangeStart: '0s',
        rangeEnd: `${hw.nitrogenDuration}s`,
        statusText: status === 'active' && n2Purging ? `N₂ purging ...` : status === 'completed' ? 'Done' : 'Waiting ...',
      }
    }
    // Cooling (default)
    return {
      gaugeValue: '',
      gaugeLabel: '',
      gaugeProgress: status === 'completed' ? 100 : progress,
      rangeStart: `${phase.temp ?? 80}°C`,
      rangeEnd: `${AMBIENT_TEMP}°C`,
      statusText: status === 'active' ? `Cooling ...` : status === 'completed' ? 'Done' : 'Waiting ...',
    }
  }

  return (
    <main className="px-3 h-full flex flex-col overflow-hidden">
      {/* Cure Sequence Header */}
      <div className="bg-card rounded-xl p-2 mt-1 shrink-0">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <h2 className="text-foreground text-sm font-bold">
              Cure
              {selectedMaterial && (
                <span className="text-muted-foreground text-xs font-normal ml-1">— {selectedMaterial.name}</span>
              )}
            </h2>
            <div className="flex items-center gap-1.5 bg-secondary rounded-full px-3 py-1">
              <span className="text-muted-foreground text-xs">{Math.min(activePhase + 1, totalSteps)}/{totalSteps}</span>
              <div className="flex gap-0.5 ml-1">
                {phases.map((p, i) => (
                  <div key={i} className={cn(
                    'w-4 h-2 rounded-sm',
                    getPhaseStatus(i) !== 'pending' ? (dotColorMap[p.name] || 'bg-primary') : 'bg-border'
                  )} />
                ))}
              </div>
            </div>
          </div>
          <span className="text-green-400 font-bold text-sm">{overallProgress}%</span>
        </div>

        <div className="flex items-center gap-2 mb-1">
          <Progress value={overallProgress} className="flex-1 h-1" />
        </div>

        <div className="flex justify-between">
          {phases.map((phase, i) => (
            <button
              key={i}
              onClick={() => !isRunning && setActivePhase(i)}
              className={cn(
                'text-xs font-medium transition-colors',
                getPhaseStatus(i) === 'active' ? (phaseColorMap[phase.name] || 'text-primary') :
                getPhaseStatus(i) === 'completed' ? 'text-green-400' : 'text-muted-foreground'
              )}
            >
              {phase.name}
              <span className="text-[9px] text-muted-foreground ml-0.5">{phase.time}m</span>
            </button>
          ))}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between bg-card rounded-lg px-3 py-1.5 mt-1 border-l-4 border-cyan-500 shrink-0">
        <div className="flex items-center gap-2">
          {isComplete ? (
            <>
              <Badge className="bg-green-500 text-white text-[10px]">Done</Badge>
              <span className="text-foreground font-bold text-sm">Cure finished!</span>
            </>
          ) : n2Purging ? (
            <>
              <Badge className="bg-white text-black text-[10px]">N₂</Badge>
              <span className="text-foreground font-bold text-sm">Nitrogen Purge</span>
              <span className="text-muted-foreground text-xs">{hw.nitrogenDuration - n2Elapsed}s remaining</span>
            </>
          ) : isRamping ? (
            <>
              <Badge className="bg-orange-500 text-white text-[10px]">{phases[activePhase]?.name ?? 'Heating'}</Badge>
              <span className="text-foreground font-bold text-sm">{hw.chamberTemp}°C → {targetTemp}°C</span>
              <span className="text-muted-foreground text-xs">Timer starts at target</span>
            </>
          ) : isRunning ? (
            <>
              <Badge variant="outline" className="text-cyan-400 border-cyan-500 text-[10px]">Next</Badge>
              <span className="text-foreground font-bold text-sm">{nextPhase?.name ?? 'Final'}</span>
              <span className="text-muted-foreground text-xs">({getNextPhaseDesc()})</span>
            </>
          ) : (
            <>
              <Badge variant="outline" className="text-cyan-400 border-cyan-500 text-[10px]">Starting</Badge>
              <span className="text-foreground font-bold text-sm">Initializing...</span>
            </>
          )}
        </div>
        {isComplete && <ArrowRight size={20} className="text-green-400" />}
        {isRunning && <ArrowRight size={20} className="text-muted-foreground" />}
      </div>

      {/* Phase Cards */}
      <div className="flex gap-3 mt-1 flex-1 min-h-0 overflow-x-auto overflow-y-hidden scroll-hidden items-stretch px-1" style={{ WebkitOverflowScrolling: 'touch', scrollSnapType: 'x mandatory', touchAction: 'pan-x' }}>
        {phases.map((phase, i) => {
          const gauge = getGaugeInfo(phase, i)
          const elapsed = phaseElapsed[i] ?? 0
          const isPhaseRamping = i === activePhase && isRamping && getPhaseStatus(i) === 'active'
          const totalRampAndElapsed = phase.type === 'nitrogen' ? n2Elapsed : isPhaseRamping ? rampElapsed : elapsed
          const minE = Math.floor(totalRampAndElapsed / 60)
          const secE = totalRampAndElapsed % 60
          const phaseProgress = phase.type === 'nitrogen'
            ? (n2Purging ? Math.min(100, (n2Elapsed / hw.nitrogenDuration) * 100) : getPhaseStatus(i) === 'completed' ? 100 : 0)
            : isPhaseRamping
              ? rampProgress
              : phase.time > 0 ? Math.min(100, (elapsed / (phase.time * 60)) * 100) : 0

          return (
            <PhaseCard
              key={i}
              type={phase.type}
              status={getPhaseStatus(i)}
              gaugeValue={gauge.gaugeValue}
              gaugeLabel={gauge.gaugeLabel}
              gaugeProgress={gauge.gaugeProgress}
              minElapsed={String(minE).padStart(2, '0')}
              secElapsed={String(secE).padStart(2, '0')}
              percentComplete={`${Math.round(phaseProgress)}%`}
              onAbort={getPhaseStatus(i) === 'active' ? () => setShowAbort(true) : undefined}
            />
          )
        })}
      </div>


      {/* Temperature Warning - model distortion risk */}
      {showTempWarning && (
        <div className="fixed inset-0 z-50 bg-background/95 flex flex-col items-center justify-center gap-5">
          <div className="w-20 h-20 rounded-full bg-yellow-500/20 flex items-center justify-center">
            <AlertTriangle size={48} className="text-yellow-500" />
          </div>
          <h2 className="text-foreground text-xl font-bold">Temperature Warning</h2>
          <p className="text-muted-foreground text-sm text-center max-w-xs">
            The system is unable to reach the target temperature of <span className="text-foreground font-semibold">{targetTemp}°C</span>.
            Current temperature: <span className="text-foreground font-semibold">{hw.chamberTemp}°C</span>
          </p>
          <p className="text-yellow-400 text-sm text-center max-w-xs font-medium">
            Continuing may cause distortions in the models.
          </p>
          <p className="text-muted-foreground text-xs text-center">Do you want to continue?</p>
          <div className="flex gap-4 mt-2">
            <button
              onClick={handleTempWarningAbort}
              className="flex items-center gap-2 bg-destructive text-destructive-foreground px-6 py-3 rounded-2xl font-semibold active:scale-95 transition-transform touch-manipulation"
            >
              Abort
            </button>
            <button
              onClick={handleTempWarningContinue}
              className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-3 rounded-2xl font-semibold active:scale-95 transition-transform touch-manipulation"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* Completion Screen */}
      {isComplete && (
        <div className="fixed inset-0 z-50 bg-background/95 flex flex-col items-center justify-center gap-6">
          <div className="w-24 h-24 rounded-full bg-green-500/20 flex items-center justify-center">
            <CheckCircle size={56} className="text-green-500" />
          </div>
          <h2 className="text-foreground text-2xl font-bold">Cure Complete!</h2>
          <p className="text-muted-foreground text-sm text-center max-w-xs">
            The curing process for <span className="text-foreground font-semibold">{selectedMaterial?.name ?? 'material'}</span> has been completed successfully.
          </p>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>Total time: <span className="text-foreground font-semibold">{formatTime(totalElapsed)}</span></span>
            <span>·</span>
            <span>{totalSteps} steps</span>
          </div>
          <button
            onClick={() => { setDoorClosed(false); setTimeout(() => { setDoorClosed(true); navigate('/') }, 500) }}
            className="flex items-center gap-3 bg-primary text-primary-foreground px-8 py-4 rounded-2xl font-semibold text-lg active:scale-95 transition-transform touch-manipulation mt-4"
          >
            <DoorOpen size={24} />
            Open Door
          </button>
        </div>
      )}

      <AbortModal
        isOpen={showAbort}
        onClose={() => setShowAbort(false)}
        onAbort={handleAbort}
      />
    </main>
  )
}
