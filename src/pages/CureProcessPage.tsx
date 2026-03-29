import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { ArrowRight, DoorOpen, CheckCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import PhaseCard from '@/components/PhaseCard'
import AbortModal from '@/components/AbortModal'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useMaterials } from '@/context/MaterialContext'
import { useHardware } from '@/context/HardwareContext'
import type { PhaseType } from '@/components/PhaseCard'

const phaseColorMap: Record<string, string> = {
  Heating: 'text-orange-400',
  Drying: 'text-blue-400',
  Cure: 'text-purple-400',
  Cooling: 'text-teal-400',
}

const dotColorMap: Record<string, string> = {
  Heating: 'bg-orange-500',
  Drying: 'bg-blue-500',
  Cure: 'bg-purple-500',
  Cooling: 'bg-teal-500',
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
    return steps.map(s => ({
      name: s.process,
      type: s.process.toLowerCase() as PhaseType,
      temp: s.temperature,
      intensity: s.intensity,
      time: s.time,
    }))
  }, [steps])

  // Calculate ramp duration for first heating phase
  const firstHeatingPhase = phases[0]
  const targetTemp = firstHeatingPhase?.temp ?? 80
  const rampDuration = Math.abs(targetTemp - AMBIENT_TEMP) * RAMP_RATE
  const rampProgress = Math.min(100, (rampElapsed / rampDuration) * 100)

  useEffect(() => {
    setPhaseElapsed(new Array(phases.length).fill(0))
  }, [phases.length])

  const totalSteps = phases.length
  const currentPhaseElapsed = phaseElapsed[activePhase] ?? 0

  // Overall progress (ramp time not counted in phase time)
  const totalSeconds = phases.reduce((sum, p) => sum + p.time * 60, 0)
  const totalElapsed = phaseElapsed.reduce((sum, e) => sum + e, 0)
  const overallProgress = Math.min(100, Math.round((totalElapsed / totalSeconds) * 100))

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
        const temp = Math.round(AMBIENT_TEMP + (targetTemp - AMBIENT_TEMP) * progress)
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
  }, [activePhase, phases, isRamping, rampDuration, targetTemp, n2Purging, hw.nitrogenDuration, setChamberTemp, setHeating, setNitrogenActive])

  // Check if current phase is done → advance (with N2 purge after drying)
  useEffect(() => {
    if (!isRunning || isComplete || isRamping || n2Purging) return

    const maxSec = (phases[activePhase]?.time ?? 1) * 60

    if (currentPhaseElapsed >= maxSec) {
      // If drying just finished and nitrogen mode is on → start N2 purge
      const currentPhase = phases[activePhase]
      if (currentPhase?.type === 'drying' && hw.nitrogenMode) {
        setN2Purging(true)
        setN2Elapsed(0)
        setNitrogenActive(true)
        return // Don't advance yet, wait for N2 to finish
      }

      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      } else {
        setIsRunning(false)
        setIsComplete(true)
        setNitrogenActive(false)
        if (pendingLogIds.length > 0) {
          removeLogs(pendingLogIds)
          sessionStorage.removeItem('scure-pending-cure-logs')
        }
      }
    }
  }, [currentPhaseElapsed, activePhase, totalSteps, phases, isRunning, isComplete, isRamping, n2Purging, hw.nitrogenMode, pendingLogIds, removeLogs, setNitrogenActive])

  // After N2 purge finishes → advance to next phase
  useEffect(() => {
    if (!n2Purging && n2Elapsed > 0 && n2Elapsed >= hw.nitrogenDuration) {
      setN2Elapsed(0)
      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      }
    }
  }, [n2Purging, n2Elapsed, hw.nitrogenDuration, activePhase, totalSteps])

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

  // Auto-start on mount
  useEffect(() => {
    if (!isRunning && !isComplete && phases.length > 0 && phaseElapsed.length > 0) {
      setIsRunning(true)
      if (phases[0]?.type === 'heating') {
        setIsRamping(true)
        setRampElapsed(0)
        setChamberTemp(AMBIENT_TEMP)
        setTargetTemp(phases[0].temp ?? 80)
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

    if (phase.type === 'heating') {
      const isActiveRamping = status === 'active' && isRamping
      return {
        gaugeValue: isActiveRamping ? `${hw.chamberTemp}` : status === 'active' ? `${phase.temp}` : status === 'completed' ? `${phase.temp}` : '0',
        gaugeLabel: isActiveRamping ? 'RAMP °C' : 'HOLD °C',
        gaugeProgress: isActiveRamping ? rampProgress : status === 'completed' ? 100 : progress,
        rangeStart: `${AMBIENT_TEMP}°C`,
        rangeEnd: `${phase.temp ?? 80}°C`,
        statusText: isActiveRamping ? `Ramping ${hw.chamberTemp}°C → ${phase.temp}°C ...` : status === 'active' ? `Holding at ${phase.temp}°C ...` : status === 'completed' ? 'Done' : 'Waiting ...',
      }
    }
    if (phase.type === 'drying') {
      return {
        gaugeValue: status !== 'pending' ? `${phase.temp ?? 0}°` : '0°',
        gaugeLabel: 'HOLD',
        gaugeProgress: status === 'completed' ? 100 : progress,
        rangeStart: '0 min',
        rangeEnd: `${phase.time} min`,
        statusText: status === 'active' ? `Drying at ${phase.temp}°C, ${phase.intensity ?? 0}% ...` : status === 'completed' ? 'Done' : 'Waiting ...',
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
    return {
      gaugeValue: '',
      gaugeLabel: '',
      gaugeProgress: status === 'completed' ? 100 : progress,
      rangeStart: `${phase.temp ?? 80}°C`,
      rangeEnd: `${AMBIENT_TEMP}°C`,
      statusText: status === 'active' ? `Cooling to ${AMBIENT_TEMP}°C ...` : status === 'completed' ? 'Done' : 'Waiting ...',
    }
  }

  // Heating phase shows ramp time remaining, then hold time
  const getTimeLeft = (phase: typeof phases[0], index: number) => {
    const elapsed = phaseElapsed[index] ?? 0
    if (index === 0 && phase.type === 'heating' && isRamping && getPhaseStatus(index) === 'active') {
      const rampRemain = Math.max(0, rampDuration - rampElapsed)
      const holdRemain = phase.time * 60
      return formatTime(rampRemain + holdRemain)
    }
    return formatTime(Math.max(0, phase.time * 60 - elapsed))
  }

  return (
    <main className="px-3 pb-2">
      {/* Cure Sequence Header */}
      <div className="bg-card rounded-xl p-3 mt-1">
        <div className="flex items-center justify-between mb-2">
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

        <div className="flex items-center gap-2 mb-2">
          <Progress value={overallProgress} className="flex-1 h-1.5" />
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
      <div className="flex items-center justify-between bg-card rounded-lg px-3 py-2 mt-2 border-l-4 border-cyan-500">
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
              <Badge className="bg-orange-500 text-white text-[10px]">Heating</Badge>
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
      <div className="flex gap-2 mt-2 overflow-x-auto pb-1">
        {phases.map((phase, i) => {
          const gauge = getGaugeInfo(phase, i)
          const elapsed = phaseElapsed[i] ?? 0
          const totalRampAndElapsed = (i === 0 && isRamping) ? rampElapsed : elapsed
          const minE = Math.floor(totalRampAndElapsed / 60)
          const secE = totalRampAndElapsed % 60
          const phaseProgress = (i === 0 && isRamping && getPhaseStatus(i) === 'active')
            ? rampProgress
            : Math.min(100, (elapsed / (phase.time * 60)) * 100)

          return (
            <PhaseCard
              key={i}
              type={phase.type}
              status={getPhaseStatus(i)}
              gaugeValue={gauge.gaugeValue}
              gaugeLabel={gauge.gaugeLabel}
              gaugeProgress={gauge.gaugeProgress}
              timeLeft={getTimeLeft(phase, i)}
              rangeStart={gauge.rangeStart}
              rangeEnd={gauge.rangeEnd}
              rangeProgress={phaseProgress}
              statusText={gauge.statusText}
              minElapsed={String(minE).padStart(2, '0')}
              secElapsed={String(secE).padStart(2, '0')}
              percentComplete={`${Math.round(phaseProgress)}%`}
              onAbort={getPhaseStatus(i) === 'active' ? () => setShowAbort(true) : undefined}
            />
          )
        })}
      </div>

      <div className="text-center mt-1">
        <span className="text-muted-foreground text-[10px]">{formatTime(totalElapsed)} / {formatTime(totalSeconds)}</span>
        {isRamping && <span className="text-orange-400 text-[10px] ml-1">(ramping)</span>}
      </div>

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
