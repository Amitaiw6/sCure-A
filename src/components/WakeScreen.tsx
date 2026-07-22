import { useState } from 'react'
import SCureLogo from '@/components/SCureLogo'

interface WakeScreenProps {
  onWake: () => void
  // When true (Sleep mode), keep the display fully black to protect the screen
  // until the user touches it — only then reveal the wake hint.
  blank?: boolean
}

export default function WakeScreen({ onWake, blank = false }: WakeScreenProps) {
  const [tapCount, setTapCount] = useState(0)

  const handleTap = () => {
    const next = tapCount + 1
    setTapCount(next)
    if (next >= 2) {
      onWake()
    }
  }

  // Sleep mode stays pure black until first touch; the screensaver always shows the hint
  const showHint = !blank || tapCount > 0

  return (
    <div
      className="fixed inset-0 z-[99999] bg-black flex flex-col items-center justify-center gap-4 touch-manipulation"
      onClick={handleTap}
    >
      {showHint && (
        <>
          <SCureLogo size={64} color="#ffffff" className="opacity-40" />
          <div className="text-muted-foreground/30 text-sm">
            {tapCount === 0 ? 'Tap to wake' : 'Tap again to start'}
          </div>
        </>
      )}
    </div>
  )
}
