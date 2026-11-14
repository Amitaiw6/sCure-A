import { AlertTriangle, Eye, Box } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'

/** Chamber temperature (°C) from which the stop/pause dialogs call the
 *  chamber HOT and show the live reading — below it the caution is generic. */
export const ABORT_HOT_CHAMBER_C = 40

/** The "hot surface" safety pictogram from the machine's CAUTION label
 *  (ISO 7010 W017): yellow triangle, heat waves rising off a surface. */
export function HotSurfaceSign({ size = 36, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 100 100" role="img" aria-label="Caution — hot surface"
      className={`shrink-0 ${className}`}
    >
      <path d="M50 7 L95 88 H5 Z" fill="#F5C400" stroke="#111" strokeWidth="5" strokeLinejoin="round" />
      <rect x="30" y="70" width="40" height="7" rx="1.5" fill="#111" />
      <g fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round">
        <path d="M38 64 c-5 -6 5 -11 0 -17 c-5 -6 5 -11 0 -17" />
        <path d="M50 64 c-5 -6 5 -11 0 -17 c-5 -6 5 -11 0 -17" />
        <path d="M62 64 c-5 -6 5 -11 0 -17 c-5 -6 5 -11 0 -17" />
      </g>
    </svg>
  )
}

/** The hot-surfaces caution shared by the stop dialog and the pause screen —
 *  worded and marked like the machine's CAUTION label: the hot-surface
 *  pictogram, hot surfaces inside, wear gloves, avoid contact. */
export function HotChamberCaution({ chamberTemp, className = '' }: { chamberTemp?: number; className?: string }) {
  const isHot = chamberTemp != null && chamberTemp >= ABORT_HOT_CHAMBER_C
  return (
    <div className={`flex items-center gap-3 rounded-lg px-2.5 py-2 text-left text-xs ${isHot ? 'bg-destructive/15 border border-destructive/40' : 'bg-accent/40'} ${className}`}>
      <HotSurfaceSign size={38} />
      <span className="text-foreground">
        <span className={`font-semibold ${isHot ? 'text-destructive' : 'text-orange-400'}`}>Caution — hot surfaces inside.</span>{' '}
        {isHot
          ? <>The chamber is at <span className="font-semibold">{Math.round(chamberTemp)}°C</span>. <span className="font-semibold">Wear heat-resistant gloves</span> and avoid contact with the chamber and the model.</>
          : <>The chamber and the model may still be warm — <span className="font-semibold">wear gloves</span> when handling.</>}
      </span>
    </div>
  )
}

interface AbortModalProps {
  isOpen: boolean
  onClose: () => void
  onAbort: () => void
  /** Live chamber temperature — drives the hot-chamber caution. */
  chamberTemp?: number
}

export default function AbortModal({ isOpen, onClose, onAbort, chamberTemp }: AbortModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md text-center" showCloseButton={false}>
        <DialogHeader className="items-center">
          <div className="w-12 h-12 bg-yellow-400 rounded-xl flex items-center justify-center mb-1">
            <AlertTriangle size={28} className="text-black" />
          </div>
          <DialogTitle className="text-2xl">Stop the Cure Process?</DialogTitle>
          <DialogDescription>
            Stopping now <span className="text-destructive font-semibold">ends the cycle immediately</span> — it cannot be resumed. To open the door and continue later, use <span className="text-cyan-300 font-semibold">Pause</span> instead.
          </DialogDescription>
        </DialogHeader>

        {/* What stopping mid-cycle can do to the model, and the hot-chamber caution */}
        <ul className="text-left text-xs space-y-2 my-1">
          <li className="flex items-start gap-2.5">
            <Eye size={16} className="text-yellow-400 shrink-0 mt-0.5" />
            <span className="text-foreground">
              The model's <span className="font-semibold">appearance and surface finish</span> may be affected.
            </span>
          </li>
          <li className="flex items-start gap-2.5">
            <Box size={16} className="text-yellow-400 shrink-0 mt-0.5" />
            <span className="text-foreground">
              A partially cured model may <span className="font-semibold">warp or lose its shape</span> and dimensional accuracy.
            </span>
          </li>
          <li><HotChamberCaution chamberTemp={chamberTemp} /></li>
        </ul>

        <DialogFooter className="flex-row gap-3 sm:justify-center">
          <Button variant="outline" onClick={onClose} className="flex-1">
            Keep Running
          </Button>
          <Button variant="destructive" onClick={onAbort} className="flex-1 bg-destructive text-destructive-foreground hover:bg-destructive/90">
            Yes, Stop
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
