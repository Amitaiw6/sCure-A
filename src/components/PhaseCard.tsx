import CircularGauge from './CircularGauge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type PhaseType = 'heating' | 'drying' | 'cure' | 'cooling' | 'bleacher' | 'nitrogen'
export type PhaseStatus = 'active' | 'completed' | 'pending'

interface PhaseCardProps {
  type: PhaseType
  status: PhaseStatus
  gaugeValue: string
  gaugeLabel: string
  gaugeProgress: number
  minElapsed: string
  secElapsed: string
  percentComplete: string
  onAbort?: () => void
}

const phaseConfig = {
  heating: { label: 'Heating', icon: '🔥', color: 'stroke-orange-500', borderColor: 'border-orange-500', badgeBg: 'bg-orange-500', dotColor: 'bg-orange-500' },
  drying: { label: 'Drying', icon: '⏱', color: 'stroke-blue-500', borderColor: 'border-blue-500', badgeBg: 'bg-blue-500', dotColor: 'bg-blue-500' },
  cure: { label: 'Cure', icon: '✦', color: 'stroke-purple-500', borderColor: 'border-purple-500', badgeBg: 'bg-purple-500', dotColor: 'bg-purple-500' },
  cooling: { label: 'Cooling', icon: '❄', color: 'stroke-teal-500', borderColor: 'border-teal-500', badgeBg: 'bg-teal-500', dotColor: 'bg-teal-500' },
  bleacher: { label: 'Bleaching', icon: '☀', color: 'stroke-cyan-400', borderColor: 'border-cyan-400', badgeBg: 'bg-cyan-400', dotColor: 'bg-cyan-400' },
  nitrogen: { label: 'N₂ Purge', icon: 'N₂', color: 'stroke-white', borderColor: 'border-white', badgeBg: 'bg-white', dotColor: 'bg-white' },
}

const GAUGE_SIZE = 130

export default function PhaseCard({
  type, status, gaugeValue, gaugeLabel, gaugeProgress,
  minElapsed, secElapsed, percentComplete, onAbort,
}: PhaseCardProps) {
  const config = phaseConfig[type]
  const isActive = status === 'active'
  const isPending = status === 'pending'
  const r = GAUGE_SIZE / 2 - 3

  return (
    <div className={cn(
      'rounded-xl p-3 flex flex-col items-center w-[240px] min-w-[240px] shrink-0 bg-card snap-start',
      isActive && `border-2 ${config.borderColor}`,
      isPending && 'border border-dashed border-border',
      !isActive && !isPending && `border-2 ${config.borderColor}`
    )}>
      {/* Phase badge */}
      <Badge className={cn(
        'gap-1 h-7 px-3 py-0 rounded-full text-xs whitespace-nowrap mb-2',
        isPending ? 'bg-secondary text-muted-foreground' : `${config.badgeBg} text-white`
      )}>
        <span>{config.icon}</span>
        <span>{config.label}</span>
      </Badge>

      {/* Gauge */}
      <div className={cn(isPending && 'opacity-40')}>
        {type === 'cure' || type === 'cooling' ? (
          <div className="relative flex items-center justify-center" style={{ width: GAUGE_SIZE, height: GAUGE_SIZE }}>
            <svg width={GAUGE_SIZE} height={GAUGE_SIZE} className="-rotate-90">
              <circle cx={GAUGE_SIZE / 2} cy={GAUGE_SIZE / 2} r={r} fill="none" stroke="#222" strokeWidth={6} />
              {!isPending && (
                <circle cx={GAUGE_SIZE / 2} cy={GAUGE_SIZE / 2} r={r} fill="none" className={config.color} strokeWidth={6}
                  strokeDasharray={2 * Math.PI * r} strokeDashoffset={2 * Math.PI * r - (gaugeProgress / 100) * 2 * Math.PI * r} strokeLinecap="round" />
              )}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="w-10 h-0.5 bg-muted-foreground mb-0.5" />
              <span className="text-[9px] text-muted-foreground uppercase">{type === 'cure' ? 'UV + HEAT' : 'COOL'}</span>
            </div>
          </div>
        ) : (
          <CircularGauge value={gaugeValue} label={gaugeLabel} progress={isPending ? 0 : gaugeProgress} color={config.color} size={GAUGE_SIZE} />
        )}
      </div>


      {/* Bottom stats */}
      <div className={cn('flex items-center gap-0 mt-2 text-xs w-full border-t border-border pt-2', isPending ? 'text-border' : 'text-muted-foreground')}>
        <div className="flex-1 text-center">
          <p className={cn('text-lg font-bold', isPending ? 'text-border' : 'text-foreground')}>{minElapsed}</p>
          <p className="uppercase text-[10px]">MIN</p>
        </div>
        <div className="w-px h-8 bg-border" />
        <div className="flex-1 text-center">
          <p className={cn('text-lg font-bold', isPending ? 'text-border' : 'text-foreground')}>{secElapsed}</p>
          <p className="uppercase text-[10px]">SEC</p>
        </div>
        <div className="w-px h-8 bg-border" />
        <div className="flex-1 text-center">
          <p className={cn('text-lg font-bold', isPending ? 'text-border' : 'text-foreground')}>{percentComplete}</p>
          <p className="uppercase text-[10px]">DONE</p>
        </div>
      </div>

      {/* Abort button — below the time stats */}
      {isActive && onAbort && (
        <Button variant="destructive" size="sm" onClick={onAbort} className="mt-2 bg-destructive text-destructive-foreground hover:bg-destructive/90 text-xs px-6">
          Abort
        </Button>
      )}
    </div>
  )
}
