import { useState } from 'react'
import { Delete, TerminalSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { useDevMode } from '@/context/DevModeContext'
import { cn } from '@/lib/utils'

const PASSWORD_LENGTH = 4

/**
 * Developer Mode authentication screen: numeric PIN pad opened after
 * 10 presses on the Settings gear. Wrong password → error, stay in
 * normal mode. Rendered once globally (see App.tsx).
 */
export default function DevAuthModal() {
  const { authOpen, closeAuth } = useDevMode()
  return (
    <Dialog open={authOpen} onOpenChange={open => { if (!open) closeAuth() }}>
      {/* Radix unmounts the content while closed, so PinEntry's state is
          fresh on every open — no reset effect needed */}
      {authOpen && <PinEntry />}
    </Dialog>
  )
}

function PinEntry() {
  const { closeAuth, tryPassword } = useDevMode()
  const [entry, setEntry] = useState('')
  const [error, setError] = useState(false)

  const pressDigit = (d: string) => {
    if (entry.length >= PASSWORD_LENGTH) return
    setError(false)
    const next = entry + d
    setEntry(next)
    if (next.length === PASSWORD_LENGTH) {
      // Small delay so the 4th dot is visible before the result
      setTimeout(() => {
        if (!tryPassword(next)) {
          setError(true)
          setEntry('')
        }
      }, 150)
    }
  }

  const backspace = () => { setError(false); setEntry(prev => prev.slice(0, -1)) }

  return (
      <DialogContent className="sm:max-w-xs text-center" showCloseButton>
        <DialogHeader className="items-center">
          <div className="w-12 h-12 bg-amber-500 rounded-xl flex items-center justify-center mb-1">
            <TerminalSquare size={26} className="text-black" />
          </div>
          <DialogTitle className="text-lg tracking-wide">Developer Mode</DialogTitle>
          <DialogDescription>Enter the Developer Mode password</DialogDescription>
        </DialogHeader>

        {/* Entry dots */}
        <div className="flex justify-center gap-3 py-1">
          {Array.from({ length: PASSWORD_LENGTH }).map((_, i) => (
            <span
              key={i}
              className={cn(
                'w-3.5 h-3.5 rounded-full border-2 transition-colors',
                i < entry.length ? 'bg-amber-500 border-amber-500' : 'border-muted-foreground/50',
                error && 'border-destructive',
              )}
            />
          ))}
        </div>
        <p className={cn('text-destructive text-xs h-4 -mt-2', !error && 'invisible')}>
          Incorrect password
        </p>

        {/* PIN pad */}
        <div className="grid grid-cols-3 gap-2">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => (
            <PinKey key={d} onClick={() => pressDigit(d)}>{d}</PinKey>
          ))}
          <div />
          <PinKey onClick={() => pressDigit('0')}>0</PinKey>
          <PinKey onClick={backspace}><Delete size={18} /></PinKey>
        </div>

        <Button variant="outline" onClick={closeAuth} className="w-full">
          Cancel
        </Button>
      </DialogContent>
  )
}

function PinKey({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="h-12 rounded-xl bg-secondary text-foreground text-lg font-semibold flex items-center justify-center hover:bg-accent active:bg-accent/70 transition-colors touch-manipulation select-none"
    >
      {children}
    </button>
  )
}
