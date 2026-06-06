import { CheckCircle, XCircle, AlertTriangle, Clock, Play, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCureHistory } from '@/context/CureHistoryContext'
import type { CureLog } from '@/context/CureHistoryContext'
import { generateCureReport } from '@/lib/cure-report'

function StatusIcon({ status }: { status: CureLog['status'] }) {
  switch (status) {
    case 'completed': return <CheckCircle size={16} className="text-green-500 shrink-0" />
    case 'aborted': return <AlertTriangle size={16} className="text-yellow-500 shrink-0" />
    case 'error': return <XCircle size={16} className="text-destructive shrink-0" />
    case 'running': return <Play size={16} className="text-primary shrink-0 animate-pulse" />
  }
}

function statusLabel(status: CureLog['status']) {
  switch (status) {
    case 'completed': return 'Completed'
    case 'aborted': return 'Aborted'
    case 'error': return 'Error'
    case 'running': return 'Running'
  }
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return '--:--'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export default function CureHistoryPage() {
  const { logs } = useCureHistory()

  return (
    <main className="overflow-y-auto scroll-hidden h-full p-3">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={16} className="text-muted-foreground" />
        <h2 className="text-foreground text-sm font-bold">Cure History</h2>
        <span className="text-muted-foreground text-xs">({logs.length})</span>
      </div>

      {logs.length === 0 ? (
        <div className="text-center py-12">
          <span className="text-muted-foreground text-sm">No cure sessions yet</span>
        </div>
      ) : (
        <div className="space-y-1.5">
          {logs.map(log => (
            <div key={log.id} className="bg-card rounded-xl px-4 py-3 flex items-center gap-3">
              <StatusIcon status={log.status} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-foreground text-sm font-medium truncate">{log.materialName}</span>
                  <span className={cn(
                    'text-[9px] px-1.5 py-0.5 rounded font-medium',
                    log.status === 'completed' ? 'bg-green-500/15 text-green-400' :
                    log.status === 'aborted' ? 'bg-yellow-500/15 text-yellow-400' :
                    log.status === 'error' ? 'bg-destructive/15 text-destructive' :
                    'bg-primary/15 text-primary'
                  )}>
                    {statusLabel(log.status)}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-muted-foreground text-[10px]">{formatDate(log.startedAt)}</span>
                  {log.endedAt && (
                    <span className="text-muted-foreground text-[10px]">to {new Date(log.endedAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
                  )}
                </div>
              </div>

              <div className="text-right shrink-0">
                <span className="text-cyan-400 text-xs font-medium block">{formatDuration(log.duration)}</span>
                <span className="text-muted-foreground text-[9px]">
                  {log.status === 'completed' ? (
                    <>{log.steps}/{log.steps} steps</>
                  ) : (
                    <span className={log.stepsCompleted < log.steps ? 'text-orange-400' : ''}>
                      {log.stepsCompleted}/{log.steps} steps
                    </span>
                  )}
                </span>
              </div>

              {log.telemetry && log.telemetry.length > 0 && (
                <button
                  onClick={(e) => { e.stopPropagation(); generateCureReport(log) }}
                  className="shrink-0 p-1.5 rounded-lg hover:bg-accent transition-colors touch-manipulation"
                >
                  <Download size={14} className="text-primary" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  )
}