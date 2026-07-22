import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, AlertOctagon, ChevronRight, ArrowLeft, Mail, Phone, MessageCircle, Wrench, FileText } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAlerts } from '@/context/AlertsContext'
import type { ErrorDef, ActiveAlert } from '@/context/AlertsContext'

export default function AlertsPage() {
  const navigate = useNavigate()
  const { criticalAlerts, warningAlerts, getErrorDef, dismissAlert, support } = useAlerts()
  const [selectedAlert, setSelectedAlert] = useState<{ alert: ActiveAlert; def: ErrorDef } | null>(null)

  const handleSelect = (alert: ActiveAlert) => {
    const def = getErrorDef(alert.code)
    if (def) setSelectedAlert({ alert, def })
  }

  // Detail view
  if (selectedAlert) {
    const { alert, def } = selectedAlert
    return (
      <main className="overflow-y-auto scroll-hidden h-full p-3">
        <div className="bg-card rounded-xl p-4 max-w-2xl mx-auto space-y-4">
          {/* Header */}
          <div className="flex items-center gap-3">
            <button onClick={() => setSelectedAlert(null)} className="text-muted-foreground hover:text-foreground touch-manipulation">
              <ArrowLeft size={20} />
            </button>
            {def.severity === 'critical'
              ? <AlertOctagon size={24} className="text-red-500" />
              : <AlertTriangle size={24} className="text-orange-400" />
            }
            <div>
              <span className="text-red-400 text-sm font-mono">{def.code}:</span>
              <span className="text-foreground text-sm font-bold ml-2">{def.message}</span>
            </div>
          </div>

          {/* Status */}
          <div className="flex items-center gap-2">
            <span className="text-foreground text-xs font-medium">Status:</span>
            <span className={cn(
              'text-xs px-2 py-0.5 rounded font-medium',
              def.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'
            )}>
              {def.severity === 'critical' ? 'Critical' : 'Warning'}
            </span>
          </div>

          {/* Description */}
          <div className="border-t border-border pt-3">
            <div className="flex items-center gap-2 mb-2">
              <FileText size={16} className="text-muted-foreground" />
              <span className="text-foreground text-sm font-bold">Problem Description</span>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed">{def.description}</p>
          </div>

          {/* Troubleshooting */}
          <div className="border-t border-border pt-3">
            <div className="flex items-center gap-2 mb-2">
              <Wrench size={16} className="text-muted-foreground" />
              <span className="text-foreground text-sm font-bold">Troubleshooting Steps</span>
            </div>
            <ol className="space-y-1 ml-4">
              {def.troubleshooting.map((step, i) => (
                <li key={i} className="text-muted-foreground text-xs list-decimal">{step}</li>
              ))}
            </ol>
          </div>

          {/* QR Code */}
          <div className="border-t border-border pt-3 flex items-start gap-4">
            <div className="bg-white p-2 rounded-lg">
              <QRCodeSVG value={def.supportUrl} size={80} />
            </div>
            <div className="flex-1">
              <span className="text-muted-foreground text-[10px] block">Scan for detailed documentation</span>
              <span className="text-primary text-[10px] font-mono break-all">{def.supportUrl}</span>
            </div>
          </div>

          {/* Support */}
          <div className="border-t border-border pt-3">
            <span className="text-foreground text-sm font-bold block mb-2">Need Help?</span>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-muted-foreground text-xs">
                <Mail size={14} className="text-primary" /> {support.email}
              </div>
              <div className="flex items-center gap-2 text-muted-foreground text-xs">
                <Phone size={14} className="text-green-400" /> {support.phone}
              </div>
              <div className="flex items-center gap-2 text-muted-foreground text-xs">
                <MessageCircle size={14} className="text-yellow-400" /> Live Chat
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button variant="outline" className="flex-1 text-xs h-9" onClick={() => setSelectedAlert(null)}>Back</Button>
            <Button className="flex-1 text-xs h-9" onClick={() => { dismissAlert(alert.id); setSelectedAlert(null) }}>
              Dismiss Alert
            </Button>
          </div>
        </div>
      </main>
    )
  }

  // List view
  return (
    <main className="overflow-y-auto scroll-hidden h-full p-3">
      <div className="space-y-3">
        {/* Critical */}
        {criticalAlerts.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <AlertOctagon size={16} className="text-red-500" />
              <span className="text-red-400 text-sm font-bold">Critical Errors</span>
            </div>
            <div className="bg-card rounded-xl overflow-hidden">
              {criticalAlerts.map(alert => {
                const def = getErrorDef(alert.code)
                if (!def) return null
                return (
                  <AlertRow key={alert.id} alert={alert} def={def} supportUrl={def.supportUrl} onSelect={() => handleSelect(alert)} />
                )
              })}
            </div>
          </div>
        )}

        {/* Warnings */}
        {warningAlerts.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={16} className="text-orange-400" />
              <span className="text-orange-400 text-sm font-bold">Non-Critical Errors</span>
            </div>
            <div className="bg-card rounded-xl overflow-hidden">
              {warningAlerts.map(alert => {
                const def = getErrorDef(alert.code)
                if (!def) return null
                return (
                  <AlertRow key={alert.id} alert={alert} def={def} supportUrl={def.supportUrl} onSelect={() => handleSelect(alert)} />
                )
              })}
            </div>
          </div>
        )}

        {/* Empty state */}
        {criticalAlerts.length === 0 && warningAlerts.length === 0 && (
          <div className="text-center py-12">
            <span className="text-green-400 text-lg font-bold block">All Clear</span>
            <span className="text-muted-foreground text-xs">No active alerts</span>
          </div>
        )}
      </div>
    </main>
  )
}

function AlertRow({ alert, def, supportUrl, onSelect }: { alert: ActiveAlert; def: ErrorDef; supportUrl: string; onSelect: () => void }) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0 cursor-pointer hover:bg-accent transition-colors touch-manipulation"
      onClick={onSelect}
    >
      <span className={cn(
        'text-[10px] font-mono font-bold px-1.5 py-0.5 rounded',
        def.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'
      )}>
        {def.code}
      </span>
      <span className="text-foreground text-xs font-medium flex-1">{def.message}</span>
      <div className="bg-white p-1 rounded">
        <QRCodeSVG value={supportUrl} size={28} />
      </div>
      <ChevronRight size={14} className="text-muted-foreground" />
    </div>
  )
}
