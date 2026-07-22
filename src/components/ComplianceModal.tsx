import { ShieldCheck, CheckCircle2, Clock } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  COMPLIANCE_STANDARDS,
  COMPLIANCE_REQUIREMENTS,
  COMPLIANCE_CONTROLS,
} from '@/lib/compliance'

interface ComplianceModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function ComplianceModal({ isOpen, onClose }: ComplianceModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[520px] p-4 max-h-[90vh] overflow-y-auto scroll-hidden">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <ShieldCheck size={16} />
            Cybersecurity Compliance
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Standards */}
          <section className="space-y-1.5">
            <h4 className="text-[11px] uppercase tracking-wide text-muted-foreground">Standards</h4>
            <div className="space-y-1">
              {COMPLIANCE_STANDARDS.map(s => (
                <div key={s.id} className="bg-secondary rounded-md px-2.5 py-1.5">
                  <span className="text-foreground text-xs font-semibold">{s.id}</span>
                  <span className="text-muted-foreground text-[10px] ml-2">{s.name}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Controls implemented in code */}
          <section className="space-y-1.5">
            <h4 className="text-[11px] uppercase tracking-wide text-muted-foreground">Controls in software</h4>
            <div className="space-y-1.5">
              {COMPLIANCE_CONTROLS.map(c => {
                const active = c.status === 'active'
                return (
                  <div key={c.id} className="bg-secondary rounded-md px-2.5 py-2">
                    <div className="flex items-center gap-2">
                      {active ? (
                        <CheckCircle2 size={13} className="text-green-500 shrink-0" />
                      ) : (
                        <Clock size={13} className="text-muted-foreground shrink-0" />
                      )}
                      <span className="text-foreground text-xs font-semibold flex-1">{c.label}</span>
                      <span className={`text-[9px] font-bold rounded-full px-2 py-0.5 ${active ? 'bg-green-500/15 text-green-400' : 'bg-muted text-muted-foreground'}`}>
                        {active ? 'ACTIVE' : 'PLANNED'}
                      </span>
                    </div>
                    <p className="text-muted-foreground text-[10px] mt-1 leading-snug">{c.detail}</p>
                    <p className="text-muted-foreground/70 text-[9px] mt-0.5 font-mono">{c.requirements.join(' · ')}</p>
                  </div>
                )
              })}
            </div>
          </section>

          {/* Requirements (from design review) */}
          <section className="space-y-1.5">
            <h4 className="text-[11px] uppercase tracking-wide text-muted-foreground">Requirements (SRS §22)</h4>
            <div className="space-y-1">
              {COMPLIANCE_REQUIREMENTS.map(r => (
                <div key={r.id} className="flex items-start gap-2 text-[10px]">
                  <span className="text-foreground font-mono font-semibold shrink-0 w-[68px]">{r.id}</span>
                  <span className="text-muted-foreground flex-1 leading-snug">{r.text}</span>
                  {r.effective && (
                    <span className="text-muted-foreground/70 font-mono shrink-0 whitespace-nowrap">
                      {new Date(r.effective).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>

          <p className="text-muted-foreground/70 text-[9px] leading-snug border-t border-border pt-2">
            Full EN 40000 / CRA conformity is a certification process; this panel reflects the
            code-level controls and the requirements they map to.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
