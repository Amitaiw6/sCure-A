import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Save, RotateCcw, LogOut, Zap, ZapOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TouchNumber } from '@/components/ui/touch-number'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import {
  LED_ZONES, LED_ZONE_LABELS, DEFAULT_LED_FACTORS, applyLedFactors,
  getLedCalibration, saveLedCalibration, resetLedCalibration,
  setDevLedPower, devLedOff, devLog,
} from '@/services/dev-api'
import type { LedZoneValues } from '@/services/dev-api'

const FACTOR_MIN = 0
const FACTOR_MAX = 1.5 // physical output is clamped to 100% regardless
const FACTOR_STEP = 0.01

/**
 * LED Intensity Calibration (Developer Mode)
 *
 * One logical "Requested System Power" drives four physical zones through
 * independent calibration factors:  zone = clamp(power × factor, 0..100).
 * The factors are persisted on the backend and applied by the central
 * calibrated-LED layer everywhere (cure UV, HDT calibration, this screen).
 */
export default function LedCalibrationPage() {
  const navigate = useNavigate()
  const [factors, setFactors] = useState<LedZoneValues>(DEFAULT_LED_FACTORS)
  const [savedFactors, setSavedFactors] = useState<LedZoneValues>(DEFAULT_LED_FACTORS)
  const [requestedPower, setRequestedPower] = useState(80)
  const [ledsLive, setLedsLive] = useState(false)
  const [saveState, setSaveState] = useState<'idle' | 'saved' | 'error'>('idle')

  // Saved factors from the backend (default 1.0 when nothing saved yet)
  useEffect(() => {
    getLedCalibration().then(f => {
      if (f) { setFactors(f); setSavedFactors(f) }
    })
  }, [])

  // Live test drive: push power/factor changes to the hardware (debounced),
  // and never leave the LEDs on when the screen goes away.
  const liveRef = useRef(false)
  useEffect(() => { liveRef.current = ledsLive }, [ledsLive])
  const pushDebounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!ledsLive) return
    if (pushDebounce.current) clearTimeout(pushDebounce.current)
    pushDebounce.current = setTimeout(() => { setDevLedPower(requestedPower, factors) }, 300)
    return () => { if (pushDebounce.current) clearTimeout(pushDebounce.current) }
  }, [ledsLive, requestedPower, factors])
  useEffect(() => () => { if (liveRef.current) devLedOff() }, [])

  const outputs = applyLedFactors(requestedPower, factors)
  const dirty = LED_ZONES.some(z => factors[z] !== savedFactors[z])

  const setZoneFactor = (zone: keyof LedZoneValues, value: number | null) => {
    const v = Math.min(FACTOR_MAX, Math.max(FACTOR_MIN, value ?? 1))
    const rounded = Math.round(v * 100) / 100
    setSaveState('idle')
    setFactors(prev => ({ ...prev, [zone]: rounded }))
    devLog(`${LED_ZONE_LABELS[zone]} LED factor changed`, { factor: rounded })
  }

  const handleSave = async () => {
    const ok = await saveLedCalibration(factors)
    setSaveState(ok ? 'saved' : 'error')
    if (ok) {
      setSavedFactors(factors)
      devLog('LED calibration saved', { ...factors })
    }
    setTimeout(() => setSaveState('idle'), 3000)
  }

  const handleReset = async () => {
    const f = await resetLedCalibration()
    const next = f ?? DEFAULT_LED_FACTORS
    setFactors(next)
    setSavedFactors(next)
    setSaveState('idle')
    devLog('LED calibration reset')
  }

  const toggleLive = () => {
    if (ledsLive) { devLedOff(); setLedsLive(false) }
    else { setLedsLive(true) }
  }

  return (
    <main className="p-3 flex flex-col gap-2 h-full">
      {/* Requested system power */}
      <div className="bg-card rounded-lg p-2.5 flex items-center gap-3">
        <span className="text-muted-foreground text-[11px] shrink-0 w-[150px]">Requested System Power</span>
        <div className="flex-1 relative h-5 flex items-center">
          <Progress value={requestedPower} className="h-1.5 w-full" />
          <input
            type="range" min={0} max={100} step={1} value={requestedPower}
            onChange={e => setRequestedPower(Number(e.target.value))}
            className="absolute inset-0 w-full opacity-0 cursor-pointer touch-manipulation"
          />
        </div>
        <TouchNumber value={requestedPower} onChange={v => setRequestedPower(Math.min(100, Math.max(0, v ?? 0)))}
          min={0} max={100} step={5} suffix="%" className="w-[120px] shrink-0" />
        <Button
          size="sm"
          variant={ledsLive ? 'destructive' : 'outline'}
          className="text-[10px] h-8 px-3 gap-1 shrink-0"
          onClick={toggleLive}
        >
          {ledsLive ? <ZapOff size={12} /> : <Zap size={12} />}
          {ledsLive ? 'LEDs ON — Turn Off' : 'Apply to LEDs'}
        </Button>
      </div>

      {/* Per-zone factors */}
      <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
        {LED_ZONES.map(zone => (
          <div key={zone} className="bg-card rounded-lg p-3 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-foreground text-sm font-semibold">{LED_ZONE_LABELS[zone]}</span>
              <span className="text-muted-foreground text-[10px]">
                Actual Output:{' '}
                <span className="text-amber-400 font-bold text-xs">{outputs[zone].toFixed(1)}%</span>
              </span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-muted-foreground text-[10px] shrink-0">Factor</span>
              <div className="flex-1 relative h-5 flex items-center">
                <Progress value={(factors[zone] / FACTOR_MAX) * 100} className="h-1.5 w-full" />
                <input
                  type="range" min={FACTOR_MIN} max={FACTOR_MAX} step={FACTOR_STEP} value={factors[zone]}
                  onChange={e => setZoneFactor(zone, Number(e.target.value))}
                  className="absolute inset-0 w-full opacity-0 cursor-pointer touch-manipulation"
                />
              </div>
              <TouchNumber
                value={factors[zone]}
                onChange={v => setZoneFactor(zone, v)}
                min={FACTOR_MIN} max={FACTOR_MAX} step={FACTOR_STEP} decimals={2}
                className="w-[110px] shrink-0"
              />
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Button onClick={handleSave} disabled={!dirty && saveState !== 'error'} className="flex-1 gap-1.5 h-9 text-xs">
          <Save size={13} />
          {saveState === 'saved' ? '✓ Calibration Saved' : saveState === 'error' ? '✗ Save Failed — Retry' : 'Save Calibration'}
        </Button>
        <Button variant="outline" onClick={handleReset} className="flex-1 gap-1.5 h-9 text-xs">
          <RotateCcw size={13} />
          Reset to Default
        </Button>
        <Button variant="outline" onClick={() => navigate('/dev')} className="flex-1 gap-1.5 h-9 text-xs">
          <LogOut size={13} />
          Exit
        </Button>
      </div>
      {dirty && (
        <p className={cn('text-[10px] -mt-1', 'text-amber-400')}>
          Unsaved changes — the cure process and HDT calibration use the last saved factors.
        </p>
      )}
    </main>
  )
}
