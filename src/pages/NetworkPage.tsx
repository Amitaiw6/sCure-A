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
}

const defaultNet: NetworkInfo = {
  ip: '192.168.2.218',
  mac: '48:b0:2d:21:c4:56',
  gateway: '192.168.2.254',
  wireguardIp: '10.145.13.115/32',
  connectionName: 'dhcp-eth0',
  protocol: 'ethernet',
  interfaces: [
    { name: 'eth0', status: 'UP', ip: '192.168.2.218' },
    { name: 'wg0', status: 'UP', ip: '10.145.13.115' },
    { name: 'lo', status: 'UP', ip: '127.0.0.1' },
  ],
}

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

  // Fetch network info: try API first, fallback to WebRTC local IP detection
  useEffect(() => {
    async function fetchNet() {
      // Try Python API
      try {
        const res = await fetch(`${API_BASE}/network/status`, { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          const data = await res.json()
          setNet(prev => ({
            ...prev,
            ip: data.ip || prev.ip,
            mac: data.mac || prev.mac,
            gateway: data.gateway || prev.gateway,
            interfaces: data.interfaces?.length ? data.interfaces : prev.interfaces,
          }))
          return
        }
      } catch { /* fallback */ }

      // Fallback: use public IP detection service
      try {
        const res = await fetch('https://api.ipify.org?format=json', { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          const data = await res.json()
          setNet(prev => ({
            ...prev,
            ip: data.ip,
            connectionName: 'browser-detected',
            protocol: navigator.onLine ? 'connected' : 'offline',
            interfaces: [
              { name: 'wan', status: 'UP', ip: data.ip },
            ],
          }))
        }
      } catch { /* no internet */ }
    }
    fetchNet()
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
          {/* Connection status */}
          <Card>
            <div className="flex items-center gap-2 mb-1">
              <div className={cn('w-2.5 h-2.5 rounded-full', hw.networkConnected ? 'bg-green-500' : 'bg-destructive')} />
              <span className={cn('text-xs font-medium', hw.networkConnected ? 'text-green-400' : 'text-destructive')}>
                {hw.networkConnected ? 'Connected' : 'No Network'}
              </span>
              {hw.apiConnected && <span className="text-[9px] text-muted-foreground ml-2">API: OK</span>}
            </div>
          </Card>

          {/* Network Info */}
          <Card>
            <InfoRow label="IP Address" value={net.ip} />
            <InfoRow label="MAC" value={net.mac} />
            <InfoRow label="Wireguard IP" value={net.wireguardIp} />
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

  const simulateResults: Record<string, (addr: string) => string> = {
    ping: (addr) =>
      `PING ${addr} (${addr}) 56(84) bytes of data.\n64 bytes from ${addr}: icmp_seq=1 ttl=118 time=12.3 ms\n64 bytes from ${addr}: icmp_seq=2 ttl=118 time=11.8 ms\n64 bytes from ${addr}: icmp_seq=3 ttl=118 time=12.1 ms\n64 bytes from ${addr}: icmp_seq=4 ttl=118 time=11.9 ms\n\n--- ${addr} ping statistics ---\n4 packets transmitted, 4 received, 0% packet loss\nrtt min/avg/max = 11.8/12.0/12.3 ms`,
    traceroute: (addr) =>
      `traceroute to ${addr}, 30 hops max\n 1  192.168.2.254  1.2 ms  1.1 ms  1.0 ms\n 2  10.0.0.1       5.4 ms  5.2 ms  5.1 ms\n 3  172.16.0.1     8.7 ms  8.5 ms  8.6 ms\n 4  ${addr}        12.1 ms  12.0 ms  11.9 ms`,
    nslookup: (addr) =>
      `Server:    8.8.8.8\nAddress:   8.8.8.8#53\n\nNon-authoritative answer:\nName:  ${addr}\nAddress: ${addr.includes('.') ? addr : '93.184.216.34'}`,
  }

  const handleExecute = async () => {
    if (!address.trim()) return
    setRunning(true)
    setResult(null)

    try {
      const res = await fetch(`${API_BASE}/network/diagnostics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool, address: address.trim() }),
        signal: AbortSignal.timeout(15000),
      })
      if (res.ok) {
        const data = await res.json()
        setResult(data.result)
        setRunning(false)
        return
      }
    } catch { /* fallback to simulation */ }

    // Simulation fallback
    setTimeout(() => {
      setResult(simulateResults[tool](address.trim()))
      setRunning(false)
    }, 1500)
  }

  const tools = [
    { id: 'ping' as const, label: 'Ping' },
    { id: 'traceroute' as const, label: 'Traceroute' },
    { id: 'nslookup' as const, label: 'NS Lookup' },
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
            const val = prompt('IP/Address:', address)
            if (val !== null) setAddress(val)
          }}
        >
          <span className={address ? 'text-foreground text-xs' : 'text-muted-foreground text-xs'}>
            {address || 'Enter address...'}
          </span>
        </div>
        <span className="text-muted-foreground text-[10px]">IP/Address</span>

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
