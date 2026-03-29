import { ChevronUp, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface TouchSpinnerProps {
  value: number | null
  onChange: (value: number | null) => void
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  suffix?: string
  placeholder?: string
  className?: string
}

export function TouchSpinner({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  suffix = '',
  placeholder = '—',
  className,
}: TouchSpinnerProps) {
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
      'flex items-center rounded-lg border border-input bg-transparent h-10 px-3',
      disabled && 'opacity-30 pointer-events-none',
      className
    )}>
      <span className="flex-1 text-sm text-foreground select-none">{displayValue}</span>
      <div className="flex flex-col -my-1 ml-2">
        <button
          type="button"
          onClick={increment}
          className="flex items-center justify-center w-5 h-4 text-muted-foreground hover:text-foreground active:text-primary transition-colors touch-manipulation"
        >
          <ChevronUp size={14} />
        </button>
        <button
          type="button"
          onClick={decrement}
          className="flex items-center justify-center w-5 h-4 text-muted-foreground hover:text-foreground active:text-primary transition-colors touch-manipulation"
        >
          <ChevronDown size={14} />
        </button>
      </div>
    </div>
  )
}
