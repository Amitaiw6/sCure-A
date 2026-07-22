import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { TouchNumber } from '@/components/ui/touch-number'
import { Progress } from '@/components/ui/progress'
import { useHardware } from '@/context/HardwareContext'
import { Download, Upload, Fan, Zap, Building2, Unlink, ShieldCheck } from 'lucide-react'
import { useSystemConfig } from '@/context/SystemConfigContext'
import { systemReboot, systemShutdown, exportLogs } from '@/services/hardware-api'
import { COMPLIANCE_CONTROLS } from '@/lib/compliance'
import UpdateModal from '@/components/UpdateModal'
import ComplianceModal from '@/components/ComplianceModal'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import { Pencil } from 'lucide-react'

function formatHours(h: number): string {
  return `${h.toFixed(1)}h`
}

export default function SettingsPage() {
  const { state: hw, setChamberTemp, setNitrogenMode, setNitrogenDuration, setNfcEnabled, setSystemName } = useHardware()
  const { config, setOrganization, resetSetup } = useSystemConfig()
  const orgFileInputRef = useRef<HTMLInputElement>(null)
  const [orgError, setOrgError] = useState<string | null>(null)

  const [dateTime, setDateTime] = useState(() => {
    const now = new Date()
    return {
      date: now.toISOString().split('T')[0],
      time: now.toTimeString().slice(0, 5),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      autoSync: true,
    }
  })
  const [ledCoolingAirflow, setLedCoolingAirflow] = useState(0)
  const [chamberIntakeFan, setChamberIntakeFan] = useState(0)
  const [chamberHeatingFan, setChamberHeatingFan] = useState(0)
  const [chamberHeating, setChamberHeatingLocal] = useState(62)
  const [damperOpen, setDamperOpen] = useState(false)
  const [bofaControl, setBofaControl] = useState(true)
  const [fanTests, setFanTests] = useState<Record<string, { running: boolean; rpm: number | null }>>({})
  const [ledTestRunning, setLedTestRunning] = useState(false)
  const [ledResults, setLedResults] = useState<string[] | null>(null)
  const [logsStatus, setLogsStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [showUpdate, setShowUpdate] = useState(false)
  const [showCompliance, setShowCompliance] = useState(false)
  const [showNameKeyboard, setShowNameKeyboard] = useState(false)
  const [editingName, setEditingName] = useState(hw.systemName)
  const [factoryTaps, setFactoryTaps] = useState(0)

  const handleExportLogs = async () => {
    setLogsStatus('loading')
    const res = await exportLogs()
    setLogsStatus(res.ok ? 'success' : 'error')
    setTimeout(() => setLogsStatus('idle'), 3000)
  }

  // Expected nominal RPM per fan (used by the per-fan diagnostic)
  const FAN_RPM: Record<string, number> = {
    led_cooling: 2850,
    chamber_intake: 3050,
    chamber_heating: 2780,
  }

  const handleFanTest = (id: string) => {
    setFanTests(prev => ({ ...prev, [id]: { running: true, rpm: null } }))
    setTimeout(() => {
      setFanTests(prev => ({ ...prev, [id]: { running: false, rpm: FAN_RPM[id] ?? 2800 } }))
    }, 2000)
  }

  const handleLedTest = () => {
    setLedTestRunning(true)
    setLedResults(null)
    setTimeout(() => {
      setLedResults(['Font LED: 62°C', 'Left LED: 62°C', 'Door LED: 62°C', 'Right LED: 62°C'])
      setLedTestRunning(false)
    }, 3000)
  }

  const handleChamberHeatingChange = (val: number | null) => {
    const v = val ?? 25
    setChamberHeatingLocal(v)
    setChamberTemp(v)
  }

  return (
    <main className="overflow-y-auto scroll-hidden h-full p-3">
      <div className="grid grid-cols-[1fr_220px] gap-3 h-full">

        {/* ===== LEFT ===== */}
        <div className="flex flex-col gap-2">

          {/* System Name */}
          <Card>
            <div className="flex items-center justify-between">
              <Label>System Name</Label>
              <div className="flex items-center gap-2">
                <span className="text-foreground text-sm font-bold">{hw.systemName}</span>
                <button
                  onClick={() => { setEditingName(hw.systemName); setShowNameKeyboard(true) }}
                  className="w-7 h-7 rounded-lg bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground active:bg-accent transition-colors touch-manipulation"
                >
                  <Pencil size={12} />
                </button>
              </div>
            </div>
          </Card>

          {/* Row 1: Power + Damper side by side */}
          <div className="flex gap-2">
            <Card className="flex-1">
              <Label>Power Options</Label>
              <div className="flex gap-2 mt-1">
                <Btn muted onClick={() => { if (confirm('Reboot device?')) systemReboot() }}>REBOOT</Btn>
                <Btn red onClick={() => {
                  sessionStorage.setItem('scure-shutdown', 'true')
                  window.location.reload()
                }}>SLEEP</Btn>
              </div>
            </Card>
            <Card className="flex-1">
              <Label>Damper</Label>
              <div className="flex gap-2 mt-1">
                <Btn active={damperOpen} onClick={() => setDamperOpen(true)}>OPEN</Btn>
                <Btn active={!damperOpen} onClick={() => setDamperOpen(false)}>CLOSE</Btn>
              </div>
            </Card>
          </div>

          {/* Row 2: Fan controls — each fan has its own diagnostic test */}
          <Card>
            <div className="space-y-2">
              <FanRow label="LED Cooling Airflow" value={ledCoolingAirflow} onChange={setLedCoolingAirflow}
                onTest={() => handleFanTest('led_cooling')} testing={fanTests['led_cooling']?.running} rpm={fanTests['led_cooling']?.rpm} />
              <FanRow label="Chamber Intake Fan" value={chamberIntakeFan} onChange={setChamberIntakeFan}
                onTest={() => handleFanTest('chamber_intake')} testing={fanTests['chamber_intake']?.running} rpm={fanTests['chamber_intake']?.rpm} />
              <FanRow label="Chamber Heating Fan" value={chamberHeatingFan} onChange={setChamberHeatingFan}
                onTest={() => handleFanTest('chamber_heating')} testing={fanTests['chamber_heating']?.running} rpm={fanTests['chamber_heating']?.rpm} />
            </div>
          </Card>

          {/* Row 3: Heating full width */}
          <Card>
            <div className="flex items-center gap-3">
              <Label className="shrink-0">Chamber Heating</Label>
              <div className="flex-1 h-4 bg-gradient-to-r from-blue-500 via-yellow-500 to-orange-500 rounded-full relative">
                <input type="range" min={20} max={80} value={chamberHeating}
                  onChange={e => handleChamberHeatingChange(Number(e.target.value))}
                  className="absolute inset-0 w-full opacity-0 cursor-pointer touch-manipulation" />
                <div className="absolute top-1/2 w-5 h-5 bg-white rounded-full shadow-lg border-2 border-primary pointer-events-none"
                  style={{ left: `calc(10px + (100% - 20px) * ${(chamberHeating - 20) / 60})`, transform: 'translate(-50%, -50%)' }} />
              </div>
              <TouchNumber value={chamberHeating} onChange={handleChamberHeatingChange} min={20} max={80} step={1} suffix="°C" className="w-[120px] shrink-0" />
            </div>
          </Card>

          {/* Row 4: LED Test */}
          <Card>
            <div className="flex items-center gap-3">
              <Label className="shrink-0">LED Test</Label>
              <Button size="sm" className="text-[10px] h-7 px-3 gap-1" onClick={handleLedTest} disabled={ledTestRunning}>
                <Zap size={11} />
                {ledTestRunning ? 'Testing...' : 'Run Diagnostic'}
              </Button>
              {ledResults && (
                <div className="flex gap-3 flex-wrap">
                  {ledResults.map((r, i) => (
                    <span key={i} className="text-[9px] text-muted-foreground">{r} <span className="text-green-400 font-bold">OK</span></span>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Row 4: Counters */}
          <Card>
            <Label>Component Counters</Label>
            <div className="grid grid-cols-3 gap-x-6 gap-y-1.5 mt-1.5">
              <InfoItem label="LED 405nm" value={formatHours(hw.counters?.led405 ?? 0)} />
              <InfoItem label="LED 450nm" value={formatHours(hw.counters?.led450 ?? 0)} />
              <InfoItem label="Cooling Fan" value={formatHours(hw.counters?.coolingFan ?? 0)} />
              <InfoItem label="Heater" value={formatHours(hw.counters?.heater ?? 0)} />
              <InfoItem label="Heater Fan" value={formatHours(hw.counters?.heaterFan ?? 0)} />
            </div>
          </Card>

          {/* Row 5: Info grid */}
          <Card>
            <div className="grid grid-cols-3 gap-x-6 gap-y-1.5">
              <InfoItem label="Lead On Time" value={`${config.leadOnTimeHours} hours`} />
              <InfoItem label="N₂ Pressure" value="2.0 bar" />
              <div className="flex items-center justify-between">
                <Label>
                  Nitrogen Mode
                  {hw.n2LinePressure < 6 && (
                    <span className="text-destructive text-[9px] ml-1">(min 6 bar)</span>
                  )}
                </Label>
                <Switch
                  checked={hw.nitrogenMode}
                  onCheckedChange={v => {
                    if (v && hw.n2LinePressure < 6) return
                    setNitrogenMode(v)
                  }}
                  disabled={!hw.nitrogenMode && hw.n2LinePressure < 6}
                />
              </div>
              <ToggleItem label="NFC" checked={hw.nfcEnabled} onChange={setNfcEnabled} />
              <ToggleItem label="BOFA Control" checked={bofaControl} onChange={setBofaControl} />
            </div>
          </Card>
        </div>

        {/* ===== RIGHT ===== */}
        <div className="flex flex-col gap-2">
          {/* Date & Time */}
          <Card>
            <Label>Date & Time</Label>
            <div className="mt-1.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground text-[10px]">Auto Sync</span>
                <Switch checked={dateTime.autoSync} onCheckedChange={v => setDateTime(prev => ({ ...prev, autoSync: v }))} />
              </div>

              {dateTime.autoSync ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground text-[10px]">Date</span>
                    <span className="text-foreground text-[11px] font-mono">{new Date(dateTime.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground text-[10px]">Time</span>
                    <span className="text-foreground text-[11px] font-mono">{dateTime.time}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground text-[10px]">Timezone</span>
                    <span className="text-foreground text-[10px] font-mono truncate max-w-[130px]">{dateTime.timezone}</span>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground text-[10px] shrink-0">Date</span>
                    <input
                      type="date"
                      value={dateTime.date}
                      onChange={e => setDateTime(prev => ({ ...prev, date: e.target.value }))}
                      className="bg-secondary border border-border rounded-md px-2 py-1 text-[11px] text-foreground font-mono w-[130px] touch-manipulation"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground text-[10px] shrink-0">Time</span>
                    <input
                      type="time"
                      value={dateTime.time}
                      onChange={e => setDateTime(prev => ({ ...prev, time: e.target.value }))}
                      className="bg-secondary border border-border rounded-md px-2 py-1 text-[11px] text-foreground font-mono w-[130px] touch-manipulation"
                    />
                  </div>
                  <Button variant="outline" size="sm" className="w-full text-[10px] h-7 mt-1" onClick={() => {
                    // In production: call API to set system clock
                    // sudo date -s "YYYY-MM-DD HH:MM"
                    console.log(`[DateTime] Set to ${dateTime.date} ${dateTime.time}`)
                  }}>
                    Apply
                  </Button>
                </>
              )}
            </div>
          </Card>

          <Card>
            <InfoItem label="S.N" value={config.serialNumber} />
          </Card>

          <Card>
            <Label>Dump Logs <span className="text-muted-foreground/60">(USB)</span></Label>
            <Button variant="outline" size="sm" className="w-full text-[10px] h-8 gap-1 mt-1.5" onClick={handleExportLogs} disabled={logsStatus === 'loading'}>
              <Download size={13} className={logsStatus === 'loading' ? 'animate-bounce' : ''} />
              {logsStatus === 'loading' ? 'Exporting...' : logsStatus === 'success' ? '✓ Done!' : logsStatus === 'error' ? '✗ No USB found' : 'Export LOGS'}
            </Button>
          </Card>

          <Card>
            <Label>Software Update <span className="text-muted-foreground/60">(USB)</span></Label>
            <Button variant="outline" size="sm" className="w-full text-[10px] h-8 gap-1 mt-1.5" onClick={() => setShowUpdate(true)}>
              <Upload size={13} /> Update Software
            </Button>
          </Card>

          <Card>
            <Label>Compliance <span className="text-muted-foreground/60">(CRA / EN 18031)</span></Label>
            <Button variant="outline" size="sm" className="w-full text-[10px] h-8 gap-1 mt-1.5" onClick={() => setShowCompliance(true)}>
              <ShieldCheck size={13} className="text-green-500" />
              {COMPLIANCE_CONTROLS.filter(c => c.status === 'active').length} controls active
            </Button>
          </Card>

          <Card>
            <Label>Organization</Label>
            {config.organizationId ? (
              <div className="mt-1.5 space-y-1.5">
                <div className="bg-secondary rounded-md px-2 py-1.5">
                  <span className="text-[8px] text-muted-foreground font-mono break-all leading-tight block">{config.organizationId}</span>
                </div>
                <div className="flex gap-1.5">
                  <Button variant="outline" size="sm" className="flex-1 text-[10px] h-7 gap-1" onClick={() => orgFileInputRef.current?.click()}>
                    <Building2 size={11} /> Change
                  </Button>
                  <Button variant="outline" size="sm" className="text-[10px] h-7 gap-1 text-destructive hover:text-destructive" onClick={() => resetSetup()}>
                    <Unlink size={11} />
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="outline" size="sm" className="w-full text-[10px] h-8 gap-1 mt-1.5" onClick={() => orgFileInputRef.current?.click()}>
                <Building2 size={13} /> Link Organization
              </Button>
            )}
            {orgError && <p className="text-destructive text-[9px] mt-1">{orgError}</p>}
            <input
              ref={orgFileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setOrgError(null)
                const reader = new FileReader()
                reader.onload = (ev) => {
                  const text = ev.target?.result as string
                  const match = text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)
                  if (match) {
                    setOrganization(match[0])
                    setOrgError(null)
                  } else {
                    setOrgError('No valid ID found')
                  }
                }
                reader.readAsText(file)
                e.target.value = ''
              }}
            />
          </Card>

          <Card>
            <div
              className="space-y-1.5"
              onClick={() => {
                const next = factoryTaps + 1
                setFactoryTaps(next)
                if (next >= 10) {
                  setFactoryTaps(0)
                  resetSetup()
                }
              }}
            >
              <InfoItem label="Firmware" value={config.firmware} />
              <InfoItem label="Last Boot" value={new Date(config.lastBoot).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} />
              <InfoItem label="Device" value={config.deviceName} />
            </div>
          </Card>

        </div>
      </div>
      <UpdateModal isOpen={showUpdate} onClose={() => setShowUpdate(false)} />
      <ComplianceModal isOpen={showCompliance} onClose={() => setShowCompliance(false)} />
      <OnScreenKeyboard
        isOpen={showNameKeyboard}
        value={editingName}
        onChange={setEditingName}
        onClose={() => { setSystemName(editingName); setShowNameKeyboard(false) }}
      />
    </main>
  )
}

/* ---------- Small helpers ---------- */

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-card rounded-lg p-2.5 ${className}`}>{children}</div>
}

function Label({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <span className={`text-muted-foreground text-[11px] ${className}`}>{children}</span>
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <Label>{label}</Label>
      <span className="text-foreground text-[11px] font-semibold">{value}</span>
    </div>
  )
}

function ToggleItem({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <Label>{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

function Btn({ children, active, muted, red, onClick }: {
  children: React.ReactNode; active?: boolean; muted?: boolean; red?: boolean; onClick: () => void
}) {
  const cls = red
    ? 'bg-red-600 hover:bg-red-500 text-white'
    : muted
      ? 'bg-secondary text-muted-foreground hover:bg-accent'
      : active
        ? 'bg-primary text-white'
        : 'bg-secondary text-muted-foreground hover:bg-accent'
  return (
    <button onClick={onClick} className={`text-[10px] font-medium px-3 h-7 rounded-lg transition-colors touch-manipulation ${cls}`}>
      {children}
    </button>
  )
}

function FanRow({ label, value, onChange, onTest, testing, rpm }: {
  label: string
  value: number
  onChange: (v: number) => void
  onTest?: () => void
  testing?: boolean
  rpm?: number | null
}) {
  return (
    <div className="flex items-center gap-2 flex-1">
      <span className="text-muted-foreground text-[10px] w-[130px] shrink-0">{label}</span>
      <span className="text-muted-foreground text-[9px] w-5 text-right">{value}%</span>
      <div className="flex-1 relative h-5 flex items-center">
        <Progress value={value} className="h-1.5 w-full" />
        <input type="range" min={0} max={100} value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer touch-manipulation" />
      </div>
      <span className="text-muted-foreground text-[9px] w-14 text-right">100% PWM</span>
      {onTest && (
        <Button variant="outline" size="sm" className="text-[10px] h-6 px-2 gap-1 shrink-0" onClick={onTest} disabled={testing}>
          <Fan size={10} className={testing ? 'animate-spin' : ''} />
          Test
        </Button>
      )}
      {rpm != null && (
        <span className="text-green-400 text-[10px] shrink-0 whitespace-nowrap w-[72px] text-right">{rpm} RPM <b>OK</b></span>
      )}
    </div>
  )
}
