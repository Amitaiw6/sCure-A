import { AlertTriangle, Fan } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'

/** Human names for the machine's fan ids (io_controller FANS). */
export const FAN_NAMES: Record<string, string> = {
  FAN_LEFT: 'Left LED fan',
  FAN_RIGHT: 'Right LED fan',
  FAN_BACK: 'Back LED fan',
  FAN_DOOR: 'Door LED fan',
  FAN_HEATER: 'Heater fan',
  FAN_COOLING: 'Chamber intake fan',
}

/** The four LED panels, keyed like the machine's ledTemps. */
export const LED_PANEL_NAMES: Record<string, string> = {
  left: 'Left LED panel',
  right: 'Right LED panel',
  back: 'Back LED panel',
  door: 'Door LED panel',
}

interface FanFailModalProps {
  isOpen: boolean
  /** 'fan' (default): a fan is not rotating. 'led': an LED panel did not warm up while the UV was on. */
  kind?: 'fan' | 'led'
  /** Fan ids that failed (0 RPM / far below nominal). */
  fans: string[]
  /** 'preflight' = the check before the process started; 'running' = the cure was stopped. */
  when: 'preflight' | 'running'
  onContinue: () => void
  onStop: () => void
}

/** A fan is not rotating. Before a process: the start is held. During a cure: the
 *  outputs were switched off. Either way the operator decides: stop, or continue
 *  anyway (the machine then runs WITHOUT that fan — recorded). */
export default function FanFailModal({ isOpen, fans, when, onContinue, onStop, kind = 'fan' }: FanFailModalProps) {
  const names = fans.map(f => (kind === 'led' ? LED_PANEL_NAMES[f] : FAN_NAMES[f]) ?? f)
  const led = kind === 'led'
  return (
    <Dialog open={isOpen} onOpenChange={o => { if (!o) onStop() }}>
      <DialogContent className="max-w-md" onPointerDownOutside={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle size={20} />
            {led ? 'Cure stopped — LED panel not heating' : when === 'running' ? 'Cure stopped — fan failure' : 'Fan failure — process not started'}
          </DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-3 text-left">
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2">
                {names.map(n => (
                  <div key={n} className="flex items-center gap-2 text-sm font-semibold text-destructive">
                    <Fan size={14} /> {n} — {led ? 'did not heat up' : 'not rotating'}
                  </div>
                ))}
              </div>
              <p className="text-sm text-foreground">
                {led
                  ? 'The UV was on for 15 s (30 s at low power) and this panel\'s temperature sensor did not rise while the others did: the panel is not emitting (unplugged, driver, or its sensor is off the module). Every output was switched off and the program is paused where it was.'
                  : when === 'running'
                  ? 'Every output was switched off and the program is paused where it was.'
                  : 'All fans were tested before starting; the one above did not turn.'}
              </p>
              <p className="text-xs text-muted-foreground">
                {led
                  ? <><span className="font-semibold">Continue anyway</span> finishes the cure with this panel dark — the part will be under-cured on that side. Otherwise stop and check the panel connector.</>
                  : <><span className="font-semibold">Continue anyway</span> runs the machine without this fan — the LED or heater it cools can overheat. The choice is recorded. Otherwise stop and check the fan connector and blades.</>}
              </p>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={onStop}>
            {when === 'running' ? 'Stop process' : 'Cancel'}
          </Button>
          <Button variant="destructive" onClick={onContinue}>Continue anyway</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
