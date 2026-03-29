import { Pencil } from 'lucide-react'

export type ProcessType = 'Cooling' | 'Cure' | 'Drying' | 'Heating'

export interface StepData {
  id: string
  stepNumber: number
  processType: ProcessType
  temperature?: number
  intensity?: number
  time: number
}

interface StepCardProps {
  step: StepData
  onEdit: (step: StepData) => void
}

const typeConfig: Record<ProcessType, { icon: string; color: string; barColor: string; textColor: string }> = {
  Cooling: { icon: '❄', color: 'border-teal-500', barColor: 'bg-teal-500', textColor: 'text-teal-400' },
  Cure: { icon: '✦', color: 'border-purple-500', barColor: 'bg-purple-500', textColor: 'text-purple-400' },
  Drying: { icon: '◇', color: 'border-blue-500', barColor: 'bg-blue-500', textColor: 'text-blue-400' },
  Heating: { icon: '🔥', color: 'border-orange-500', barColor: 'bg-orange-500', textColor: 'text-orange-400' },
}

export default function StepCard({ step, onEdit }: StepCardProps) {
  const config = typeConfig[step.processType]
  const tempOrIntensity = step.temperature ?? step.intensity

  return (
    <div className={`border ${config.color} rounded-xl p-4 min-w-[170px] bg-gray-900/60`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-400 border border-gray-600 rounded-full w-5 h-5 flex items-center justify-center">
            {step.stepNumber}
          </span>
          <span className="text-sm">{config.icon}</span>
          <span className={`text-sm font-semibold ${config.textColor}`}>{step.processType}</span>
        </div>
        <button onClick={() => onEdit(step)} className="text-gray-500 hover:text-white transition-colors">
          <Pencil size={14} />
        </button>
      </div>

      {/* Info */}
      <div className="text-xs text-gray-400 space-y-0.5">
        <p>Temp: <span className="text-white font-semibold">{tempOrIntensity}°C</span></p>
        <p>Time: <span className="text-white font-semibold">{step.time} min</span></p>
      </div>

      {/* Progress bar */}
      <div className="mt-3 w-full h-1 bg-gray-700 rounded-full">
        <div className={`h-full rounded-full ${config.barColor}`} style={{ width: '15%' }} />
      </div>
    </div>
  )
}
