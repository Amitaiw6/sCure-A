import { DoorOpen, Play, Square, Lock } from 'lucide-react'
import { HotChamberCaution } from '@/components/AbortModal'

interface PauseOverlayProps {
  /** Real door sensor: true closed, false open, null unreadable. */
  doorClosed: boolean | null
  chamberTemp: number
  phaseName: string
  /** Off-Pi there is no door sensor — Continue is always allowed. */
  apiConnected: boolean
  onContinue: () => void
  onStop: () => void
}

/** Full-screen "process paused" screen: every output is off and the door is
 *  released. Continue is gated on the door being closed again — the hardware
 *  interlock refuses heater/UV commands with the door open anyway. */
export default function PauseOverlay({ doorClosed, chamberTemp, phaseName, apiConnected, onContinue, onStop }: PauseOverlayProps) {
  const canContinue = !apiConnected || doorClosed === true
  return (
    <div className="fixed inset-0 z-50 bg-background/95 flex flex-col items-center justify-center gap-3 px-8">
      <div className="w-16 h-16 rounded-full bg-cyan-500/20 flex items-center justify-center">
        <DoorOpen size={36} className="text-cyan-400" />
      </div>
      <h2 className="text-foreground text-xl font-bold">Process Paused — Door Released</h2>
      <p className="text-muted-foreground text-sm text-center max-w-md">
        Heating, UV and gas are <span className="text-foreground font-semibold">off</span>. The <span className="text-foreground font-semibold">{phaseName}</span> step
        is on hold and will continue exactly where it stopped.
      </p>

      <HotChamberCaution chamberTemp={chamberTemp} className="max-w-md w-full" />

      <p className={`text-sm text-center font-medium ${canContinue ? 'text-green-400' : 'text-orange-400'}`}>
        {canContinue
          ? 'Door closed — press Continue to resume heating and UV.'
          : 'Close the chamber door to continue.'}
      </p>

      <div className="flex gap-4 mt-1">
        <button
          onClick={onStop}
          className="flex items-center gap-2 bg-destructive text-destructive-foreground px-6 py-3 rounded-2xl font-semibold active:scale-95 transition-transform touch-manipulation"
        >
          <Square size={18} />
          Stop Process
        </button>
        <button
          onClick={onContinue}
          disabled={!canContinue}
          className="flex items-center gap-2 bg-primary text-primary-foreground px-8 py-3 rounded-2xl font-semibold active:scale-95 transition-transform touch-manipulation disabled:opacity-40 disabled:active:scale-100"
        >
          {canContinue ? <Play size={18} /> : <Lock size={18} />}
          Continue
        </button>
      </div>
    </div>
  )
}
