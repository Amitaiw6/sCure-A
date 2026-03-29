import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import PhaseCard from '../components/PhaseCard'
import AbortModal from '../components/AbortModal'

type ActivePhase = 0 | 1 | 2 | 3

const phases = ['Heating', 'Drying', 'Cure', 'Cooling'] as const
const phaseColors = ['text-orange-400', 'text-blue-400', 'text-purple-400', 'text-teal-400']
const dotColors = ['bg-orange-500', 'bg-blue-500', 'bg-purple-500', 'bg-teal-500']

export default function CureProcessPage() {
  const [activePhase, setActivePhase] = useState<ActivePhase>(0)
  const [showAbort, setShowAbort] = useState(false)

  const currentStep = activePhase + 1
  const overallProgress = currentStep * 20

  const getPhaseStatus = (index: number) => {
    if (index < activePhase) return 'completed' as const
    if (index === activePhase) return 'active' as const
    return 'pending' as const
  }

  const nextPhaseIndex = activePhase + 1
  const nextPhaseName = nextPhaseIndex < 4 ? phases[nextPhaseIndex] : '-----'

  return (
    <main className="px-4 pb-4">
      {/* Cure Sequence Header */}
      <div className="bg-[#111] rounded-2xl p-4 mt-2">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <h2 className="text-white text-lg font-bold">Cure Sequence</h2>
            <div className="flex items-center gap-2 bg-[#1a1a1a] rounded-full px-4 py-1.5">
              <span className="text-gray-400 text-sm">Step {currentStep} of 4</span>
              <div className="flex gap-1 ml-1">
                {[0, 1, 2, 3].map(i => (
                  <div key={i} className={`w-6 h-3 rounded-sm ${
                    i <= activePhase ? dotColors[i] : 'bg-gray-600'
                  }`} />
                ))}
              </div>
            </div>
          </div>
          <p className="text-sm">
            <span className="text-gray-400">Overall Progress: </span>
            <span className="text-green-400 font-bold text-lg">{overallProgress}%</span>
          </p>
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xs text-gray-500">0%</span>
          <div className="flex-1 h-2 bg-gray-700 rounded-full">
            <div
              className="h-full bg-gradient-to-r from-green-500 to-green-400 rounded-full transition-all duration-500"
              style={{ width: `${overallProgress}%` }}
            />
          </div>
          <span className="text-xs text-gray-500">100%</span>
        </div>

        {/* Phase labels */}
        <div className="flex justify-between px-8">
          {phases.map((phase, i) => (
            <button
              key={phase}
              onClick={() => setActivePhase(i as ActivePhase)}
              className={`text-sm font-medium transition-colors ${
                i === activePhase ? phaseColors[i] : 'text-gray-500'
              }`}
            >
              {phase}
            </button>
          ))}
        </div>
      </div>

      {/* Next Phase */}
      <div className="flex items-center justify-between bg-[#111] rounded-xl px-5 py-3 mt-4 border-l-4 border-cyan-500">
        <div className="flex items-center gap-3">
          <span className="text-cyan-400 text-sm">Next Phase:</span>
          <span className="text-white font-bold text-lg">{nextPhaseName}</span>
          <span className="text-gray-500 text-sm">(Hold ar 80°C for 20 min . UV off)</span>
        </div>
        <ArrowRight size={20} className="text-gray-400" />
      </div>

      {/* Phase Cards */}
      <div className="flex gap-3 mt-4 overflow-x-auto pb-2">
        <PhaseCard
          type="heating"
          status={getPhaseStatus(0)}
          gaugeValue="7.5"
          gaugeLabel="RAMP °C/s"
          gaugeProgress={65}
          timeLeft="12:31"
          rangeStart="25°C"
          rangeEnd="80°C"
          rangeProgress={60}
          statusText="Ramping up team ..."
          minElapsed="00"
          secElapsed="00"
          percentComplete="0%"
          onAbort={() => setShowAbort(true)}
        />
        <PhaseCard
          type="drying"
          status={getPhaseStatus(1)}
          gaugeValue="0°"
          gaugeLabel="HOLD"
          gaugeProgress={0}
          timeLeft="20:00"
          rangeStart="0 min"
          rangeEnd="20 min"
          rangeProgress={0}
          statusText="Waiting for hear phase.."
          minElapsed="00"
          secElapsed="00"
          percentComplete="0%"
        />
        <PhaseCard
          type="cure"
          status={getPhaseStatus(2)}
          gaugeValue=""
          gaugeLabel=""
          gaugeProgress={0}
          timeLeft="20:00"
          rangeStart="25°C"
          rangeEnd="80°C"
          rangeProgress={0}
          statusText="Ramping up team ..."
          minElapsed="00"
          secElapsed="00"
          percentComplete="0%"
        />
        <PhaseCard
          type="cooling"
          status={getPhaseStatus(3)}
          gaugeValue=""
          gaugeLabel=""
          gaugeProgress={0}
          timeLeft="20:00"
          rangeStart="25°C"
          rangeEnd="80°C"
          rangeProgress={0}
          statusText="Ramping up team ..."
          minElapsed="00"
          secElapsed="00"
          percentComplete="0%"
        />
      </div>

      <AbortModal
        isOpen={showAbort}
        onClose={() => setShowAbort(false)}
        onAbort={() => setShowAbort(false)}
      />
    </main>
  )
}
