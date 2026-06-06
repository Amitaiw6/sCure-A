import { useState, useRef } from 'react'
import { useSystemConfig } from '@/context/SystemConfigContext'
import { useHardware } from '@/context/HardwareContext'
import { Button } from '@/components/ui/button'
import { Usb, Upload, Building2, ArrowRight, CheckCircle2, Pencil } from 'lucide-react'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import SCureLogo from '@/components/SCureLogo'

type Step = 'welcome' | 'name' | 'org'

export default function SetupPage() {
  const { setOrganization, completeSetup } = useSystemConfig()
  const { state: hw, setSystemName } = useHardware()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [step, setStep] = useState<Step>('welcome')
  const [deviceName, setDeviceName] = useState(hw.systemName)
  const [showKeyboard, setShowKeyboard] = useState(false)
  const [orgId, setOrgId] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [usbVideoIdx, setUsbVideoIdx] = useState(0)
  const usbVideos = ['/videos/usb-insert.mp4', '/videos/usb-org.mp4']

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)

    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      const uuidRegex = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
      const match = text.match(uuidRegex)
      if (match) {
        setOrgId(match[0])
        setFileName(file.name)
      } else {
        setError('No valid organization ID found in CSV file')
        setOrgId(null)
        setFileName(null)
      }
    }
    reader.readAsText(file)
  }

  const handleNameNext = () => {
    if (deviceName.trim()) {
      setSystemName(deviceName.trim())
      setStep('org')
    }
  }

  const handleConnect = () => {
    if (orgId) {
      setOrganization(orgId)
      completeSetup()
      window.location.href = '/'
    }
  }

  const handleSkip = () => {
    completeSetup()
    window.location.href = '/'
  }

  return (
    <div className="w-full h-full bg-background flex items-center justify-center overflow-hidden">

      {/* Step indicators */}
      {step !== 'welcome' && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full transition-colors ${step === 'name' ? 'bg-primary' : 'bg-primary/30'}`} />
          <div className="w-6 h-px bg-border" />
          <div className={`w-2 h-2 rounded-full transition-colors ${step === 'org' ? 'bg-primary' : 'bg-border'}`} />
        </div>
      )}

      {step === 'welcome' ? (
        /* ===== WELCOME SCREEN ===== */
        <div className="flex flex-col items-center justify-center gap-3 relative w-full h-full">

          {/* Background rings */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none -mt-6">
            <div className="w-[180px] h-[180px] rounded-full border border-primary/10 animate-welcome-ring" />
          </div>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none -mt-6">
            <div className="w-[260px] h-[260px] rounded-full border border-primary/5 animate-welcome-ring-delayed" />
          </div>

          {/* Animated logo */}
          <div className="relative animate-welcome-logo">
            <SCureLogo size={100} color="#ffffff" />
          </div>

          {/* Title with shimmer */}
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-widest animate-welcome-title">
              <span className="welcome-shimmer-text">S-Cure</span>
            </h1>
            <p className="text-muted-foreground text-xs mt-1 leading-relaxed animate-welcome-subtitle">
              Congratulations on your new <span className="text-primary font-semibold">S-Cure</span> curing system.<br />
              Let's set it up in just a few steps.
            </p>
          </div>

          {/* CTA Button */}
          <Button
            onClick={() => setStep('name')}
            className="h-9 px-8 text-sm font-semibold gap-2 animate-welcome-btn"
          >
            Get Started
            <ArrowRight size={14} />
          </Button>
        </div>
      ) : step === 'name' ? (
        /* ===== STEP 1: Device Name ===== */
        <div className="flex gap-6 items-center px-6">

          {/* Left – Device illustration */}
          <div className="shrink-0">
            <svg viewBox="0 0 200 180" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-[160px] h-[145px]">
              {/* Device body */}
              <rect x="35" y="20" width="130" height="110" rx="10" fill="#111111" stroke="#333333" strokeWidth="1.5" />
              {/* Vents */}
              <rect x="42" y="40" width="28" height="5" rx="2" fill="#222222" />
              <rect x="42" y="50" width="28" height="5" rx="2" fill="#222222" />
              <rect x="42" y="60" width="28" height="5" rx="2" fill="#222222" />
              <rect x="42" y="70" width="28" height="5" rx="2" fill="#222222" />
              <rect x="42" y="80" width="28" height="5" rx="2" fill="#222222" />
              {/* Screen */}
              <rect x="85" y="32" width="68" height="85" rx="5" fill="#0a0a0a" stroke="#222222" strokeWidth="1" />
              {/* Name on screen */}
              <text x="119" y="72" textAnchor="middle" fill="#ffffff" fontSize="8" fontFamily="monospace" fontWeight="bold">
                {deviceName || '???'}
              </text>
              <text x="119" y="86" textAnchor="middle" fill="#9ca3af" fontSize="5" fontFamily="monospace">NAME ME</text>
              {/* Label */}
              <text x="100" y="155" textAnchor="middle" fill="#555555" fontSize="6" fontFamily="sans-serif">Give your cure box a name</text>
            </svg>
          </div>

          {/* Right – Name input */}
          <div className="flex flex-col gap-3 w-[340px]">
            <div>
              <h1 className="text-base font-bold text-foreground">Name Your Cure Box</h1>
              <p className="text-muted-foreground text-[10px] mt-0.5">
                Choose a name to identify this device
              </p>
            </div>

            <button
              onClick={() => setShowKeyboard(true)}
              className="w-full bg-card border border-border rounded-lg p-2.5 flex items-center gap-3 hover:border-primary/50 transition-colors touch-manipulation active:bg-secondary"
            >
              <div className="flex-1 text-left">
                <span className="text-muted-foreground text-[9px] block">Device Name</span>
                <span className={`text-sm font-semibold block mt-0.5 ${deviceName ? 'text-foreground' : 'text-muted-foreground/40'}`}>
                  {deviceName || 'Tap to enter name...'}
                </span>
              </div>
              <Pencil size={13} className="text-muted-foreground" />
            </button>

            <Button
              onClick={handleNameNext}
              disabled={!deviceName.trim()}
              className="w-full h-8 text-xs font-semibold gap-2"
            >
              Next
              <ArrowRight size={12} />
            </Button>
          </div>
        </div>
      ) : (
        /* ===== STEP 2: Organization ===== */
        <div className="flex gap-6 items-center px-6">

          {/* Left – USB video */}
          <div className="shrink-0 w-[420px] h-[420px] flex items-center justify-center">
            <video
              key={usbVideoIdx}
              src={usbVideos[usbVideoIdx]}
              autoPlay
              muted
              playsInline
              onEnded={() => setUsbVideoIdx(prev => (prev + 1) % usbVideos.length)}
              className="w-full h-full object-cover"
            />
          </div>

          {/* Right – Org content */}
          <div className="flex flex-col gap-4 w-[320px]">
            <div>
              <h1 className="text-lg font-bold text-foreground">Connect Organization</h1>
              <p className="text-muted-foreground text-xs mt-1">
                Link <span className="text-primary font-medium">{deviceName}</span> to your organization
              </p>
            </div>

            <div>
              {!orgId ? (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full bg-card border border-dashed border-border rounded-xl p-4 flex items-center gap-3 hover:border-primary/50 transition-colors touch-manipulation active:bg-secondary"
                >
                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Upload size={16} className="text-primary" />
                  </div>
                  <div className="text-left">
                    <span className="text-foreground text-sm font-medium block">Upload Organization CSV</span>
                    <span className="text-muted-foreground text-xs">
                      Select the CSV file from the USB drive
                    </span>
                  </div>
                </button>
              ) : (
                <div className="w-full bg-card border border-primary/30 rounded-lg p-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-green-500/10 flex items-center justify-center shrink-0">
                      <CheckCircle2 size={16} className="text-green-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <Building2 size={11} className="text-primary shrink-0" />
                        <span className="text-foreground text-xs font-semibold">Organization Found</span>
                      </div>
                      <p className="text-muted-foreground text-[9px] mt-0.5 truncate font-mono">{orgId}</p>
                      <p className="text-muted-foreground text-[8px] mt-0.5">from {fileName}</p>
                    </div>
                    <button
                      onClick={() => { setOrgId(null); setFileName(null); setError(null) }}
                      className="text-[10px] text-muted-foreground hover:text-foreground px-2 py-1 rounded bg-secondary touch-manipulation"
                    >
                      Change
                    </button>
                  </div>
                </div>
              )}

              {error && (
                <p className="text-destructive text-[10px] mt-1.5 text-center">{error}</p>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                className="hidden"
              />
            </div>

            <div className="flex flex-col gap-2 mt-1">
              <Button
                onClick={handleConnect}
                disabled={!orgId}
                className="w-full h-11 text-sm font-semibold gap-2 rounded-xl"
              >
                <Usb size={14} />
                Assign Organization to S-Cure
                <ArrowRight size={14} />
              </Button>

              <button
                onClick={handleSkip}
                className="w-full text-muted-foreground text-xs py-2 hover:text-foreground transition-colors touch-manipulation"
              >
                Continue without organization
              </button>
            </div>
          </div>
        </div>
      )}

      <OnScreenKeyboard
        isOpen={showKeyboard}
        value={deviceName}
        onChange={setDeviceName}
        onClose={() => setShowKeyboard(false)}
      />
    </div>
  )
}
