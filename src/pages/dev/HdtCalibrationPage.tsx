import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Play, OctagonX, Download, CheckCircle2, XCircle, CircleAlert,
  Thermometer, Activity, Eye, EyeOff, RotateCcw,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { TouchNumber } from '@/components/ui/touch-number'
import { cn } from '@/lib/utils'
import { exportCsvToUsb } from '@/services/hardware-api'
import { generateHdtReport } from '@/lib/hdt-report'
import {
  LED_ZONES, LED_ZONE_LABELS, applyLedFactors,
  getPicologStatus, getHdtStatus, hdtStart, hdtAbort, hdtReset, fetchHdtCsv, devLog,
} from '@/services/dev-api'
import type { PicologStatus, HdtStatus, HdtSample } from '@/services/dev-api'

const POLL_MS = 1000
const CHART_MAX_POINTS = 900 // downsample beyond this so long runs stay smooth

function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return '--'
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return h > 0 ? `${h}h ${m}m ${String(r).padStart(2, '0')}s` : `${m}m ${String(r).padStart(2, '0')}s`
}

function fmtClock(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

const STEP_STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  PASS: { label: 'PASS', cls: 'text-green-400' },
  RUNNING: { label: 'RUNNING', cls: 'text-amber-400' },
  NOT_CONVERGED: { label: 'NOT CONVERGED', cls: 'text-orange-400' },
  HDT_LIMIT: { label: 'HDT LIMIT', cls: 'text-destructive' },
  ABORTED: { label: 'ABORTED', cls: 'text-destructive' },
  NOT_TESTED: { label: 'NOT TESTED', cls: 'text-muted-foreground' },
}

const FINAL_STATUS_STYLE: Record<string, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  COMPLETED: { label: 'COMPLETED', cls: 'text-green-400', icon: CheckCircle2 },
  HDT_LIMIT_REACHED: { label: 'HDT LIMIT REACHED', cls: 'text-orange-400', icon: CircleAlert },
  ABORTED_BY_USER: { label: 'ABORTED BY USER', cls: 'text-destructive', icon: XCircle },
  SENSOR_ERROR: { label: 'SENSOR ERROR', cls: 'text-destructive', icon: XCircle },
  NOT_CONVERGED: { label: 'NOT CONVERGED', cls: 'text-orange-400', icon: CircleAlert },
}

/**
 * Material HDT Calibration (Developer Mode)
 *
 * UI only — the calibration itself is a state machine on the backend
 * (server/hdt_calibration.py) that sweeps calibrated system LED power
 * 10→90% against the entered material HDT, with the PicoLog TC-08 CH1
 * as the model-temperature feedback. This screen configures, watches
 * (1 Hz poll + incremental samples) and aborts it, and exports reports.
 */
export default function HdtCalibrationPage() {
  const [hdtC, setHdtC] = useState<number | null>(65)
  const [marginC, setMarginC] = useState<number | null>(2)
  const [pico, setPico] = useState<PicologStatus | null>(null)
  const [status, setStatus] = useState<HdtStatus | null>(null)
  const [samples, setSamples] = useState<HdtSample[]>([])
  const [showOutputs, setShowOutputs] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [exportState, setExportState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle')
  const [htmlState, setHtmlState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle')
  const samplesRef = useRef<HdtSample[]>([])

  const running = status?.running ?? false
  const finished = !!status?.finalStatus && !running
  const inSetup = !running && !finished

  // Single 1 Hz poll drives everything: state machine status, live PicoLog
  // health, and incremental temperature samples for the graph.
  const poll = useCallback(async () => {
    const s = await getHdtStatus(samplesRef.current.length)
    if (!s) return
    if (s.samples && s.samples.length > 0) {
      // A fresh run restarts sample numbering — resync instead of appending
      const first = s.samples[0]
      const next = s.sampleCount <= samplesRef.current.length + s.samples.length && first.t >= (samplesRef.current.at(-1)?.t ?? -1)
        ? [...samplesRef.current, ...s.samples]
        : s.samples
      samplesRef.current = next
      setSamples(next)
    } else if (s.sampleCount === 0 && samplesRef.current.length > 0 && s.running) {
      samplesRef.current = []
      setSamples([])
    }
    setStatus(s)
    setPico(s.picolog)
  }, [])

  useEffect(() => {
    const first = setTimeout(poll, 0)      // immediate async kick-off
    const id = setInterval(poll, POLL_MS)
    return () => { clearTimeout(first); clearInterval(id) }
  }, [poll])

  // Extra PicoLog status refresh while configuring (drives the Start gate)
  useEffect(() => {
    if (!inSetup) return
    const id = setInterval(async () => setPico(await getPicologStatus()), 2000)
    return () => clearInterval(id)
  }, [inSetup])

  const canStart =
    inSetup &&
    hdtC != null && hdtC >= 30 &&
    !!pico?.connected && !!pico?.ch1Available && pico?.temperature != null

  const handleStart = async () => {
    setStartError(null)
    setExportState('idle')
    devLog('Material HDT entered', { hdtC, marginC })
    const res = await hdtStart({ hdtC: hdtC!, safetyMarginC: marginC ?? 2 })
    if (!res?.ok) {
      setStartError(res?.message ?? 'Failed to start calibration (API unreachable)')
      return
    }
    samplesRef.current = []
    setSamples([])
    poll()
  }

  const handleAbort = async () => {
    if (!confirm('Abort HDT calibration? LEDs turn off immediately; collected data is preserved.')) return
    await hdtAbort()
    poll()
  }

  const handleExportCsv = async () => {
    setExportState('busy')
    const csv = await fetchHdtCsv()
    if (!csv) { setExportState('error'); setTimeout(() => setExportState('idle'), 3000); return }
    const filename = `hdt-calibration-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')}.csv`
    // Machine-first: write to the USB drive; off-Pi fall back to a browser download
    const usb = await exportCsvToUsb(filename, csv)
    if (!usb.ok && usb.code === undefined) {
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    }
    devLog('Report exported', { filename })
    setExportState(usb.ok || usb.code === undefined ? 'done' : 'error')
    setTimeout(() => setExportState('idle'), 3000)
  }

  /* ---------- Chart data ---------- */

  const chart = useMemo(() => {
    const src = samples
    const stride = Math.max(1, Math.ceil(src.length / CHART_MAX_POINTS))
    const pts = src.filter((_, i) => i % stride === 0 || i === src.length - 1)
    // Power-level transition markers: first sample of each new test step
    const transitions: { t: number; power: number }[] = []
    let lastStep = -2
    for (const s of src) {
      if (s.step !== lastStep && s.step >= 0) transitions.push({ t: s.t, power: s.power })
      lastStep = s.step
    }
    return { pts, transitions }
  }, [samples])

  const effHdt = running || finished ? status?.hdtC ?? hdtC : hdtC
  const effMargin = running || finished ? status?.safetyMarginC ?? marginC : marginC

  const factors = status?.factors
  const previewOutputs = factors && status?.currentPower != null
    ? applyLedFactors(status.currentPower, factors)
    : null
  const liveOutputs = status?.outputs ?? previewOutputs

  const finalStyle = status?.finalStatus ? FINAL_STATUS_STYLE[status.finalStatus] : null

  return (
    <main className="p-3 flex flex-col gap-2 h-full min-h-0">
      {/* ===== Top row: config / live status + PicoLog ===== */}
      <div className="flex gap-2">
        {/* Material HDT + margin */}
        <div className="bg-card rounded-lg p-2.5 flex-1">
          <div className="flex items-center gap-3">
            <Thermometer size={16} className="text-amber-400 shrink-0" />
            <div className="flex-1 grid grid-cols-2 gap-x-4 gap-y-1 items-center">
              <span className="text-muted-foreground text-[11px]">Material HDT</span>
              {inSetup ? (
                <TouchNumber value={hdtC} onChange={setHdtC} min={30} max={150} step={1} suffix="°C" className="w-[120px]" />
              ) : (
                <span className="text-foreground text-sm font-bold">{effHdt}°C</span>
              )}
              <span className="text-muted-foreground text-[11px]">Safety Margin</span>
              {inSetup ? (
                <TouchNumber value={marginC} onChange={setMarginC} min={0} max={10} step={0.5} suffix="°C" className="w-[120px]" />
              ) : (
                <span className="text-foreground text-sm font-bold">{effMargin}°C</span>
              )}
              <span className="text-muted-foreground text-[11px]">Recommended Max Temp</span>
              <span className="text-orange-400 text-sm font-bold">
                {effHdt != null && effMargin != null ? `${(effHdt - effMargin).toFixed(1)}°C` : '--'}
              </span>
            </div>
          </div>
        </div>

        {/* PicoLog status */}
        <div className="bg-card rounded-lg p-2.5 w-[250px] shrink-0">
          <div className="space-y-1">
            <StatusRow label="PicoLog TC-08" ok={!!pico?.connected} okText="Connected" failText="Not Connected" />
            <StatusRow label="Channel 1" ok={!!pico?.ch1Available} okText="Available" failText="Not Available" />
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-[11px]">CH1 Temperature</span>
              <span className={cn('text-sm font-bold', pico?.temperature != null ? 'text-foreground' : 'text-muted-foreground')}>
                {pico?.temperature != null ? `${pico.temperature.toFixed(1)}°C` : 'N/A'}
              </span>
            </div>
            {pico?.error && <p className="text-destructive text-[9px] leading-tight">{pico.error}</p>}
          </div>
        </div>
      </div>

      {/* ===== Live run stats ===== */}
      {(running || finished) && status && (
        <div className="bg-card rounded-lg p-2.5 flex items-center gap-4">
          <Activity size={16} className={cn('shrink-0', running ? 'text-amber-400 animate-pulse' : 'text-muted-foreground')} />
          <Stat label="Test" value={`${Math.min(status.stepIndex + 1, status.totalSteps)} of ${status.totalSteps}`} />
          <Stat label="Test Power" value={status.currentPower != null ? `${status.currentPower}%` : '--'} highlight />
          <Stat label="Raw CH1" value={status.rawTemp != null ? `${status.rawTemp.toFixed(1)}°C` : '--'} />
          <Stat label="Average" value={status.avgTemp != null ? `${status.avgTemp.toFixed(1)}°C` : '--'} />
          <Stat label="Step Time" value={fmtClock(status.stepElapsedSec)} />
          <Stat label="Total" value={fmtDuration(status.totalElapsedSec)} />
          <div className="flex-1 min-w-0 text-right">
            {finalStyle ? (
              <span className={cn('text-xs font-bold inline-flex items-center gap-1.5', finalStyle.cls)}>
                <finalStyle.icon size={14} /> {finalStyle.label}
              </span>
            ) : (
              <span className="text-muted-foreground text-[11px]">{status.message}</span>
            )}
          </div>
        </div>
      )}

      {/* Calibrated physical outputs (engineering detail, toggleable) */}
      {(running || finished) && liveOutputs && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowOutputs(v => !v)}
            className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground touch-manipulation"
          >
            {showOutputs ? <EyeOff size={11} /> : <Eye size={11} />}
            Calibrated Physical Outputs
          </button>
          {showOutputs && (
            <div className="flex gap-3">
              {LED_ZONES.map(z => (
                <span key={z} className="text-[10px] text-muted-foreground">
                  {LED_ZONE_LABELS[z]}: <span className="text-amber-400 font-bold">{liveOutputs[z].toFixed(1)}%</span>
                  {factors && <span className="text-muted-foreground/60"> (×{factors[z].toFixed(2)})</span>}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ===== Middle: graph + (when finished) results ===== */}
      <div className="flex-1 min-h-0 flex gap-2">
        {/* Temperature vs time */}
        <div className="bg-card rounded-lg p-2 flex-1 min-w-0 flex flex-col">
          <span className="text-muted-foreground text-[10px] px-1">Model Temperature [°C] vs Time</span>
          <div className="flex-1 min-h-0">
            {chart.pts.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart.pts} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="#333" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t" type="number" domain={['dataMin', 'dataMax']}
                    tickFormatter={v => fmtClock(v)} tick={{ fontSize: 9, fill: '#888' }} stroke="#555"
                  />
                  {/* Y domain always spans up past the HDT line so the safety
                      references stay visible from the very first samples */}
                  <YAxis tick={{ fontSize: 9, fill: '#888' }} stroke="#555"
                    domain={[
                      (dataMin: number) => Math.floor(Math.min(dataMin, 20)),
                      (dataMax: number) => Math.ceil(Math.max(dataMax + 2, (effHdt ?? 0) + 4)),
                    ]} />
                  <Tooltip
                    contentStyle={{ background: '#1b1b1b', border: '1px solid #444', borderRadius: 8, fontSize: 10 }}
                    labelFormatter={v => `t = ${fmtClock(Number(v))}`}
                    formatter={(value, name) => [`${Number(value).toFixed(1)}°C`, String(name)]}
                  />
                  {effHdt != null && (
                    <ReferenceLine y={effHdt} stroke="#ef4444" strokeDasharray="6 3"
                      label={{ value: `HDT ${effHdt}°C`, fill: '#ef4444', fontSize: 9, position: 'insideTopRight' }} />
                  )}
                  {effHdt != null && effMargin != null && effMargin > 0 && (
                    <ReferenceLine y={effHdt - effMargin} stroke="#f97316" strokeDasharray="4 3"
                      label={{ value: `HDT−${effMargin}°C`, fill: '#f97316', fontSize: 9, position: 'insideBottomRight' }} />
                  )}
                  {chart.transitions.map(tr => (
                    <ReferenceLine key={tr.t} x={tr.t} stroke="#666" strokeDasharray="2 3"
                      label={{ value: `${tr.power}%`, fill: '#aaa', fontSize: 8, position: 'top' }} />
                  ))}
                  <Line type="monotone" dataKey="raw" name="Raw CH1" stroke="#60a5fa" strokeWidth={1} dot={false} isAnimationActive={false} connectNulls />
                  <Line type="monotone" dataKey="avg" name="Average" stroke="#facc15" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground text-xs">
                {running ? 'Collecting temperature data…' : 'No temperature data yet'}
              </div>
            )}
          </div>
        </div>

        {/* Results panel (visible once there is anything to show) */}
        {status && status.results.length > 0 && (running || finished) && (
          <div className="bg-card rounded-lg p-2 w-[290px] shrink-0 overflow-y-auto scroll-hidden">
            {finished && (
              <div className="mb-2 pb-2 border-b border-border">
                <div className="text-muted-foreground text-[10px]">Recommended System LED Power</div>
                <div className={cn('text-2xl font-bold', status.recommendedPower != null ? 'text-green-400' : 'text-muted-foreground')}>
                  {status.recommendedPower != null ? `${status.recommendedPower}%` : 'None'}
                </div>
                {status.recommendedPower != null && factors && (
                  <div className="text-[9px] text-muted-foreground leading-snug mt-0.5">
                    {LED_ZONES.map(z =>
                      `${LED_ZONE_LABELS[z]} ${applyLedFactors(status.recommendedPower!, factors)[z].toFixed(1)}%`
                    ).join(' · ')}
                  </div>
                )}
              </div>
            )}
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="font-normal pb-1">Power</th>
                  <th className="font-normal pb-1">Stable</th>
                  <th className="font-normal pb-1">Time</th>
                  <th className="font-normal pb-1 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {status.results.map(r => {
                  const st = STEP_STATUS_STYLE[r.status] ?? STEP_STATUS_STYLE.NOT_TESTED
                  return (
                    <tr key={r.power} className="border-t border-border/50">
                      <td className="py-1 font-semibold text-foreground">{r.power}%</td>
                      <td className="py-1 text-foreground">{r.stableTemp != null ? `${r.stableTemp.toFixed(1)}°C` : '--'}</td>
                      <td className="py-1 text-muted-foreground">{r.timeToStabilitySec != null ? fmtDuration(r.timeToStabilitySec) : '--'}</td>
                      <td className={cn('py-1 text-right font-bold', st.cls)}>{st.label}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {finished && (
              <div className="mt-2 pt-2 border-t border-border space-y-0.5 text-[9px] text-muted-foreground">
                <div>Duration: {fmtDuration(status.totalElapsedSec)}</div>
                <div>Max measured temp: {status.maxMeasuredTemp != null ? `${status.maxMeasuredTemp.toFixed(1)}°C` : '--'}</div>
                {pico?.deviceInfo && <div>Device: {pico.deviceInfo} · CH1</div>}
                {factors && <div>Factors: {LED_ZONES.map(z => `${LED_ZONE_LABELS[z]} ${factors[z].toFixed(2)}`).join(', ')}</div>}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ===== Bottom: actions ===== */}
      <div className="flex items-center gap-2">
        {inSetup && (
          <>
            <Button onClick={handleStart} disabled={!canStart} className="flex-1 gap-1.5 h-10 text-sm">
              <Play size={15} />
              Start Calibration
            </Button>
            {!canStart && (
              <span className="text-muted-foreground text-[10px] flex-1">
                {pico?.connected
                  ? pico?.ch1Available
                    ? pico?.temperature == null ? 'Waiting for a valid CH1 temperature…' : hdtC == null || hdtC < 30 ? 'Enter a material HDT (≥ 30°C)' : ''
                    : 'CH1 is not available — check the thermocouple.'
                  : 'Connect the PicoLog TC-08 to enable calibration.'}
              </span>
            )}
            {startError && <span className="text-destructive text-[10px] flex-1">{startError}</span>}
          </>
        )}
        {running && (
          <Button variant="destructive" onClick={handleAbort} className="flex-1 gap-1.5 h-10 text-sm">
            <OctagonX size={15} />
            Abort Calibration
          </Button>
        )}
        {finished && (
          <>
            <Button onClick={handleExportCsv} disabled={exportState === 'busy'} className="flex-1 gap-1.5 h-9 text-xs">
              <Download size={13} />
              {exportState === 'busy' ? 'Exporting…' : exportState === 'done' ? '✓ CSV Exported' : exportState === 'error' ? '✗ Export Failed' : 'Export Report (CSV)'}
            </Button>
            <Button
              variant="outline"
              disabled={htmlState === 'busy' || !status}
              onClick={async () => {
                if (!status) return
                setHtmlState('busy')
                const res = await generateHdtReport(status, samples)
                devLog('Report exported', { format: 'html', ok: res.ok })
                setHtmlState(res.ok ? 'done' : 'error')
                setTimeout(() => setHtmlState('idle'), 3000)
              }}
              className="flex-1 gap-1.5 h-9 text-xs"
            >
              <Download size={13} />
              {htmlState === 'busy' ? 'Exporting…' : htmlState === 'done' ? '✓ HTML Exported' : htmlState === 'error' ? '✗ Export Failed' : 'Export Report (HTML)'}
            </Button>
            <Button variant="outline" onClick={async () => { await hdtReset(); samplesRef.current = []; setSamples([]); setStatus(null); setExportState('idle'); setHtmlState('idle') }} className="flex-1 gap-1.5 h-9 text-xs">
              <RotateCcw size={13} />
              New Calibration
            </Button>
          </>
        )}
      </div>
    </main>
  )
}

function StatusRow({ label, ok, okText, failText }: { label: string; ok: boolean; okText: string; failText: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <span className={cn('text-[11px] font-bold flex items-center gap-1', ok ? 'text-green-400' : 'text-destructive')}>
        <span className={cn('w-1.5 h-1.5 rounded-full', ok ? 'bg-green-400' : 'bg-destructive')} />
        {ok ? okText : failText}
      </span>
    </div>
  )
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="shrink-0">
      <div className="text-muted-foreground text-[9px] leading-tight">{label}</div>
      <div className={cn('text-sm font-bold leading-tight', highlight ? 'text-amber-400' : 'text-foreground')}>{value}</div>
    </div>
  )
}
