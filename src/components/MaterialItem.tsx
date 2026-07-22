import { PlusCircle, ChevronRight, Lock, Star } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MaterialItemProps {
  label: string
  duration?: string
  isCommand?: boolean
  isSelected?: boolean
  isPreset?: boolean
  isFavorite?: boolean
  onToggleFavorite?: () => void
  onClick?: () => void
}

export default function MaterialItem({ label, duration, isCommand, isSelected, isPreset, isFavorite, onToggleFavorite, onClick }: MaterialItemProps) {
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
        {onToggleFavorite && (
          <button
            onClick={(e) => { e.stopPropagation(); onToggleFavorite() }}
            className="shrink-0 -ml-1 p-1 rounded-md hover:bg-white/10 transition-colors touch-manipulation"
            title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
          >
            <Star
              size={18}
              className={isFavorite ? 'text-yellow-400 fill-yellow-400' : 'text-muted-foreground/60'}
            />
          </button>
        )}
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
