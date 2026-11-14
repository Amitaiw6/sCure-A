import { PauseCircle, DoorOpen, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { HotChamberCaution } from '@/components/AbortModal'

interface PauseModalProps {
  isOpen: boolean
  onClose: () => void
  /** Confirm: outputs off, door released, run held until Continue. */
  onPause: () => void
  /** Live chamber temperature — drives the hot-surface caution. */
  chamberTemp?: number
}

/** Confirmation behind the Pause (⏸) button on the active step — a
 *  TEMPORARY stop, as opposed to Abort which ends the run for good. */
export default function PauseModal({ isOpen, onClose, onPause, chamberTemp }: PauseModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md text-center" showCloseButton={false}>
        <DialogHeader className="items-center">
          <div className="w-12 h-12 bg-cyan-500/20 rounded-xl flex items-center justify-center mb-1">
            <PauseCircle size={30} className="text-cyan-400" />
          </div>
          <DialogTitle className="text-2xl">Pause the Process?</DialogTitle>
          <DialogDescription>
            Heating, UV and gas <span className="text-foreground font-semibold">stop</span> and the door is <span className="text-foreground font-semibold">released</span>.
            The current step is held and continues exactly where it stopped when you press Continue.
          </DialogDescription>
        </DialogHeader>

        {/* A pause interrupts the cure: the models in the chamber may not come out as intended */}
        <div className="flex items-start gap-2.5 rounded-lg px-2.5 py-2 text-left text-xs bg-yellow-400/10 border border-yellow-400/40">
          <AlertTriangle size={16} className="text-yellow-400 shrink-0 mt-0.5" />
          <span className="text-foreground">
            <span className="text-yellow-400 font-semibold">Note —</span> pausing interrupts the cure and may
            <span className="font-semibold"> affect the quality of the models</span> in the process (surface finish, shape and dimensional accuracy).
          </span>
        </div>

        <HotChamberCaution chamberTemp={chamberTemp} className="my-1" />

        <DialogFooter className="flex-row gap-3 sm:justify-center">
          <Button variant="outline" onClick={onClose} className="flex-1">
            Keep Running
          </Button>
          <Button onClick={onPause} className="flex-1 bg-cyan-500 text-black hover:bg-cyan-400">
            <DoorOpen size={16} />
            Pause &amp; Open Door
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
