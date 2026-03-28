interface CircularGaugeProps {
  value: string
  label: string
  progress: number // 0-100
  color: string // tailwind color class like "stroke-orange-500"
  size?: number
}

export default function CircularGauge({ value, label, progress, color, size = 140 }: CircularGaugeProps) {
  const strokeWidth = 8
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (progress / 100) * circumference

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#374151"
          strokeWidth={strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          className={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-white">{value}</span>
        <span className="text-xs text-gray-400 uppercase tracking-wider">{label}</span>
      </div>
    </div>
  )
}
