import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { ArrowRight, DoorOpen, CheckCircle, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import PhaseCard from '@/components/PhaseCard'
import AbortModal from '@/components/AbortModal'
import PauseOverlay from '@/components/PauseOverlay'
import PauseModal from '@/components/PauseModal'
import FanFailModal, { FAN_NAMES, LED_PANEL_NAMES } from '@/components/FanFailModal'
import HeaterFaultModal from '@/components/HeaterFaultModal'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useMaterials } from '@/context/MaterialContext'
import { useHardware } from '@/context/HardwareContext'
import { useCureHistory } from '@/context/CureHistoryContext'
import { useSystemConfig } from '@/context/SystemConfigContext'
import type { PhaseType } from '@/components/PhaseCard'
import type { CoolingMode, TimerMode, UvStartMode } from '@/context/MaterialContext'
import { AMBIENT_TEMP, COOL_RATE_C_PER_MIN, estimateHeatSeconds, estimateProgram } from '@/lib/program-estimate'
import { CHAMBER_SENSOR, FAN_FAILURE, FAN_STOPPED, TEMP_SENSOR, isA, ledNotHeatingCode } from '@/lib/error-codes'
import {
  heatToTargetTemperature, dryToTargetTemperature, cureUv405, cureUv450, cureUvOnly,
  coolToTargetTemperature, stopCureOutputs, doorOpen, setNitrogenValve,
  reportPhaseTiming, ackDoorAbort, runFanTest, setFanOverride,
} from '@/services/hardware-api'

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

// Ramp / cooling rates and the overall-progress total come from the MEASURED
// phase timings (src/lib/program-estimate.ts): the heater does ~13 s/°C up to
// 45 °C and slows a lot above, cooling runs ~1.5 °C/min in medium mode.
// Off-Pi cooling simulation: °C per second per cooling mode
const COOL_RATES: Record<CoolingMode, number> = {
  fast: COOL_RATE_C_PER_MIN.fast / 60, medium: COOL_RATE_C_PER_MIN.medium / 60, slow: COOL_RATE_C_PER_MIN.slow / 60,
}
const COOL_DONE_BAND = 0.5  // °C band around the target that counts as "reached"

/** A heating command refused because the heater's temperature sensor (chamber NTC) is not reading: Err 9010 (9001 on older machines) from the
 *  start pre-flight, or the heater safety's own reason ("thermistor ... disconnected / out of range"). */
function isHeaterSensorRefusal(res: { ok: boolean; code?: number; message?: string }): boolean {
  if (res.ok) return false
  const m = res.message ?? ''
  return (isA(res.code, TEMP_SENSOR) && /TEMP_CHAMBER|chamber|heater/i.test(m)) || /thermistor/i.test(m)
}

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
  const [showPause, setShowPause] = useState(false)
  // Paused = every output off, door released, all clocks frozen. Resume
  // shifts the clock anchors by the pause length and re-sends the phase
  // command, so the step continues exactly where it stopped.
  const [isPaused, setIsPaused] = useState(false)
  // Fan failure: the check before the process starts, and the stop mid-cure (Continue anyway / Stop)
  const [fanFail, setFanFail] = useState<{ fans: string[]; when: 'preflight' | 'running' } | null>(null)
  const [fanPreflight, setFanPreflight] = useState<'pending' | 'checking' | 'ok'>('pending')
  const fanOverriddenRef = useRef<Set<string>>(new Set())
  const fanPreflightRunRef = useRef(false)
  // LED panels must warm up while the UV is on: the four thermistors are sampled when the UV comes on and
  // checked 15 s later; a panel that did not rise pauses the cure and names itself (Stop / Continue anyway)
  const ledCheckRef = useRef<{ at: number; temps: Record<string, number>; intensity: number; done: boolean; bleaching: boolean } | null>(null)
  const ledOverriddenRef = useRef<Set<string>>(new Set())
  const [ledFail, setLedFail] = useState<string[] | null>(null)
  // The heater's temperature sensor (chamber NTC) is not reading: the machine never switches the heater on without it
  // (start refused, Err 9001) and switches a running heater off at once. The program pauses; the operator retries or stops.
  const [heaterFail, setHeaterFail] = useState<{ when: 'start' | 'running'; message: string } | null>(null)
  const heaterAlertHandledRef = useRef(false)
  const pausedAtRef = useRef(0)
  const [isRunning, setIsRunning] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  // Real wall-clock timing: when the program and the current phase ACTUALLY
  // started. Feeds the phase-timing analytics (server/data/phase_timings.json)
  // and the true "Total time" on the completion screen — the step timers alone
  // exclude ramps, so they understate what a program really takes.
  const processStartRef = useRef<number>(0)
  const phaseWallRef = useRef<{ start: number; temp: number; ramp: number | null }>({ start: 0, temp: 0, ramp: null })
  const [wallTotal, setWallTotal] = useState<number | null>(null)

  // Ramp state for heating phase
  const [isRamping, setIsRamping] = useState(false)
  const [rampElapsed, setRampElapsed] = useState(0)

  // Nitrogen purge state (runs after drying if enabled)
  const [n2Purging, setN2Purging] = useState(false)
  const [n2Elapsed, setN2Elapsed] = useState(0)

  // Temperature stall detection (heating + cooling)
  const [, setTempRetries] = useState(0)
  const lastCheckTemp = useRef(0)
  const stallCheckRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [showTempWarning, setShowTempWarning] = useState(false)
  const MAX_TEMP_RETRIES = 5
  const STALL_CHECK_INTERVAL = 300000 // 5 minutes

  // Elapsed seconds per phase (only counts AFTER ramp)
  const [phaseElapsed, setPhaseElapsed] = useState<number[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Elapsed values are computed from performance.now() anchors, never by
  // counting interval ticks: setInterval on the kiosk browser fires late
  // under load and the lag accumulates into minutes over a long cure.
  const rampAnchorRef = useRef(0)
  const n2AnchorRef = useRef(0)
  const holdAnchorRef = useRef<{ phase: number; start: number } | null>(null)

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
        { name: 'Heating', type: 'heating' as PhaseType, temp: 80, intensity: null, time: 1, coolingMode: 'medium' as CoolingMode, uvStartMode: 'at-target' as UvStartMode, timerMode: 'on-target' as TimerMode, vent: false },
        { name: 'Drying', type: 'drying' as PhaseType, temp: 80, intensity: 30, time: 1, coolingMode: 'medium' as CoolingMode, uvStartMode: 'at-target' as UvStartMode, timerMode: 'on-target' as TimerMode, vent: false },
        { name: 'Cure', type: 'cure' as PhaseType, temp: null, intensity: 50, time: 1, coolingMode: 'medium' as CoolingMode, uvStartMode: 'at-target' as UvStartMode, timerMode: 'on-target' as TimerMode, vent: false },
        { name: 'Cooling', type: 'cooling' as PhaseType, temp: 25, intensity: null, time: 1, coolingMode: 'medium' as CoolingMode, uvStartMode: 'at-target' as UvStartMode, timerMode: 'on-target' as TimerMode, vent: false },
      ]
    }
    // Skip Nitrogen steps if nitrogen is not enabled on the system
    return steps
      .filter(s => s.process !== 'Nitrogen' || hw.nitrogenMode)
      .map(s => ({
        name: s.process,
        type: s.process.toLowerCase() as PhaseType,
        // null on a Cure/Bleacher step = UV only, no chamber heating
        temp: s.temperature,
        // StepModal stores the user's UV value in uvIntensity; legacy rows may
        // still carry it in intensity. The hardware expects 5-100%.
        intensity: s.uvIntensity ?? s.intensity,
        time: s.time,
        coolingMode: (s.coolingMode ?? 'medium') as CoolingMode,
        uvStartMode: (s.uvStartMode ?? 'at-target') as UvStartMode,
        // Timer Start: 'on-ramp' = the step timer runs through the ramp;
        // 'on-target' (default) = it starts only at the target temperature.
        timerMode: (s.timerMode ?? 'on-target') as TimerMode,
        // No-heat UV steps: fresh-air ventilation (damper + intake fan)
        vent: !!s.ventilation,
      }))
  }, [steps, hw.nitrogenMode])

  // Send the real hardware command for a phase. Off-Pi (API not connected)
  // this is skipped and the page keeps its local simulation.
  // The hardware can REFUSE a command (door open, fan fault, bad target...) —
  // surface that instead of silently animating a phase that never started.
  const commandedPhaseRef = useRef(-1)
  const [phaseError, setPhaseError] = useState<string | null>(null)
  // deferUv: a cure/bleacher step that starts with a ramp heats FIRST and the
  // UV LEDs stay OFF until the measured chamber temp reaches the target
  // (startPhaseUv below). Steps with UV Start = "On ramp start" (at-start)
  // skip the deferral — cure_uv heats AND lights the LEDs from the ramp start.
  const commandPhase = useCallback(async (phase: (typeof phases)[number], deferUv = false) => {
    if (!hw.apiConnected) return
    const temp = phase.temp ?? hw.chamberTemp
    let res: { ok: boolean; message: string; code?: number } | null = null
    switch (phase.type) {
      case 'heating': res = await heatToTargetTemperature(temp); break
      case 'drying': res = await dryToTargetTemperature(temp); break
      // temp == null on cure/bleacher: UV only — no heater, optional fresh-air vent
      case 'cure':
        res = phase.temp == null ? await cureUvOnly(405, phase.intensity ?? 30, phase.vent)
            : deferUv ? await heatToTargetTemperature(temp)
                      : await cureUv405(temp, phase.intensity ?? 30)
        break
      case 'bleacher':
        res = phase.temp == null ? await cureUvOnly(450, phase.intensity ?? 30, phase.vent)
            : deferUv ? await heatToTargetTemperature(temp)
                      : await cureUv450(temp, phase.intensity ?? 30)
        break
      case 'cooling': res = await coolToTargetTemperature(phase.temp ?? AMBIENT_TEMP, phase.coolingMode); break
    }
    if (res && !res.ok) {
      setPhaseError(res.message || 'The hardware refused the command')
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: res.code ?? 6015 } }))
      if (isHeaterSensorRefusal(res)) {
        // the heater was NOT switched on: freeze the clocks where they are and pop the fault (Retry re-sends the step)
        pausedAtRef.current = performance.now()
        setIsPaused(true)
        setHeating(false)
        setHeaterFail(prev => prev ?? { when: 'start', message: res.message ?? '' })
      }
    } else {
      setPhaseError(null)
    }
  }, [hw.apiConnected, hw.chamberTemp, setHeating])

  // Ramp finished for a cure/bleacher step → NOW turn the UV on (the heating
  // loop keeps running; cure_uv on an active loop just re-targets it).
  const startPhaseUv = useCallback(async (phase: (typeof phases)[number] | undefined) => {
    if (!hw.apiConnected || !phase) return
    if (phase.type !== 'cure' && phase.type !== 'bleacher') return
    if (phase.uvStartMode === 'at-start') return  // UV already on since ramp start
    const temp = phase.temp ?? hw.chamberTemp
    const res = phase.type === 'cure'
      ? await cureUv405(temp, phase.intensity ?? 30)
      : await cureUv450(temp, phase.intensity ?? 30)
    if (!res.ok) {
      setPhaseError(res.message || 'UV command refused')
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: res.code ?? 6015 } }))
      if (isHeaterSensorRefusal(res)) {
        pausedAtRef.current = performance.now()
        setIsPaused(true)
        setHeating(false)
        setHeaterFail(prev => prev ?? { when: 'start', message: res.message ?? '' })
      }
    }
  }, [hw.apiConnected, hw.chamberTemp, setHeating])

  // Ramp start temperature (where ramp begins from)
  const [rampStartTemp, setRampStartTemp] = useState(AMBIENT_TEMP)
  // Chamber temperature at the moment the cooling phase started
  const [coolStartTemp, setCoolStartTemp] = useState(AMBIENT_TEMP)

  // Calculate ramp for current active phase.
  // With real hardware the ramp progress follows the measured chamber
  // temperature; off-Pi it follows the simulated time-based ramp.
  const currentPhaseTemp = phases[activePhase]?.temp ?? 80
  const rampDuration = Math.max(1, estimateHeatSeconds(rampStartTemp, currentPhaseTemp))
  const rampProgress = hw.apiConnected && currentPhaseTemp !== rampStartTemp
    ? Math.min(100, Math.max(0, ((hw.chamberTemp - rampStartTemp) / (currentPhaseTemp - rampStartTemp)) * 100))
    : Math.min(100, (rampElapsed / rampDuration) * 100)
  const targetTemp = currentPhaseTemp

  useEffect(() => {
    setPhaseElapsed(new Array(phases.length).fill(0))
  }, [phases.length])

  const totalSteps = phases.length
  const currentPhaseElapsed = phaseElapsed[activePhase] ?? 0

  // Overall progress: holds + estimated heating ramps + estimated cooling
  // (+ N2 duration) - the real expected length, not just the hold minutes.
  const totalSeconds = useMemo(
    () => estimateProgram(steps.filter(s => s.process !== 'Nitrogen' || hw.nitrogenMode),
                          { nitrogenSeconds: hw.nitrogenMode ? hw.nitrogenDuration : 0 }).totalSeconds,
    [steps, hw.nitrogenMode, hw.nitrogenDuration])
  const totalElapsed = phaseElapsed.reduce((sum, e, i) => sum + (phases[i]?.type === 'nitrogen' ? n2Elapsed : e), 0)
  const overallProgress = totalSeconds > 0 ? Math.min(100, Math.round((totalElapsed / totalSeconds) * 100)) : 0

  // Timer tick
  const tick = useCallback(() => {
    // Ramp phase
    if (isRamping) {
      // Real hardware: the heater is already commanded; the ramp ends when
      // the measured chamber temperature reaches the target.
      if (hw.apiConnected) {
        setRampElapsed(Math.floor((performance.now() - rampAnchorRef.current) / 1000))
        if (hw.chamberTemp >= targetTemp - 0.5) {
          setIsRamping(false)
          setHeating(false)
          // At target: cure/bleacher steps switch the UV LEDs on only now
          startPhaseUv(phases[activePhase])
        }
      } else {
        // Off-Pi simulation: time-based ramp that also fakes the temperature.
        const rampNext = Math.min(rampDuration,
          Math.floor((performance.now() - rampAnchorRef.current) / 1000))
        setRampElapsed(rampNext)
        if (rampNext >= rampDuration) {
          setIsRamping(false)
          setChamberTemp(targetTemp)
          setHeating(false)
        } else {
          const progress = rampNext / rampDuration
          setChamberTemp(Math.round(rampStartTemp + (targetTemp - rampStartTemp) * progress))
        }
      }
      // Timer Start = "On ramp start": the step timer runs THROUGH the ramp,
      // so fall through to the phase-timer update below. "On target" steps
      // (the default) keep the timer parked until the ramp ends.
      if (phases[activePhase]?.timerMode !== 'on-ramp') return
    }

    // N2 purge phase (after drying)
    if (n2Purging) {
      const n2Next = Math.min(hw.nitrogenDuration,
        Math.floor((performance.now() - n2AnchorRef.current) / 1000))
      setN2Elapsed(n2Next)
      if (n2Next >= hw.nitrogenDuration) {
        setN2Purging(false)
        setNitrogenActive(false)
        if (hw.apiConnected) setNitrogenValve(false)   // close the real valve
      }
      return
    }

    // Cooling phase off-Pi: simulate the chamber dropping toward the target
    // at the mode's rate so the temperature-based completion below works.
    const coolingPhase = phases[activePhase]
    if (coolingPhase?.type === 'cooling' && !hw.apiConnected) {
      const target = coolingPhase.temp ?? AMBIENT_TEMP
      if (hw.chamberTemp > target) {
        const rate = COOL_RATES[coolingPhase.coolingMode] ?? COOL_RATES.medium
        setChamberTemp(Math.max(target, hw.chamberTemp - rate))
      }
    }

    // Normal phase timer. The anchor is (re)set lazily on the first tick a
    // phase spends holding — that covers every entry path (run start, phase
    // advance, ramp end) and carries over any seconds already on the clock.
    setPhaseElapsed(prev => {
      const next = [...prev]
      const phaseIdx = activePhase
      const maxSec = (phases[phaseIdx]?.time ?? 1) * 60

      let anchor = holdAnchorRef.current
      if (!anchor || anchor.phase !== phaseIdx) {
        anchor = {
          phase: phaseIdx,
          start: performance.now() - (next[phaseIdx] ?? 0) * 1000,
        }
        holdAnchorRef.current = anchor
      }
      next[phaseIdx] = Math.min(maxSec,
        Math.floor((performance.now() - anchor.start) / 1000))
      return next
    })
  }, [activePhase, phases, isRamping, rampDuration, rampStartTemp, targetTemp, n2Purging, hw.nitrogenDuration, hw.apiConnected, hw.chamberTemp, setChamberTemp, setHeating, setNitrogenActive, startPhaseUv])

  // Temperature stall detection: every 1 min during ramp or cooling, check progress
  const isInTempPhase = !isPaused && (isRamping || (isRunning && phases[activePhase]?.type === 'cooling'))
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
    stopCureOutputs(true)      // abort: outputs stop now, heater fan runs its cooldown
    setShowTempWarning(false)
    setIsRunning(false)
    setIsRamping(false)
    setHeating(false)
    setCooling(false)
    setUv(false)
    if (cureLogId) abortCure(cureLogId, activePhase)
    navigate('/')
  }

  // SAFETY: the door opened mid-process. The server watchdog gives a grace
  // period (10 s) to close it — meanwhile a countdown warning is shown here.
  // Only when the server flags doorAborted (the door STAYED open past the
  // grace) is the program stopped (Err 6016).
  const [doorCountdown, setDoorCountdown] = useState<number | null>(null)
  useEffect(() => {
    if (!isRunning || isComplete || isPaused || !hw.apiConnected || hw.doorClosed !== false) {
      setDoorCountdown(null)
      return
    }
    setDoorCountdown(10)
    const iv = setInterval(
      () => setDoorCountdown(prev => (prev === null || prev <= 0 ? prev : prev - 1)),
      1000)
    return () => clearInterval(iv)
  }, [isRunning, isComplete, isPaused, hw.apiConnected, hw.doorClosed])

  // A door abort latched by an EARLIER run (Err 6016 never acknowledged)
  // must not kill this one: the flag only counts once it has been seen
  // clear during this run. The run start acknowledges the stale flag.
  const staleDoorAbortRef = useRef(false)
  useEffect(() => {
    if (!hw.doorAborted) staleDoorAbortRef.current = false
  }, [hw.doorAborted])
  useEffect(() => {
    if (!isRunning || isComplete) return
    if (!hw.apiConnected || !hw.doorAborted || staleDoorAbortRef.current) return
    setDoorCountdown(null)
    stopCureOutputs(true)
    setIsRunning(false)
    setIsRamping(false)
    setN2Purging(false)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    if (cureLogId) abortCure(cureLogId, activePhase)
    window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: 6016 } }))
    navigate('/')
  }, [isRunning, isComplete, hw.apiConnected, hw.doorAborted, cureLogId, activePhase,
      abortCure, navigate, setHeating, setCooling, setUv, setNitrogenActive])

  // A fan fails DURING the cure (the machine's supervision: 'critical' after 5 s at 0 RPM, or its
  // fan-stop / not-spinning alert naming the fan - 902x / 903x, one per fan, or the grouped 9002 / 9003 of older machines): every output off, the program paused where it is, and the
  // operator decides — stop, or continue anyway without that fan.
  useEffect(() => {
    if (!isRunning || isComplete || isPaused || fanFail || !hw.apiConnected) return
    const health = hw.fanHealth ?? {}
    const failed = Object.entries(health)
      .filter(([name, h]) => h.status === 'critical' && !fanOverriddenRef.current.has(name))
      .map(([name]) => name)
    for (const code of hw.hwAlerts.filter(c => isA(c, FAN_FAILURE) || isA(c, FAN_STOPPED))) {
      const d = hw.alertDetails[String(code)] ?? ''
      for (const name of Object.keys(FAN_NAMES)) {
        if (d.includes(name) && !fanOverriddenRef.current.has(name) && !failed.includes(name)) failed.push(name)
      }
    }
    if (!failed.length) return
    pausedAtRef.current = performance.now()
    setIsPaused(true)
    stopCureOutputs(true)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    setFanFail({ fans: failed, when: 'running' })
  }, [isRunning, isComplete, isPaused, fanFail, hw.apiConnected, hw.fanHealth, hw.hwAlerts, hw.alertDetails, setHeating, setCooling, setUv, setNitrogenActive])

  // The heater's sensor stops reading DURING a heating step: the machine switched the heater off at once (heater safety)
  // and raised Err 9010 (9001 on older machines) with the heater detail. Outputs off, program paused where it is; Retry re-sends the step.
  const heaterCode = hw.hwAlerts.includes(CHAMBER_SENSOR) ? CHAMBER_SENSOR : hw.hwAlerts.includes(TEMP_SENSOR) ? TEMP_SENSOR : null
  const heaterDetail = heaterCode === null ? '' : hw.alertDetails[String(heaterCode)] ?? ''
  useEffect(() => {
    const active = heaterCode !== null && /TEMP_CHAMBER|heater/i.test(heaterDetail)
    if (!active) { heaterAlertHandledRef.current = false; return }
    if (heaterAlertHandledRef.current || !isRunning || isComplete || isPaused || fanFail || ledFail || heaterFail || !hw.apiConnected) return
    heaterAlertHandledRef.current = true
    pausedAtRef.current = performance.now()
    setIsPaused(true)
    stopCureOutputs(true)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    setHeaterFail({ when: 'running', message: heaterDetail })
  }, [isRunning, isComplete, isPaused, fanFail, ledFail, heaterFail, hw.apiConnected, heaterCode, heaterDetail, setHeating, setCooling, setUv, setNitrogenActive])

  // An LED panel that does not warm up within 15 s of the UV coming on (30 s below 60 % power) is not emitting (unplugged, driver,
  // sensor off the module): outputs off, program paused where it is, the operator decides.
  useEffect(() => {
    if (!isRunning || isComplete || isPaused || fanFail || ledFail || heaterFail || !hw.apiConnected || !hw.uvOn) {
      if (!hw.uvOn) ledCheckRef.current = null          // every UV-on stretch gets its own check
      return
    }
    const temps = hw.ledTemps ?? {}
    if (!ledCheckRef.current) {
      const snap: Record<string, number> = {}
      const bleaching = phases[activePhase]?.type === 'bleacher'          // 450 nm strings leave ~half the heat; the door's too little to judge
      for (const k of Object.keys(LED_PANEL_NAMES)) {
        const v = temps[k]
        // a panel still warm (>= 30 °C) was emitting a moment ago and cools faster than it warms — not judged this stretch
        if (typeof v === 'number' && v < 30 && !(bleaching && k === 'door')) snap[k] = v
      }
      ledCheckRef.current = { at: Date.now(), temps: snap, intensity: hw.uvIntensity || 100, done: false, bleaching }
      return
    }
    const c = ledCheckRef.current
    // measured on the test unit at 100 %: healthy panels +1.1 … +1.9 °C in 15 s, a dark panel +0.2 °C (warmth from its neighbours)
    const windowMs = (c.intensity >= 60 && !c.bleaching) ? 15000 : 30000   // low UV power or 450 nm warms the panels slowly: give them 30 s
    if (c.done || Date.now() - c.at < windowMs) return
    c.done = true
    const need = Math.max(0.35, 0.8 * (c.intensity / 100) * (windowMs / 15000))   // 0.8 °C at 100 % in 15 s (slowest healthy panel +0.9, dark +0.2), scaled with power and window
    const cold = Object.entries(c.temps)
      .filter(([k, t0]) => { const t1 = temps[k]; return typeof t1 === 'number' && t1 - t0 < need && !ledOverriddenRef.current.has(k) })
      .map(([k]) => k)
    if (!cold.length) return
    pausedAtRef.current = performance.now()
    setIsPaused(true)
    stopCureOutputs(true)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    setLedFail(cold)
    // one alert per cold panel: 9040 left, 9041 right, 9044 back, 9045 door
    for (const k of cold)
      window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: ledNotHeatingCode(k), detail: `${LED_PANEL_NAMES[k]}: ${(temps[k] as number) - c.temps[k] >= 0 ? '+' : ''}${((temps[k] as number) - c.temps[k]).toFixed(1)} °C in ${windowMs / 1000} s` } }))
  }, [isRunning, isComplete, isPaused, fanFail, ledFail, heaterFail, hw.apiConnected, hw.uvOn, hw.ledTemps, hw.uvIntensity, phases, activePhase, setHeating, setCooling, setUv, setNitrogenActive])

  // When entering a new phase: command the hardware, then start ramp / N2 purge
  useEffect(() => {
    if (!isRunning || isComplete || isRamping || n2Purging) return
    const currentPhase = phases[activePhase]
    if (!currentPhase) return
    if (commandedPhaseRef.current === activePhase) return  // phase already started
    commandedPhaseRef.current = activePhase

    // Nitrogen phase → start purge (opens the real N₂ valve on the IO board)
    if (currentPhase.type === 'nitrogen') {
      setN2Purging(true)
      setN2Elapsed(0)
      n2AnchorRef.current = performance.now()
      setNitrogenActive(true)
      if (hw.apiConnected) {
        setNitrogenValve(true).then(res => {
          if (!res.ok) {
            setPhaseError(res.message || 'Nitrogen valve command refused')
            window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: res.code ?? 6015 } }))
          }
        })
      }
      return
    }

    // Will this phase start with a heat-up ramp? (not cooling, not nitrogen,
    // not first phase which is handled on mount). Cure/bleacher steps that
    // ramp keep the UV off until the target temperature is reached — unless
    // the step's UV Start is "On ramp start", which lights the UV immediately.
    const willRamp = activePhase > 0 && currentPhase.temp != null &&
      currentPhase.type !== 'cooling' && currentPhase.temp > hw.chamberTemp

    commandPhase(currentPhase, willRamp && currentPhase.uvStartMode !== 'at-start')

    // Cooling: remember where the drop starts so the gauge can show real progress
    if (currentPhase.type === 'cooling') {
      setCoolStartTemp(hw.chamberTemp)
    }

    if (willRamp && currentPhase.temp != null) {
      setIsRamping(true)
      setRampElapsed(0)
      rampAnchorRef.current = performance.now()
      setRampStartTemp(hw.chamberTemp)
      setTargetTemp(currentPhase.temp)
      setHeating(true)
    }
  }, [activePhase, isRunning, isComplete, isRamping, n2Purging, phases, commandPhase, hw.chamberTemp, hw.apiConnected, setNitrogenActive, setTargetTemp, setHeating])

  // A phase finished: report its REAL duration (wall-clock, incl. ramp) to the
  // machine's timing log, then re-anchor the clock for the next phase.
  const reportPhaseEnd = useCallback((idx: number) => {
    const p = phases[idx]
    const now = Date.now()
    if (p && cureLogId && phaseWallRef.current.start > 0) {
      reportPhaseTiming(cureLogId, {
        program: selectedMaterial?.name ?? 'Unknown',
        step: idx + 1,
        process: p.name,
        targetTemp: p.temp ?? null,
        plannedMin: p.time ?? 0,
        startedAt: new Date(phaseWallRef.current.start).toISOString(),
        endedAt: new Date(now).toISOString(),
        seconds: Math.round((now - phaseWallRef.current.start) / 1000),
        rampSeconds: phaseWallRef.current.ramp,
        tempStart: phaseWallRef.current.temp,
        tempEnd: hw.chamberTemp,
        // since v0.8.37: lets the next timing review separate cooling modes
        // and UV loads instead of guessing them from the rates
        coolingMode: p.type === 'cooling' ? p.coolingMode : null,
        intensity: p.intensity ?? null,
        timerMode: p.timerMode,
      })
    }
    phaseWallRef.current = { start: now, temp: hw.chamberTemp, ramp: null }
  }, [phases, cureLogId, selectedMaterial, hw.chamberTemp])

  // Capture how much of the current phase was spent ramping to temperature
  const wasRampingRef = useRef(false)
  useEffect(() => {
    if (wasRampingRef.current && !isRamping && phaseWallRef.current.start > 0) {
      phaseWallRef.current.ramp = Math.round((Date.now() - phaseWallRef.current.start) / 1000)
    }
    wasRampingRef.current = isRamping
  }, [isRamping])

  // Check if current phase is done → advance.
  // Time-holds end on the timer; COOLING ends when the measured chamber
  // temperature actually reaches the target (the hardware cooling loop owns
  // the process — a zero/short step time must not cut it short).
  useEffect(() => {
    if (!isRunning || isComplete || n2Purging || isPaused) return

    const currentPhase = phases[activePhase]
    // Nitrogen phases are handled by N2 purge logic, skip here
    if (currentPhase?.type === 'nitrogen') return
    // "On target" timers cannot finish during the ramp; an "On ramp start"
    // timer counts through it and may expire before the target is reached.
    if (isRamping && currentPhase?.timerMode !== 'on-ramp') return

    const maxSec = (currentPhase?.time ?? 1) * 60
    const phaseDone = currentPhase?.type === 'cooling'
      ? hw.chamberTemp <= (currentPhase.temp ?? AMBIENT_TEMP) + COOL_DONE_BAND
      : currentPhaseElapsed >= maxSec

    if (phaseDone) {
      if (isRamping) {          // on-ramp timer expired mid-climb: end the ramp cleanly
        setIsRamping(false)
        setHeating(false)
      }
      reportPhaseEnd(activePhase)
      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      } else {
        stopCureOutputs()
        setIsRunning(false)
        setIsComplete(true)
        setWallTotal(Math.round((Date.now() - processStartRef.current) / 1000))
        setNitrogenActive(false)
        if (cureLogId) completeCure(cureLogId)

        if (pendingLogIds.length > 0) {
          removeLogs(pendingLogIds)
          sessionStorage.removeItem('scure-pending-cure-logs')
        }
      }
    }
  }, [currentPhaseElapsed, activePhase, totalSteps, phases, isRunning, isComplete, isRamping, n2Purging, isPaused, hw.nitrogenMode, hw.chamberTemp, pendingLogIds, removeLogs, setNitrogenActive, reportPhaseEnd, cureLogId, completeCure])

  // After N2 purge finishes → advance to next phase or complete
  useEffect(() => {
    if (!n2Purging && n2Elapsed > 0 && n2Elapsed >= hw.nitrogenDuration) {
      setN2Elapsed(0)
      reportPhaseEnd(activePhase)
      if (activePhase < totalSteps - 1) {
        setActivePhase(prev => prev + 1)
      } else {
        stopCureOutputs()
        setIsRunning(false)
        setIsComplete(true)
        setWallTotal(Math.round((Date.now() - processStartRef.current) / 1000))
        setNitrogenActive(false)
        if (cureLogId) completeCure(cureLogId)
        if (pendingLogIds.length > 0) {
          removeLogs(pendingLogIds)
          sessionStorage.removeItem('scure-pending-cure-logs')
        }
      }
    }
  }, [n2Purging, n2Elapsed, hw.nitrogenDuration, activePhase, totalSteps, cureLogId, completeCure, pendingLogIds, removeLogs, setNitrogenActive, reportPhaseEnd])

  // Start/stop timer
  useEffect(() => {
    if (isRunning && !isComplete && !isPaused) {
      timerRef.current = setInterval(tick, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isRunning, isComplete, isPaused, tick])

  // Telemetry recording: one sample at start, then every 5 seconds.
  // The changing inputs are read through a ref — putting them in the effect
  // deps would tear the interval down on every 1s status poll, so the 5s
  // timer would never fire and runs would end up with no telemetry (and no
  // downloadable report).
  const telemetryStartRef = useRef<number>(0)
  const telemetrySnapRef = useRef({ chamberTemp: hw.chamberTemp, ledTemps: hw.ledTemps, fanHealth: hw.fanHealth, phases, activePhase, isRamping, isPaused })
  telemetrySnapRef.current = { chamberTemp: hw.chamberTemp, ledTemps: hw.ledTemps, fanHealth: hw.fanHealth, phases, activePhase, isRamping, isPaused }
  useEffect(() => {
    if (!isRunning || isComplete || !cureLogId) return
    telemetryStartRef.current = Date.now()
    const sample = () => {
      const { chamberTemp, ledTemps, fanHealth, phases, activePhase, isRamping, isPaused } = telemetrySnapRef.current
      const elapsed = Math.round((Date.now() - telemetryStartRef.current) / 1000)
      const currentPhase = phases[activePhase]
      const isCure = currentPhase?.type === 'cure'
      const isBleacher = currentPhase?.type === 'bleacher'
      // UV is off while still ramping to the cure temperature, except for
      // "On ramp start" steps where it runs through the whole ramp
      const uvOn = !isPaused && (isCure || isBleacher) && (!isRamping || currentPhase?.uvStartMode === 'at-start')
      const uvType = isCure ? '405nm' as const : isBleacher ? '450nm' as const : null
      // Real per-module LED thermistors from the IO board when available;
      // simulated around chamber temp only off-Pi.
      const base = chamberTemp
      const real = ledTemps
      // Tachometer RPM of every fan (from the IO board's fan supervision);
      // undefined off-Pi so the report simply omits the fan chart.
      const fanRpm = fanHealth
        ? Object.fromEntries(Object.entries(fanHealth).map(([f, v]) => [f, v.rpm]))
        : undefined
      recordTelemetry(cureLogId, {
        t: elapsed,
        chamberTemp,
        uvOn,
        uvType,
        fanRpm,
        ledTemps: {
          right: real?.right ?? base + Math.round(Math.random() * 4 - 2),
          left: real?.left ?? base + Math.round(Math.random() * 4 - 2),
          door: real?.door ?? base + Math.round(Math.random() * 3 - 1),
          back: real?.back ?? base + Math.round(Math.random() * 3 - 1),
        }
      })
    }
    sample()  // t=0 — even a run aborted seconds in gets a report
    const interval = setInterval(sample, 5000)
    return () => clearInterval(interval)
  }, [isRunning, isComplete, cureLogId, recordTelemetry])

  // Before any process: every fan (all six) is spun and its tachometer read. A fan that does not
  // turn holds the start and asks the operator: cancel, or continue anyway (recorded on the machine).
  useEffect(() => {
    if (fanPreflight !== 'pending' || isRunning || isComplete || cureLogId || phases.length === 0 || phaseElapsed.length === 0) return
    if (!hw.apiConnected) { setFanPreflight('ok'); return }
    if (fanPreflightRunRef.current) return
    fanPreflightRunRef.current = true
    setFanPreflight('checking')
    // no cancellation here: the state flip to 'checking' re-runs this effect, and a cleanup would discard the answer
    runFanTest('all').then(res => {
      const fans = (res as { fans?: Record<string, { rpm: number; status: string }> }).fans
      // only FAIL holds the start: a WARN fan is worn (9051 territory) but still moves the air it must
      const failed = fans ? Object.entries(fans).filter(([, f]) => f.status === 'FAIL').map(([n]) => n) : []
      if (failed.length) setFanFail({ fans: failed, when: 'preflight' })
      else setFanPreflight('ok')
    }).catch(() => setFanPreflight('ok'))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fanPreflight, phases.length, phaseElapsed.length, hw.apiConnected])

  // Auto-start on mount — once the fan check has passed (or was overridden)
  useEffect(() => {
    if (fanPreflight === 'ok' && !isRunning && !isComplete && phases.length > 0 && phaseElapsed.length > 0 && !cureLogId) {
      setIsRunning(true)
      // A door abort still latched from a previous run is stale: clear it on
      // the machine (same as confirming Err 6016) and ignore it until it drops.
      if (hw.apiConnected && hw.doorAborted) {
        staleDoorAbortRef.current = true
        ackDoorAbort()
      }
      // Anchor the real wall clocks: whole program + first phase
      processStartRef.current = Date.now()
      phaseWallRef.current = { start: Date.now(), temp: hw.chamberTemp, ramp: null }
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
      // First phase always ramps when it has a temperature — cure/bleacher
      // steps hold their UV off until the chamber reaches the target.
      const firstWillRamp = firstPhase?.temp != null &&
        firstPhase.type !== 'cooling' && firstPhase.type !== 'nitrogen'
      if (firstPhase && firstPhase.type !== 'nitrogen') {
        commandedPhaseRef.current = 0
        commandPhase(firstPhase, firstWillRamp && firstPhase.uvStartMode !== 'at-start')
      }
      if (firstPhase?.type === 'cooling') {
        setCoolStartTemp(hw.apiConnected ? hw.chamberTemp : AMBIENT_TEMP)
      }
      if (firstWillRamp) {
        setIsRamping(true)
        setRampElapsed(0)
        rampAnchorRef.current = performance.now()
        // Real hardware: ramp starts from the measured chamber temperature
        const startTemp = hw.apiConnected ? hw.chamberTemp : AMBIENT_TEMP
        setRampStartTemp(startTemp)
        if (!hw.apiConnected) setChamberTemp(AMBIENT_TEMP)
        setTargetTemp(firstPhase.temp ?? 80)
        setHeating(true)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseElapsed.length, fanPreflight])

  // Pause: every output off NOW (immediate — no heater-fan run-on, so the
  // server's door watchdog sees no live output and will not abort while the
  // door stays open), then release the door. Clocks freeze via isPaused.
  const handlePause = () => {
    setShowPause(false)
    pausedAtRef.current = performance.now()
    setIsPaused(true)
    stopCureOutputs(true)
    setHeating(false)
    setCooling(false)
    setUv(false)
    setNitrogenActive(false)
    doorOpen()
    if (!hw.apiConnected) setDoorClosed(false)
  }

  // Resume: shift every clock anchor by the pause length so the step picks
  // up exactly where it stopped, then re-send the command the phase was
  // running — heater + UV come back (UV still deferred if it was mid-ramp
  // with UV Start = at-target), N₂ valve re-opens on a purge step.
  const handleResume = () => {
    const pausedMs = performance.now() - pausedAtRef.current
    rampAnchorRef.current += pausedMs
    n2AnchorRef.current += pausedMs
    if (holdAnchorRef.current) holdAnchorRef.current.start += pausedMs
    phaseWallRef.current.start += pausedMs
    processStartRef.current += pausedMs
    if (!hw.apiConnected) setDoorClosed(true)
    const phase = phases[activePhase]
    if (phase) {
      if (phase.type === 'nitrogen') {
        setNitrogenActive(true)
        if (hw.apiConnected) setNitrogenValve(true)
      } else {
        commandPhase(phase, isRamping && phase.uvStartMode !== 'at-start')
        if (isRamping) setHeating(true)
      }
    }
    setIsPaused(false)
  }

  // "Continue anyway": the machine runs without the failed fan(s) for the rest of this process — recorded
  const clearFanOverrides = useCallback(() => {
    for (const f of Array.from(fanOverriddenRef.current)) setFanOverride(f, false)
    fanOverriddenRef.current.clear()
  }, [])
  useEffect(() => { if (isComplete) clearFanOverrides() }, [isComplete, clearFanOverrides])
  useEffect(() => () => clearFanOverrides(), [clearFanOverrides])

  const handleFanContinue = async () => {
    const fail = fanFail
    setFanFail(null)
    if (!fail) return
    for (const f of fail.fans) { fanOverriddenRef.current.add(f); await setFanOverride(f, true) }
    if (fail.when === 'preflight') setFanPreflight('ok')
    else handleResume()
  }

  const handleLedContinue = () => {
    for (const k of ledFail ?? []) ledOverriddenRef.current.add(k)
    setLedFail(null)
    handleResume()
  }

  const handleLedStop = () => {
    setLedFail(null)
    handleAbort()
  }

  // Retry: the sensor is re-checked by the machine when the step is re-sent (resume re-commands the phase)
  const handleHeaterRetry = () => {
    setHeaterFail(null)
    handleResume()
  }

  const handleHeaterStop = () => {
    setHeaterFail(null)
    handleAbort()
  }

  const handleFanStop = () => {
    const fail = fanFail
    setFanFail(null)
    if (fail?.when === 'preflight') { navigate('/'); return }
    handleAbort()
  }

  const handleAbort = () => {
    clearFanOverrides()
    setIsPaused(false)
    stopCureOutputs(true)      // abort: outputs stop now, heater fan runs its cooldown
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
        statusText: isActiveRamping ? `Ramping...` : status === 'active' ? `${label}...` : status === 'completed' ? 'Done' : 'Waiting...',
      }
    }
    if (phase.type === 'cure') {
      const ventNote = phase.temp == null ? (phase.vent ? ' (no heat, vented)' : ' (no heat)') : ''
      return {
        gaugeValue: '',
        gaugeLabel: '',
        gaugeProgress: status === 'completed' ? 100 : progress,
        rangeStart: '0%',
        rangeEnd: `${phase.intensity ?? 100}%`,
        statusText: status === 'active' ? `UV curing at ${phase.intensity}%${ventNote}...` : status === 'completed' ? 'Done' : 'Waiting...',
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
        statusText: status === 'active' && n2Purging ? `N₂ purging...` : status === 'completed' ? 'Done' : 'Waiting...',
      }
    }
    // Cooling (default): progress follows the MEASURED chamber temperature
    // dropping from the phase-entry temp toward the step's real target.
    const coolTarget = phase.temp ?? AMBIENT_TEMP
    const coolSpan = Math.max(0.1, coolStartTemp - coolTarget)
    const coolProgress = status === 'completed' ? 100
      : status === 'active'
        ? Math.min(100, Math.max(0, ((coolStartTemp - hw.chamberTemp) / coolSpan) * 100))
        : 0
    return {
      gaugeValue: status === 'active' ? `${hw.chamberTemp}` : '',
      gaugeLabel: status === 'active' ? 'COOL °C' : '',
      gaugeProgress: coolProgress,
      rangeStart: `${Math.round(coolStartTemp)}°C`,
      rangeEnd: `${coolTarget}°C`,
      statusText: status === 'active' ? `Cooling to ${coolTarget}°C...` : status === 'completed' ? 'Done' : 'Waiting...',
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
              <span className="text-foreground font-bold text-sm">Cure complete!</span>
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
              <span className="text-muted-foreground text-xs">
                {phases[activePhase]?.timerMode === 'on-ramp' ? 'Timer running — started with the ramp' : 'Timer starts at target'}
              </span>
            </>
          ) : isRunning ? (
            <>
              <Badge variant="outline" className="text-cyan-400 border-cyan-500 text-[10px]">Next</Badge>
              <span className="text-foreground font-bold text-sm">{nextPhase?.name ?? 'Final phase'}</span>
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

      {/* Hardware refused a phase command (door open, fan fault, invalid target...) */}
      {phaseError && (
        <div className="flex items-center gap-2 bg-destructive/15 border border-destructive rounded-lg px-3 py-1.5 mt-1 shrink-0">
          <AlertTriangle size={14} className="text-destructive shrink-0" />
          <span className="text-destructive text-xs font-medium">Hardware: {phaseError}</span>
        </div>
      )}

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
            : phase.type === 'cooling'
              ? gauge.gaugeProgress
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
              onPause={getPhaseStatus(i) === 'active' ? () => setShowPause(true) : undefined}
              centerLabel={(phase.type === 'cure' || phase.type === 'bleacher') && phase.temp == null
                ? (phase.vent ? 'UV + VENT' : 'UV ONLY') : undefined}
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
            Current temperature: <span className="text-foreground font-semibold">{hw.chamberTemp}°C</span>.
          </p>
          <p className="text-yellow-400 text-sm text-center max-w-xs font-medium">
            Continuing may cause distortion of the printed models.
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
            {/* True wall-clock duration since the program started — the step
                timers alone exclude ramp/cool time and understate reality */}
            <span>Total time: <span className="text-foreground font-semibold">{formatTime(wallTotal ?? totalElapsed)}</span></span>
            <span>·</span>
            <span>{totalSteps} steps</span>
          </div>
          <button
            onClick={() => { doorOpen(); setDoorClosed(false); setTimeout(() => { setDoorClosed(true); navigate('/') }, 500) }}
            className="flex items-center gap-3 bg-primary text-primary-foreground px-8 py-4 rounded-2xl font-semibold text-lg active:scale-95 transition-transform touch-manipulation mt-4"
          >
            <DoorOpen size={24} />
            Open Door
          </button>
        </div>
      )}

      {fanPreflight === 'checking' && (
        <div className="fixed inset-x-0 top-14 z-40 text-center text-xs text-muted-foreground">Checking all fans before starting…</div>
      )}

      <FanFailModal
        isOpen={!!fanFail}
        fans={fanFail?.fans ?? []}
        when={fanFail?.when ?? 'running'}
        onContinue={handleFanContinue}
        onStop={handleFanStop}
      />

      <FanFailModal
        isOpen={!!ledFail}
        kind="led"
        fans={ledFail ?? []}
        when="running"
        onContinue={handleLedContinue}
        onStop={handleLedStop}
      />

      <HeaterFaultModal
        isOpen={!!heaterFail}
        when={heaterFail?.when ?? 'start'}
        message={heaterFail?.message}
        onRetry={handleHeaterRetry}
        onStop={handleHeaterStop}
      />

      <AbortModal
        isOpen={showAbort}
        onClose={() => setShowAbort(false)}
        onAbort={handleAbort}
        chamberTemp={hw.chamberTemp}
      />

      <PauseModal
        isOpen={showPause}
        onClose={() => setShowPause(false)}
        onPause={handlePause}
        chamberTemp={hw.chamberTemp}
      />

      {/* Deliberate pause: outputs off, door released; Continue once the door is closed */}
      {isPaused && !fanFail && !ledFail && !heaterFail && (
        <PauseOverlay
          doorClosed={hw.doorClosed}
          chamberTemp={hw.chamberTemp}
          phaseName={phases[activePhase]?.name ?? 'current'}
          apiConnected={hw.apiConnected}
          onContinue={handleResume}
          onStop={handleAbort}
        />
      )}

      {/* Door opened mid-process: grace-period countdown before the server
          aborts the run (Err 6016). Closing the door resumes normally. */}
      {doorCountdown !== null && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center">
          <div className="bg-zinc-900 border-2 border-red-500 rounded-2xl p-6 mx-8 max-w-md text-center">
            <AlertTriangle size={44} className="text-red-500 mx-auto mb-3" />
            <h2 className="text-xl font-bold text-white mb-2">
              Door Open — Process Paused
            </h2>
            <p className="text-zinc-300">
              The chamber door was opened during an active process.
              The process cannot continue while the door is open.
            </p>
            <p className="text-zinc-300 mt-1 font-semibold">
              Close the door now, or the process will be aborted in
            </p>
            <div className="text-5xl font-bold text-red-500 my-3">{doorCountdown}</div>
            <p className="text-zinc-500 text-sm">seconds</p>
          </div>
        </div>
      )}
    </main>
  )
}
