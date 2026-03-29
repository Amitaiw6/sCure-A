import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { TouchNumber } from '@/components/ui/touch-number'
import { Progress } from '@/components/ui/progress'
import { useHardware } from '@/context/HardwareContext'
import { Download, Upload, Fan, Zap } from 'lucide-react'
import { useSystemConfig } from '@/context/SystemConfigContext'
import { systemReboot, systemShutdown, exportLogs } from '@/services/hardware-api'
import UpdateModal from '@/components/UpdateModal'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import { Pencil } from 'lucide-react'

export default function SettingsPage() {
  const { state: hw, setChamberTemp, setNitrogenMode, setNitrogenDuration, setNfcEnabled, setSystemName } = useHardware()
  const { config } = useSystemConfig()

  const [ledCoolingAirflow, setLedCoolingAirflow] = useState(0)
  const [chamberIntakeFan, setChamberIntakeFan] = useState(0)
  const [chamberHeatingFan, setChamberHeatingFan] = useState(0)
  const [chamberHeating, setChamberHeatingLocal] = useState(62)
  const [damperOpen, setDamperOpen] = useState(false)
  const [bofaControl, setBofaControl] = useState(true)
  const [fanTestRunning, setFanTestRunning] = useState(false)
  const [fanSpeed, setFanSpeed] = useState<number | null>(null)
  const [ledTestRunning, setLedTestRunning] = useState(false)
  const [ledResults, setLedResults] = useState<string[] | null>(null)
  const [logsStatus, setLogsStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [showUpdate, setShowUpdate] = useState(false)
  const [showNameKeyboard, setShowNameKeyboard] = useState(false)
  const [editingName, setEditingName] = useState(hw.systemName)

  const handleExportLogs = async () => {
    setLogsStatus('loading')
    const res = await exportLogs()
    setLogsStatus(res.ok ? 'success' : 'error')
    setTimeout(() => setLogsStatus('idle'), 3000)
  }

  const handleFanTest = () => {
    setFanTestRunning(true)
    setFanSpeed(null)
    setTimeout(() => { setFanSpeed(2850); setFanTestRunning(false) }, 2000)
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
                  if (confirm('Shutdown device?')) {
                    systemShutdown()
                    sessionStorage.setItem('scure-shutdown', 'true')
                    window.location.reload()
                  }
                }}>SHUTDOWN</Btn>
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

          {/* Row 2: Fan controls */}
          <Card>
            <div className="space-y-2">
              <FanRow label="LED Cooling Airflow" value={ledCoolingAirflow} onChange={setLedCoolingAirflow} />
              <FanRow label="Chamber Intake Fan" value={chamberIntakeFan} onChange={setChamberIntakeFan} />
              <div className="flex items-center gap-2">
                <FanRow label="Chamber Heating Fan" value={chamberHeatingFan} onChange={setChamberHeatingFan} />
                <Button variant="outline" size="sm" className="text-[10px] h-6 px-2 gap-1 shrink-0" onClick={handleFanTest} disabled={fanTestRunning}>
                  <Fan size={10} className={fanTestRunning ? 'animate-spin' : ''} />
                  Test
                </Button>
                {fanSpeed !== null && <span className="text-green-400 text-[10px] shrink-0 whitespace-nowrap">{fanSpeed} RPM <b>OK</b></span>}
              </div>
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
                  style={{ left: `${((chamberHeating - 20) / 60) * 100}%`, transform: 'translate(-50%, -50%)' }} />
              </div>
              <TouchNumber value={chamberHeating} onChange={handleChamberHeatingChange} min={20} max={80} step={1} suffix="°C" className="w-[100px]" />
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

          {/* Row 4: Info grid */}
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
            <div className="space-y-1.5">
              <InfoItem label="Firmware" value={config.firmware} />
              <InfoItem label="Last Boot" value={new Date(config.lastBoot).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })} />
              <InfoItem label="Device" value={config.deviceName} />
            </div>
          </Card>

        </div>
      </div>
      <UpdateModal isOpen={showUpdate} onClose={() => setShowUpdate(false)} />
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

function FanRow({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
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
    </div>
  )
}
