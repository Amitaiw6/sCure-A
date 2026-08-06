import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useHardware } from '@/context/HardwareContext'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'

type Tab = 'status' | 'diagnostics'

interface NetworkInfo {
  ip: string
  mac: string
  gateway: string
  wireguardIp: string
  connectionName: string
  protocol: string
  interfaces: { name: string; status: string; ip: string }[]
  lanConnected: boolean | null       // eth0 has an IP (null = not known yet)
  internet: boolean | null           // machine's live TCP-443 reachability watch
  statusKnown: boolean               // /api/network/status answered at least once
}

const defaultNet: NetworkInfo = {
  ip: '—',
  mac: '—',
  gateway: '—',
  wireguardIp: '—',
  connectionName: '—',
  protocol: 'ethernet',
  interfaces: [],
  lanConnected: null,
  internet: null,
  statusKnown: false,
}

const NET_POLL_MS = 3000

export default function NetworkPage() {
  const [tab, setTab] = useState<Tab>('status')
  const [connectionMode, setConnectionMode] = useState<'dhcp' | 'static'>('dhcp')
  const [showStaticIp, setShowStaticIp] = useState(false)
  const [staticIp, setStaticIp] = useState('')
  const [staticGateway, setStaticGateway] = useState('')
  const [staticSubnet, setStaticSubnet] = useState('255.255.255.0')
  const [staticDns, setStaticDns] = useState('8.8.8.8')
  const { state: hw } = useHardware()
  const [net, setNet] = useState<NetworkInfo>(defaultNet)

  // Live network status: poll the machine every NET_POLL_MS so pulling the
  // cable / losing the uplink shows here within seconds. `connected` is the
  // LAN/IP level; `internet` is the machine's real background reachability
  // watch (TCP 443 every 5s) — never navigator.onLine, which is meaningless
  // on the kiosk (the UI talks to localhost).
  useEffect(() => {
    let cancelled = false
    async function fetchNet() {
      try {
        const res = await fetch(`${API_BASE}/network/status`, { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          const data = await res.json()
          if (cancelled) return
          setNet(prev => ({
            ...prev,
            ip: data.ip && data.ip !== '0.0.0.0' ? data.ip : '—',
            mac: data.mac || prev.mac,
            gateway: data.gateway || '—',
            interfaces: data.interfaces?.length ? data.interfaces : prev.interfaces,
            lanConnected: data.connected ?? null,
            internet: data.internet ?? null,
            statusKnown: true,
          }))
          return
        }
      } catch { /* API unreachable */ }
      if (!cancelled) setNet(prev => ({ ...prev, lanConnected: null, internet: null, statusKnown: false }))
    }
    fetchNet()
    const interval = setInterval(fetchNet, NET_POLL_MS)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return (
    <main className="overflow-y-auto scroll-hidden h-full p-3">
      {/* Tabs */}
      <div className="flex gap-1 mb-3">
        <TabBtn active={tab === 'status'} onClick={() => setTab('status')}>STATUS</TabBtn>
        <TabBtn active={tab === 'diagnostics'} onClick={() => setTab('diagnostics')}>DIAGNOSTICS</TabBtn>
      </div>

      {tab === 'status' && (
        <div className="space-y-2">
          {/* Connection status — live from the machine, refreshed every 3s */}
          <Card>
            <div className="flex items-center gap-2 mb-1">
              <div className={cn('w-2.5 h-2.5 rounded-full',
                !net.statusKnown ? 'bg-orange-400' : net.lanConnected ? 'bg-green-500' : 'bg-destructive')} />
              <span className={cn('text-xs font-medium',
                !net.statusKnown ? 'text-orange-400' : net.lanConnected ? 'text-green-400' : 'text-destructive')}>
                {!net.statusKnown ? 'Status unavailable' : net.lanConnected ? 'Connected' : 'No Network'}
              </span>
              {hw.apiConnected && <span className="text-[9px] text-muted-foreground ml-2">API: OK</span>}
            </div>
          </Card>

          {/* Network Info */}
          <Card>
            <InfoRow label="IP Address" value={net.ip} />
            <InfoRow label="MAC" value={net.mac} />
            <InfoRow label="WireGuard IP" value={net.wireguardIp} />
          </Card>

          {/* Connection Details */}
          <Card>
            <InfoRow label="Name" value={net.connectionName} />
            <InfoRow label="Protocol" value={net.protocol} />
            <InfoRow label="IP" value={`${net.ip}/24`} />
            <InfoRow label="Gateway" value={net.gateway} />
          </Card>

          {/* Change Connection */}
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-foreground text-xs font-medium">Change Connection</span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className={cn('text-[11px] h-8 px-4', connectionMode === 'static' ? 'bg-primary text-white' : 'bg-secondary text-muted-foreground')}
                  onClick={() => { setStaticIp(net.ip); setStaticGateway(net.gateway); setShowStaticIp(true) }}
                >
                  STATIC IP
                </Button>
                <Button
                  size="sm"
                  className={cn('text-[11px] h-8 px-4', connectionMode === 'dhcp' ? 'bg-primary text-white' : 'bg-secondary text-muted-foreground')}
                  onClick={() => {
                    setConnectionMode('dhcp')
                    // Apply on the device too, not only in local UI state
                    fetch(`${API_BASE}/network/static`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ dhcp: true }),
                    }).catch(() => {})
                  }}
                >
                  DHCP
                </Button>
              </div>
            </div>
          </Card>

          {/* Static IP Dialog */}
          {showStaticIp && (
            <StaticIpDialog
              ip={staticIp} onIpChange={setStaticIp}
              gateway={staticGateway} onGatewayChange={setStaticGateway}
              subnet={staticSubnet} onSubnetChange={setStaticSubnet}
              dns={staticDns} onDnsChange={setStaticDns}
              onSave={() => {
                setConnectionMode('static')
                setNet(prev => ({ ...prev, ip: staticIp, gateway: staticGateway, connectionName: 'static-eth0' }))
                setShowStaticIp(false)
                // In production: call API to apply network config
                fetch(`${API_BASE}/network/static`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ ip: staticIp, gateway: staticGateway, subnet: staticSubnet, dns: staticDns }),
                }).catch(() => {})
              }}
              onCancel={() => setShowStaticIp(false)}
            />
          )}
        </div>
      )}

      {tab === 'diagnostics' && (
        <div className="space-y-2">
          <DiagnosticsTab />
        </div>
      )}
    </main>
  )
}

function DiagnosticsTab() {
  const [tool, setTool] = useState<'ping' | 'traceroute' | 'nslookup'>('ping')
  const [address, setAddress] = useState('8.8.8.8')
  const [result, setResult] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  // Diagnostics run ONLY on the machine — a failed call shows a real error,
  // never a fabricated "success" printout.
  const handleExecute = async () => {
    if (!address.trim()) return
    setRunning(true)
    setResult(null)

    try {
      const res = await fetch(`${API_BASE}/network/diagnostics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, address: address.trim() }),
        signal: AbortSignal.timeout(60000),
      })
      if (res.ok) {
        const data = await res.json()
        setResult(data.result || '(no output — host unreachable or command produced nothing)')
        setRunning(false)
        return
      }
      setResult(`Diagnostics failed: API returned ${res.status}`)
    } catch {
      setResult('Diagnostics unavailable: the hardware API is not reachable.')
    }
    setRunning(false)
  }

  const tools = [
    { id: 'ping' as const, label: 'Ping' },
    { id: 'traceroute' as const, label: 'Traceroute' },
    { id: 'nslookup' as const, label: 'DNS Lookup' },
  ]

  return (
    <div className="grid grid-cols-[280px_1fr] gap-2 h-[calc(100vh-140px)]">
      {/* Left: Parameters */}
      <Card>
        <span className="text-foreground text-xs font-bold block mb-3">Parameters</span>

        {/* Tool selection */}
        <div className="flex items-start gap-3 mb-3">
          <span className="text-muted-foreground text-xs mt-1 w-10">Tool</span>
          <div className="space-y-2">
            {tools.map(t => (
              <label key={t.id} className="flex items-center gap-2 cursor-pointer touch-manipulation">
                <div className={cn(
                  'w-5 h-5 rounded border-2 flex items-center justify-center transition-colors',
                  tool === t.id ? 'border-primary bg-primary' : 'border-border'
                )}
                  onClick={() => setTool(t.id)}
                >
                  {tool === t.id && <div className="w-2 h-2 bg-white rounded-sm" />}
                </div>
                <span className="text-foreground text-xs" onClick={() => setTool(t.id)}>{t.label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* IP/Address input */}
        <div
          className="bg-secondary rounded-lg h-10 flex items-center px-3 mb-1 cursor-pointer"
          onClick={() => {
            const val = prompt('IP address or hostname:', address)
            if (val !== null) setAddress(val)
          }}
        >
          <span className={address ? 'text-foreground text-xs' : 'text-muted-foreground text-xs'}>
            {address || 'Enter address...'}
          </span>
        </div>
        <span className="text-muted-foreground text-[10px]">IP address or hostname</span>

        {/* Execute */}
        <Button
          size="sm"
          className="w-full mt-3 text-xs h-9"
          onClick={handleExecute}
          disabled={running || !address.trim()}
        >
          {running ? 'Running...' : 'EXECUTE'}
        </Button>
      </Card>

      {/* Right: Result */}
      <Card>
        <span className="text-foreground text-xs font-bold block mb-2">Result</span>
        <div className="bg-secondary rounded-lg p-3 h-[calc(100%-28px)] overflow-y-auto scroll-hidden">
          {running ? (
            <span className="text-muted-foreground text-xs animate-pulse">Executing {tool} {address}...</span>
          ) : result ? (
            <pre className="text-green-400 text-[11px] font-mono whitespace-pre-wrap">{result}</pre>
          ) : (
            <span className="text-muted-foreground text-xs">Select a tool and press EXECUTE</span>
          )}
        </div>
      </Card>
    </div>
  )
}

function TabBtn({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-4 py-2 rounded-lg text-xs font-medium transition-colors touch-manipulation',
        active ? 'bg-card border border-border text-foreground' : 'text-muted-foreground hover:text-foreground'
      )}
    >
      {children}
    </button>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="bg-card rounded-lg p-3 space-y-1.5">{children}</div>
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-foreground text-xs font-mono font-medium">{value}</span>
    </div>
  )
}

function StaticIpDialog({ ip, onIpChange, gateway, onGatewayChange, subnet, onSubnetChange, dns, onDnsChange, onSave, onCancel }: {
  ip: string; onIpChange: (v: string) => void
  gateway: string; onGatewayChange: (v: string) => void
  subnet: string; onSubnetChange: (v: string) => void
  dns: string; onDnsChange: (v: string) => void
  onSave: () => void
  onCancel: () => void
}) {
  const isValidIp = (v: string) => /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(v)
  const canSave = isValidIp(ip) && isValidIp(gateway)

  return (
    <Dialog open onOpenChange={onCancel}>
      <DialogContent className="sm:max-w-[380px] p-4" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-base">Static IP Configuration</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-muted-foreground text-[11px] block mb-1">IP Address *</label>
            <Input value={ip} onChange={e => onIpChange(e.target.value)} placeholder="192.168.1.100" className="font-mono text-xs h-9" />
          </div>
          <div>
            <label className="text-muted-foreground text-[11px] block mb-1">Gateway *</label>
            <Input value={gateway} onChange={e => onGatewayChange(e.target.value)} placeholder="192.168.1.1" className="font-mono text-xs h-9" />
          </div>
          <div>
            <label className="text-muted-foreground text-[11px] block mb-1">Subnet Mask</label>
            <Input value={subnet} onChange={e => onSubnetChange(e.target.value)} placeholder="255.255.255.0" className="font-mono text-xs h-9" />
          </div>
          <div>
            <label className="text-muted-foreground text-[11px] block mb-1">DNS Server</label>
            <Input value={dns} onChange={e => onDnsChange(e.target.value)} placeholder="8.8.8.8" className="font-mono text-xs h-9" />
          </div>
        </div>

        <DialogFooter className="flex-row gap-3">
          <Button variant="outline" onClick={onCancel} className="flex-1 text-xs h-9">Cancel</Button>
          <Button onClick={onSave} disabled={!canSave} className="flex-1 text-xs h-9">Apply</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
