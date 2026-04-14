import { Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type ProcessType = 'Cooling' | 'Cure' | 'Drying' | 'Heating' | 'Bleacher' | 'Nitrogen'

export type TimerMode = 'on-ramp' | 'on-target'
export type UvStartMode = 'at-start' | 'at-target' | 'at-ramp-percent'
export type CoolingMode = 'fast' | 'medium' | 'slow'

export interface StepData {
  id: string
  stepNumber: number
  processType: ProcessType
  temperature?: number
  intensity?: number
  time: number
  uvIntensity?: number
  timerMode?: TimerMode
  uvStartMode?: UvStartMode
  uvRampPercent?: number
  coolingMode?: CoolingMode
}

interface StepCardProps {
  step: StepData
  onEdit: (step: StepData) => void
}

const typeConfig: Record<ProcessType, { icon: string; borderColor: string; barColor: string; textColor: string }> = {
  Cooling: { icon: '❄', borderColor: 'border-teal-500/60', barColor: 'bg-teal-500', textColor: 'text-teal-400' },
  Cure: { icon: '✦', borderColor: 'border-purple-500/60', barColor: 'bg-purple-500', textColor: 'text-purple-400' },
  Drying: { icon: '◇', borderColor: 'border-blue-500/60', barColor: 'bg-blue-500', textColor: 'text-blue-400' },
  Heating: { icon: '🔥', borderColor: 'border-orange-500/60', barColor: 'bg-orange-500', textColor: 'text-orange-400' },
  Bleacher: { icon: '☀', borderColor: 'border-cyan-400/60', barColor: 'bg-cyan-400', textColor: 'text-cyan-300' },
  Nitrogen: { icon: 'N₂', borderColor: 'border-white/60', barColor: 'bg-white', textColor: 'text-white' },
}

export default function StepCard({ step, onEdit }: StepCardProps) {
  const config = typeConfig[step.processType]

  return (
    <div className={cn(
      'border rounded-xl p-3 min-w-[140px] max-w-[160px] bg-card flex flex-col',
      config.borderColor
    )}>
      {/* Header: number + icon + name + edit */}
      <div className="flex items-center gap-1 mb-2">
        <span className={cn(
          'w-5 h-5 rounded-full border flex items-center justify-center text-[10px] font-bold shrink-0',
          config.borderColor, config.textColor
        )}>
          {step.stepNumber}
        </span>
        <span className="text-xs">{config.icon}</span>
        <span className={cn('text-xs font-semibold truncate', config.textColor)}>
          {step.processType}
        </span>
        <Button variant="ghost" size="icon-xs" onClick={() => onEdit(step)} className="ml-auto shrink-0">
          <Pencil size={12} />
        </Button>
      </div>

      {/* Info */}
      <div className="text-[11px] text-muted-foreground space-y-0.5">
        {step.temperature != null && (
          <p>{step.processType === 'Cooling' ? 'Target' : 'Temp'}: <span className="text-foreground font-semibold">{step.temperature}°C</span></p>
        )}
        {step.processType === 'Cooling' && step.coolingMode && (
          <p>Mode: <span className="text-foreground font-semibold capitalize">{step.coolingMode}</span></p>
        )}
        {step.intensity != null && (
          <p>Int: <span className="text-foreground font-semibold">{step.intensity}%</span></p>
        )}
        {(step.processType === 'Cure' || step.processType === 'Bleacher') && step.uvIntensity != null && step.uvIntensity > 0 && (
          <p>UV: <span className="text-purple-400 font-semibold">{step.uvIntensity}%</span></p>
        )}
        <p>Time: <span className="text-foreground font-semibold">{step.time} min</span></p>
        {(step.processType === 'Cure' || step.processType === 'Bleacher') && step.timerMode === 'on-ramp' && (
          <p className="text-[9px] text-orange-400">Timer: on ramp start</p>
        )}
      </div>

      {/* Progress bar */}
      <div className="mt-2 w-full h-1 bg-border rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full', config.barColor)} style={{ width: '15%' }} />
      </div>
    </div>
  )
}
