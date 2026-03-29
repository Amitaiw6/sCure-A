import { useState } from 'react'

interface WakeScreenProps {
  onWake: () => void
}

export default function WakeScreen({ onWake }: WakeScreenProps) {
  const [tapCount, setTapCount] = useState(0)

  const handleTap = () => {
    const next = tapCount + 1
    setTapCount(next)
    if (next >= 2) {
      onWake()
    }
  }

  return (
    <div
      className="fixed inset-0 z-[99999] bg-black flex flex-col items-center justify-center touch-manipulation"
      onClick={handleTap}
    >
      <div className="text-muted-foreground/30 text-sm">
        {tapCount === 0 ? 'Tap to wake' : 'Tap again to start'}
      </div>
    </div>
  )
}
