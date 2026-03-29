import { PlusCircle, ChevronRight, Lock } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MaterialItemProps {
  label: string
  duration?: string
  isCommand?: boolean
  isSelected?: boolean
  isPreset?: boolean
  onClick?: () => void
}

export default function MaterialItem({ label, duration, isCommand, isSelected, isPreset, onClick }: MaterialItemProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-center justify-between rounded-2xl px-4 py-3 mb-2 transition-colors cursor-pointer group',
        isSelected
          ? 'bg-accent border border-primary/60'
          : 'bg-card border border-transparent hover:bg-accent'
      )}
    >
      <div className="flex items-center gap-3">
        {isPreset ? (
          <Lock size={16} className="text-muted-foreground/50" />
        ) : (
          <PlusCircle size={20} className="text-muted-foreground" />
        )}
        <span className="text-muted-foreground text-sm">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        {duration && (
          <span className={cn('text-xs font-medium', isCommand ? 'text-cyan-400' : 'text-cyan-400')}>
            {duration}
          </span>
        )}
        <ChevronRight size={16} className="text-muted-foreground group-hover:text-foreground transition-colors" />
      </div>
    </div>
  )
}
