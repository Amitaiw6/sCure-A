import { AlertTriangle, Thermometer } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'

interface HeaterFaultModalProps {
  isOpen: boolean
  /** 'start': the heater was NOT switched on (the command was refused). 'running': the heater was switched off mid-step. */
  when: 'start' | 'running'
  /** The machine's reason (which sensor, what it read). */
  message?: string
  /** Re-check the sensor and send the heating command again (cure page). Omitted on the Settings slider. */
  onRetry?: () => void
  onStop: () => void
  /** Label of the stop button ('Stop process' on the cure page, 'OK' in Settings). */
  stopLabel?: string
}

/** The heater's temperature sensor (the chamber NTC) is not reading. The heater is never
 *  switched on without it - there is no "continue anyway": without the sensor the heater
 *  has no temperature to control on and no over-temperature protection. */
export default function HeaterFaultModal({ isOpen, when, message, onRetry, onStop, stopLabel }: HeaterFaultModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={o => { if (!o) onStop() }}>
      <DialogContent className="max-w-md" onPointerDownOutside={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle size={20} />
            {when === 'running' ? 'Heater switched off — temperature sensor not reading' : 'Heater not started — temperature sensor not reading'}
          </DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-3 text-left">
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
                  <Thermometer size={14} /> Heater temperature sensor (chamber) — no reading
                </div>
                {message && <div className="mt-1 text-xs text-destructive/80">{message}</div>}
              </div>
              <p className="text-sm text-foreground">
                {when === 'running'
                  ? 'The sensor the heater is controlled on stopped reading, so the machine switched the heater off at once. Every output is off and the program is paused where it was.'
                  : 'The heater is only switched on while its temperature sensor reads. The sensor reads open (unplugged) or out of range, so the heater was not started.'}
              </p>
              <p className="text-xs text-muted-foreground">
                Check the chamber thermistor cable and its connector on the IO board, then {onRetry ? 'press Retry' : 'try again'}. Err 9010 is on the Alerts screen.
              </p>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant={onRetry ? 'outline' : 'default'} onClick={onStop}>{stopLabel ?? (when === 'running' ? 'Stop process' : 'Cancel')}</Button>
          {onRetry && <Button onClick={onRetry}>Retry</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
