import { useState, useEffect } from 'react'
import type { ProcessType, StepData } from './StepCard'

interface StepModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: Omit<StepData, 'id'>) => void
  onDelete?: () => void
  editStep?: StepData | null
  stepNumber: number
}

const processTypes: ProcessType[] = ['Cooling', 'Cure', 'Drying', 'Heating']

export default function StepModal({ isOpen, onClose, onSave, onDelete, editStep, stepNumber }: StepModalProps) {
  const [processType, setProcessType] = useState<ProcessType>('Cooling')
  const [secondValue, setSecondValue] = useState('')
  const [time, setTime] = useState('10')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  useEffect(() => {
    if (editStep) {
      setProcessType(editStep.processType)
      setSecondValue(
        editStep.temperature !== undefined
          ? String(editStep.temperature)
          : editStep.intensity !== undefined
            ? String(editStep.intensity)
            : ''
      )
      setTime(String(editStep.time))
    } else {
      setProcessType('Cooling')
      setSecondValue('25')
      setTime('10')
    }
  }, [editStep, isOpen])

  if (!isOpen) return null

  const isEdit = !!editStep

  const getSecondFieldLabel = () => {
    switch (processType) {
      case 'Cooling': return 'Temperature (°C)'
      case 'Heating': return 'Temperature'
      case 'Cure': return 'Intensity:'
      case 'Drying': return 'Intensity:'
    }
  }

  const getSecondFieldPlaceholder = () => {
    switch (processType) {
      case 'Cooling': return '25'
      case 'Heating': return '50 Deg'
      case 'Cure': return '30%'
      case 'Drying': return '50 Deg'
    }
  }

  const handleSave = () => {
    const data: Omit<StepData, 'id'> = {
      stepNumber,
      processType,
      time: parseInt(time) || 10,
    }
    if (processType === 'Cooling' || processType === 'Heating') {
      data.temperature = parseInt(secondValue) || 25
    } else {
      data.intensity = parseInt(secondValue) || 30
    }
    onSave(data)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-[#2a2a3e] rounded-2xl p-6 w-[400px] mx-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-sky-400">{isEdit ? 'Edit Step' : 'Add Step'}</h2>
          <span className="text-gray-400 text-sm">Step {stepNumber}</span>
        </div>

        {/* Process Type */}
        <div className="flex items-center justify-between mb-4 relative">
          <label className="text-gray-300 text-sm">Process Type</label>
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="bg-gray-800 border border-gray-600 rounded-lg px-4 py-2 text-white text-sm min-w-[150px] text-left flex items-center justify-between"
            >
              {processType}
              <span className="text-gray-400 text-xs ml-2">⌃</span>
            </button>
            {dropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white rounded-lg shadow-xl z-10 overflow-hidden">
                {processTypes.map(pt => (
                  <button
                    key={pt}
                    onClick={() => { setProcessType(pt); setDropdownOpen(false) }}
                    className="w-full text-left px-4 py-2.5 text-gray-800 text-sm hover:bg-gray-100 transition-colors"
                  >
                    {pt}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Second field */}
        <div className="flex items-center justify-between mb-4">
          <label className="text-gray-300 text-sm">{getSecondFieldLabel()}</label>
          <input
            type="text"
            value={secondValue}
            onChange={e => setSecondValue(e.target.value)}
            placeholder={getSecondFieldPlaceholder()}
            className="bg-gray-800 border border-gray-600 rounded-lg px-4 py-2 text-white text-sm min-w-[150px] outline-none focus:border-sky-500"
          />
        </div>

        {/* Time */}
        <div className="flex items-center justify-between mb-6">
          <label className="text-gray-300 text-sm">Time (Min):</label>
          <input
            type="text"
            value={time}
            onChange={e => setTime(e.target.value)}
            placeholder="10 min"
            className="bg-gray-800 border border-gray-600 rounded-lg px-4 py-2 text-white text-sm min-w-[150px] outline-none focus:border-sky-500"
          />
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-3">
          {isEdit && onDelete && (
            <button
              onClick={onDelete}
              className="px-4 py-2.5 rounded-xl border border-red-500 text-red-500 text-sm font-semibold hover:bg-red-500/10 transition-colors"
            >
              Delete
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl border border-gray-600 text-gray-400 text-sm font-semibold hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-6 py-2.5 rounded-xl bg-sky-500 text-white text-sm font-semibold hover:bg-sky-400 transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
