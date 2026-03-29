import { Minus, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface TouchNumberProps {
  value: number | null
  onChange: (value: number | null) => void
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  placeholder?: string
  suffix?: string
  className?: string
}

export function TouchNumber({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  placeholder = '—',
  suffix = '',
  className,
}: TouchNumberProps) {
  const displayValue = value !== null ? `${value}${suffix}` : placeholder

  const increment = () => {
    if (disabled) return
    const next = (value ?? min) + step
    onChange(Math.min(next, max))
  }

  const decrement = () => {
    if (disabled) return
    const next = (value ?? min) - step
    onChange(Math.max(next, min))
  }

  return (
    <div className={cn(
      'flex items-center gap-0 rounded-lg border border-input overflow-hidden',
      disabled && 'opacity-40 pointer-events-none',
      className
    )}>
      <button
        type="button"
        onClick={decrement}
        className="flex items-center justify-center w-9 h-9 bg-secondary hover:bg-accent active:bg-accent/80 transition-colors shrink-0 touch-manipulation"
      >
        <Minus size={14} className="text-muted-foreground" />
      </button>
      <div className="flex-1 text-center text-sm font-medium text-foreground min-w-[48px] select-none">
        {displayValue}
      </div>
      <button
        type="button"
        onClick={increment}
        className="flex items-center justify-center w-9 h-9 bg-secondary hover:bg-accent active:bg-accent/80 transition-colors shrink-0 touch-manipulation"
      >
        <Plus size={14} className="text-muted-foreground" />
      </button>
    </div>
  )
}
