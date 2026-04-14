import { useState } from 'react'
import { Plus, ArrowRight } from 'lucide-react'
import StepCard from '@/components/StepCard'
import StepModal from '@/components/StepModal'
import ImportCsvModal from '@/components/ImportCsvModal'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { StepData } from '@/components/StepCard'

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

  const displaySteps = [...steps].reverse()

  return (
    <main className="px-4 pb-16">
      {/* Material Name */}
      <div className="flex items-center gap-4 mt-6">
        <span className="text-muted-foreground text-sm whitespace-nowrap">Material Name:</span>
        <div
          className="flex-1 cursor-pointer flex items-center justify-between"
          onClick={() => setShowKeyboard(true)}
        >
          <Input readOnly value={materialName} className="cursor-pointer" />
        </div>
      </div>

      {/* Add CSV button */}
      <Button
        onClick={() => setShowImportModal(true)}
        className="mt-5 rounded-full"
      >
        + Add CSV
      </Button>

      {/* Process Sequence */}
      <h3 className="text-muted-foreground text-sm mt-8 mb-4">Process Sequence</h3>

      <div className="flex items-center gap-3 overflow-x-auto pb-4">
        {displaySteps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-3">
            <StepCard step={step} onEdit={handleEditStep} />
            {index < displaySteps.length - 1 && (
              <ArrowRight size={16} className="text-muted-foreground flex-shrink-0" />
            )}
          </div>
        ))}

        {steps.length > 0 && (
          <ArrowRight size={16} className="text-muted-foreground flex-shrink-0" />
        )}

        <button
          onClick={handleAddStep}
          className="w-20 h-20 rounded-full border-2 border-dashed border-border flex items-center justify-center text-muted-foreground hover:border-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
        >
          <Plus size={28} />
        </button>
      </div>

      {/* Save Program button */}
      <div className="fixed bottom-4 right-4">
        <Button className="rounded-2xl px-6 py-3 shadow-lg">
          Save Program
        </Button>
      </div>

      {/* Modals */}
      <StepModal
        isOpen={showStepModal}
        onClose={() => { setShowStepModal(false); setEditingStep(null) }}
        onSave={handleSaveStep}
        onDelete={editingStep ? handleDeleteStep : undefined}
        editStep={editingStep}
        stepNumber={editingStep ? editingStep.stepNumber : steps.length + 1}
        minTemp={(() => {
          const idx = editingStep ? editingStep.stepNumber - 1 : steps.length
          for (let i = idx - 1; i >= 0; i--) {
            if (steps[i].processType === 'Cooling') return 20
            if (steps[i].temperature != null) return steps[i].temperature!
          }
          return 20
        })()}
        maxCoolingTemp={(() => {
          const idx = editingStep ? editingStep.stepNumber - 1 : steps.length
          for (let i = idx - 1; i >= 0; i--) {
            if (steps[i].temperature != null) return steps[i].temperature! - 5
          }
          return 75
        })()}
      />

      <ImportCsvModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
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
