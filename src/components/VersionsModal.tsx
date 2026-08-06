import { useState, useEffect } from 'react'
import { Tag } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const API_BASE = import.meta.env.VITE_HW_API_URL || 'http://localhost:3001/api'

interface VersionEntry {
  version: string
  date: string
  notes: string[]
}

interface LiveVersions {
  appVersion?: string
  gitCommit?: string | null
  gitDate?: string | null
  lastBoot?: string | null
  os?: string | null
  kernel?: string | null
  python?: string | null
}

interface VersionsModalProps {
  isOpen: boolean
  onClose: () => void
}

/** Settings > Versions: live component versions from the machine plus the
 *  full release history (public/config/versions.json, newest first). */
export default function VersionsModal({ isOpen, onClose }: VersionsModalProps) {
  const [live, setLive] = useState<LiveVersions | null>(null)
  const [history, setHistory] = useState<VersionEntry[]>([])

  useEffect(() => {
    if (!isOpen) return
    fetch(`${API_BASE}/system/version`, { signal: AbortSignal.timeout(4000) })
      .then(r => (r.ok ? r.json() : null))
      .then(setLive)
      .catch(() => setLive(null))
    fetch('/config/versions.json', { signal: AbortSignal.timeout(4000) })
      .then(r => (r.ok ? r.json() : null))
      .then(d => setHistory(d?.history ?? []))
      .catch(() => setHistory([]))
  }, [isOpen])

  if (!isOpen) return null

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[440px] p-4 max-h-[85vh] overflow-y-auto scroll-hidden">
        <DialogHeader>
          <DialogTitle className="text-base">Versions</DialogTitle>
        </DialogHeader>

        {/* Live installed versions — read from the machine, not a config file */}
        <div className="bg-secondary rounded-lg p-3 space-y-1">
          <Row label="Software" value={live?.appVersion ?? '—'} strong />
          <Row label="Build (git)" value={live?.gitCommit ? `${live.gitCommit}${live.gitDate ? ` · ${live.gitDate}` : ''}` : '—'} />
          <Row label="OS" value={live?.os ?? '—'} />
          <Row label="Kernel" value={live?.kernel ?? '—'} />
          <Row label="Python" value={live?.python ?? '—'} />
          <Row label="Last Boot" value={live?.lastBoot ?? '—'} />
        </div>

        {/* Release history */}
        <span className="text-muted-foreground text-[11px] font-medium mt-2 block">VERSION HISTORY</span>
        {history.length === 0 ? (
          <p className="text-muted-foreground text-xs">No version history available.</p>
        ) : (
          <div className="space-y-2">
            {history.map(v => (
              <div key={v.version} className="bg-secondary rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Tag size={13} className="text-cyan-400" />
                  <span className="text-foreground text-sm font-bold">v{v.version}</span>
                  <span className="text-muted-foreground text-[10px] ml-auto font-mono">{v.date}</span>
                </div>
                <ul className="space-y-0.5">
                  {v.notes.map((n, i) => (
                    <li key={i} className="text-muted-foreground text-[11px] leading-snug pl-3 relative">
                      <span className="absolute left-0">·</span>{n}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground text-xs shrink-0">{label}</span>
      <span className={`text-xs font-mono text-right ${strong ? 'text-foreground font-bold' : 'text-foreground/80'}`}>{value}</span>
    </div>
  )
}
