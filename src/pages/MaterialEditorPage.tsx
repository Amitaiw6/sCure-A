import { useState } from 'react'
import { Plus, Menu, ArrowRight } from 'lucide-react'
import StepCard from '../components/StepCard'
import StepModal from '../components/StepModal'
import ImportCsvModal from '../components/ImportCsvModal'
import OnScreenKeyboard from '../components/OnScreenKeyboard'
import type { StepData, ProcessType } from '../components/StepCard'

export default function MaterialEditorPage() {
  const [materialName, setMaterialName] = useState('Untitled')
  const [steps, setSteps] = useState<StepData[]>([])
  const [showStepModal, setShowStepModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showKeyboard, setShowKeyboard] = useState(false)
  const [editingStep, setEditingStep] = useState<StepData | null>(null)

  const handleAddStep = () => {
    setEditingStep(null)
    setShowStepModal(true)
  }

  const handleEditStep = (step: StepData) => {
    setEditingStep(step)
    setShowStepModal(true)
  }

  const handleSaveStep = (data: Omit<StepData, 'id'>) => {
    if (editingStep) {
      setSteps(prev => prev.map(s => s.id === editingStep.id ? { ...s, ...data } : s))
    } else {
      const newStep: StepData = {
        ...data,
        id: crypto.randomUUID(),
        stepNumber: steps.length + 1,
      }
      setSteps(prev => [...prev, newStep])
    }
    setShowStepModal(false)
    setEditingStep(null)
  }

  const handleDeleteStep = () => {
    if (editingStep) {
      setSteps(prev => {
        const filtered = prev.filter(s => s.id !== editingStep.id)
        return filtered.map((s, i) => ({ ...s, stepNumber: i + 1 }))
      })
    }
    setShowStepModal(false)
    setEditingStep(null)
  }

  const handleImport = (_file: File) => {
    // CSV parsing would go here
    const sampleSteps: StepData[] = [
      { id: crypto.randomUUID(), stepNumber: 1, processType: 'Heating' as ProcessType, temperature: 40, time: 10 },
      { id: crypto.randomUUID(), stepNumber: 2, processType: 'Drying' as ProcessType, temperature: 40, intensity: 30, time: 10 },
      { id: crypto.randomUUID(), stepNumber: 3, processType: 'Cure' as ProcessType, intensity: 30, time: 10 },
      { id: crypto.randomUUID(), stepNumber: 4, processType: 'Cooling' as ProcessType, temperature: 25, time: 5 },
    ]
    setSteps(sampleSteps)
    setShowImportModal(false)
  }

  // Reverse display order (highest step number first, left to right)
  const displaySteps = [...steps].reverse()

  return (
    <main className="px-4 pb-16">
      {/* Material Name */}
      <div className="flex items-center gap-4 mt-6">
        <span className="text-gray-500 text-sm whitespace-nowrap">Material Name:</span>
        <div
          className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg px-4 py-2.5 text-white cursor-pointer flex items-center justify-between"
          onClick={() => setShowKeyboard(true)}
        >
          <span>{materialName}</span>
          <Menu size={18} className="text-gray-400" />
        </div>
      </div>

      {/* Add CSV button */}
      <button
        onClick={() => setShowImportModal(true)}
        className="mt-5 bg-sky-500 hover:bg-sky-400 text-white text-sm font-semibold px-5 py-2 rounded-full transition-colors"
      >
        + Add CSV
      </button>

      {/* Process Sequence */}
      <h3 className="text-gray-500 text-sm mt-8 mb-4">Process Sequence</h3>

      <div className="flex items-center gap-3 overflow-x-auto pb-4">
        {displaySteps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-3">
            <StepCard step={step} onEdit={handleEditStep} />
            {index < displaySteps.length - 1 && (
              <ArrowRight size={16} className="text-gray-600 flex-shrink-0" />
            )}
          </div>
        ))}

        {/* Arrow before add button (if steps exist) */}
        {steps.length > 0 && (
          <ArrowRight size={16} className="text-gray-600 flex-shrink-0" />
        )}

        {/* Add step button */}
        <button
          onClick={handleAddStep}
          className="w-20 h-20 rounded-full border-2 border-dashed border-[#333] flex items-center justify-center text-gray-500 hover:border-gray-400 hover:text-gray-300 transition-colors flex-shrink-0"
        >
          <Plus size={28} />
        </button>
      </div>

      {/* Save Program button */}
      <div className="fixed bottom-6 right-6">
        <button className="bg-sky-500 hover:bg-sky-400 text-white font-semibold px-6 py-3 rounded-2xl shadow-lg transition-all active:scale-95">
          Save Program
        </button>
      </div>

      {/* Modals */}
      <StepModal
        isOpen={showStepModal}
        onClose={() => { setShowStepModal(false); setEditingStep(null) }}
        onSave={handleSaveStep}
        onDelete={editingStep ? handleDeleteStep : undefined}
        editStep={editingStep}
        stepNumber={editingStep ? editingStep.stepNumber : steps.length + 1}
      />

      <ImportCsvModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
      />

      <OnScreenKeyboard
        isOpen={showKeyboard}
        value={materialName}
        onChange={setMaterialName}
        onClose={() => setShowKeyboard(false)}
      />
    </main>
  )
}
