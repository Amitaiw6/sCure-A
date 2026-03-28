import CircularGauge from './CircularGauge'

export type PhaseType = 'heating' | 'drying' | 'cure' | 'cooling'
export type PhaseStatus = 'active' | 'completed' | 'pending'

interface PhaseCardProps {
  type: PhaseType
  status: PhaseStatus
  gaugeValue: string
  gaugeLabel: string
  gaugeProgress: number
  timeLeft: string
  rangeStart: string
  rangeEnd: string
  rangeProgress: number
  statusText: string
  minElapsed: string
  secElapsed: string
  percentComplete: string
  onAbort?: () => void
}

const phaseConfig = {
  heating: {
    label: 'Heating',
    icon: '🔥',
    color: 'stroke-orange-500',
    borderColor: 'border-orange-500',
    badgeBg: 'bg-orange-500',
    barColor: 'bg-orange-500',
    dotColor: 'bg-orange-500',
  },
  drying: {
    label: 'Drying Phase',
    icon: '⏱',
    color: 'stroke-blue-500',
    borderColor: 'border-blue-500',
    badgeBg: 'bg-blue-500',
    barColor: 'bg-blue-500',
    dotColor: 'bg-blue-500',
  },
  cure: {
    label: 'Cure',
    icon: '✦',
    color: 'stroke-purple-500',
    borderColor: 'border-purple-500',
    badgeBg: 'bg-purple-500',
    barColor: 'bg-purple-500',
    dotColor: 'bg-purple-500',
  },
  cooling: {
    label: 'Cooling',
    icon: '❄',
    color: 'stroke-teal-500',
    borderColor: 'border-teal-500',
    badgeBg: 'bg-teal-500',
    barColor: 'bg-teal-500',
    dotColor: 'bg-teal-500',
  },
}

export default function PhaseCard({
  type,
  status,
  gaugeValue,
  gaugeLabel,
  gaugeProgress,
  timeLeft,
  rangeStart,
  rangeEnd,
  rangeProgress,
  statusText,
  minElapsed,
  secElapsed,
  percentComplete,
  onAbort,
}: PhaseCardProps) {
  const config = phaseConfig[type]
  const isActive = status === 'active'
  const isPending = status === 'pending'

  return (
    <div
      className={`rounded-2xl p-5 flex flex-col items-center relative min-w-[220px] flex-1 ${
        isActive
          ? `border-2 ${config.borderColor} bg-gray-900/80`
          : isPending
            ? 'border border-dashed border-gray-600 bg-gray-900/40'
            : `border-2 ${config.borderColor} bg-gray-900/80`
      }`}
    >
      {/* Phase badge */}
      <div className={`absolute -top-4 left-4 px-4 py-1 rounded-full text-sm font-semibold flex items-center gap-1.5 ${
        isPending ? 'bg-gray-700 text-gray-400' : `${config.badgeBg} text-white`
      }`}>
        <span>{config.icon}</span>
        <span>{config.label}</span>
      </div>

      {/* Gauge */}
      <div className={`mt-6 ${isPending ? 'opacity-40' : ''}`}>
        {type === 'cure' ? (
          <div className="relative flex items-center justify-center" style={{ width: 140, height: 140 }}>
            <svg width={140} height={140} className="-rotate-90">
              <circle cx={70} cy={70} r={62} fill="none" stroke="#374151" strokeWidth={8} />
              {!isPending && (
                <circle cx={70} cy={70} r={62} fill="none" className={config.color} strokeWidth={8}
                  strokeDasharray={2 * Math.PI * 62} strokeDashoffset={2 * Math.PI * 62 - (gaugeProgress / 100) * 2 * Math.PI * 62} strokeLinecap="round" />
              )}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="w-16 h-0.5 bg-gray-500 mb-1" />
              <span className="text-xs text-gray-400 uppercase">UV + HEAT</span>
            </div>
          </div>
        ) : type === 'cooling' ? (
          <div className="relative flex items-center justify-center" style={{ width: 140, height: 140 }}>
            <svg width={140} height={140} className="-rotate-90">
              <circle cx={70} cy={70} r={62} fill="none" stroke="#374151" strokeWidth={8} />
              {!isPending && (
                <circle cx={70} cy={70} r={62} fill="none" className={config.color} strokeWidth={8}
                  strokeDasharray={2 * Math.PI * 62} strokeDashoffset={2 * Math.PI * 62 - (gaugeProgress / 100) * 2 * Math.PI * 62} strokeLinecap="round" />
              )}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="w-16 h-0.5 bg-gray-500 mb-1" />
              <span className="text-xs text-gray-400 uppercase">COOL</span>
            </div>
          </div>
        ) : (
          <CircularGauge
            value={gaugeValue}
            label={gaugeLabel}
            progress={isPending ? 0 : gaugeProgress}
            color={config.color}
          />
        )}
      </div>

      {/* Time left */}
      <p className={`mt-3 text-sm ${isPending ? 'text-gray-600' : 'text-gray-400'}`}>
        Time left: <span className={`font-bold ${isPending ? 'text-gray-600' : 'text-white'}`}>{timeLeft}</span>
      </p>

      {/* Range bar */}
      <div className={`w-full mt-3 ${isPending ? 'opacity-30' : ''}`}>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{rangeStart}</span>
          <span>{rangeEnd}</span>
        </div>
        <div className="w-full h-1.5 bg-gray-700 rounded-full">
          <div
            className={`h-full rounded-full ${config.barColor}`}
            style={{ width: `${rangeProgress}%` }}
          />
        </div>
      </div>

      {/* Status text */}
      <p className={`mt-3 text-sm ${isPending ? 'text-gray-600' : 'text-gray-400'}`}>{statusText}</p>

      {/* Dots */}
      <div className="flex gap-1.5 mt-2">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className={`w-2 h-2 rounded-full ${
            isPending ? 'bg-gray-700' : i === 0 ? config.dotColor : 'bg-gray-600'
          }`} />
        ))}
      </div>

      {/* Abort button (heating only when active) */}
      {type === 'heating' && isActive && onAbort && (
        <button
          onClick={onAbort}
          className="mt-3 bg-red-600 hover:bg-red-500 text-white text-sm font-semibold px-5 py-2 rounded-xl transition-colors"
        >
          Abort Process
        </button>
      )}

      {/* Bottom stats */}
      <div className={`flex items-center gap-0 mt-4 text-xs w-full border-t border-gray-700 pt-3 ${isPending ? 'text-gray-700' : 'text-gray-500'}`}>
        <div className="flex-1 text-center">
          <p className={`text-lg font-bold ${isPending ? 'text-gray-700' : 'text-white'}`}>{minElapsed}</p>
          <p className="uppercase text-[10px]">MIN ELAPSED</p>
        </div>
        <div className="w-px h-8 bg-gray-700" />
        <div className="flex-1 text-center">
          <p className={`text-lg font-bold ${isPending ? 'text-gray-700' : 'text-white'}`}>{secElapsed}</p>
          <p className="uppercase text-[10px]">SEC</p>
        </div>
        <div className="w-px h-8 bg-gray-700" />
        <div className="flex-1 text-center">
          <p className={`text-lg font-bold ${isPending ? 'text-gray-700' : 'text-white'}`}>{percentComplete}</p>
          <p className="uppercase text-[10px]">COMPLETE</p>
        </div>
      </div>
    </div>
  )
}
