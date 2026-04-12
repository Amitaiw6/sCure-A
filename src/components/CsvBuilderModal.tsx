import { useState, useEffect } from 'react'
import { Plus, Trash2, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TouchNumber } from '@/components/ui/touch-number'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import { useMaterials } from '@/context/MaterialContext'
import type { CureStep, Material, TimerMode, UvStartMode } from '@/context/MaterialContext'

interface CsvBuilderModalProps {
  isOpen: boolean
  onClose: () => void
  editMaterial?: Material | null
}

type ProcessType = 'Heating' | 'Drying' | 'Cure' | 'Cooling' | 'Bleacher'

const emptyStep = (stepNum: number): CureStep => ({
  step: stepNum,
  process: 'Heating',
  temperature: 40,
  intensity: null,
  time: 10,
})

export default function CsvBuilderModal({ isOpen, onClose, editMaterial }: CsvBuilderModalProps) {
  const { addMaterial, updateMaterial } = useMaterials()
  const [name, setName] = useState('')
  const [showKeyboard, setShowKeyboard] = useState(false)
  const [steps, setSteps] = useState<CureStep[]>([emptyStep(1)])

  const isEditing = !!editMaterial

  // Load data when editing
  useEffect(() => {
    if (editMaterial) {
      setName(editMaterial.name)
      setSteps([...editMaterial.steps])
    } else {
      setName('')
      setSteps([emptyStep(1)])
    }
  }, [editMaterial, isOpen])

  const addNewStep = () => {
    setSteps(prev => [...prev, emptyStep(prev.length + 1)])
  }

  const removeStep = (index: number) => {
    setSteps(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, step: i + 1 })))
  }

  const updateStep = (index: number, field: keyof CureStep, value: string | number | null) => {
    setSteps(prev => prev.map((s, i) => {
      if (i !== index) return s
      if (field === 'process') {
        const proc = value as ProcessType
        return {
          ...s,
          process: proc,
          temperature: proc !== 'Cooling' ? (s.temperature ?? 40) : null,
          intensity: (proc === 'Cure' || proc === 'Bleacher') ? (s.intensity ?? 30) : null,
          coolingRate: proc === 'Cooling' ? (s.coolingRate ?? 5) : null,
        }
      }
      return { ...s, [field]: value }
    }))
  }

  const totalDuration = steps.reduce((sum, s) => sum + (s.time || 0), 0)

  const generateCsv = () => {
    const header = 'Step,Process,Temperature,Intensity,Time'
    const rows = steps.map(s =>
      `${s.step},${s.process},${s.temperature ?? ''},${s.intensity ?? ''},${s.time}`
    )
    return [header, ...rows].join('\n')
  }

  const handleDownloadCsv = () => {
    const csv = generateCsv()
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${name || 'untitled'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSave = () => {
    if (!name.trim()) return
    if (steps.length === 0) return

    const csvContent = generateCsv()

    if (isEditing && editMaterial) {
      updateMaterial(editMaterial.id, {
        name: name.trim(),
        steps,
        totalDuration,
        csvContent,
      })
    } else {
      addMaterial({
        name: name.trim(),
        steps,
        totalDuration,
        csvContent,
      })
    }

    setName('')
    setSteps([emptyStep(1)])
    onClose()
  }

  const handleClose = () => {
    setName('')
    setSteps([emptyStep(1)])
    onClose()
  }

  if (showKeyboard) {
    return (
      <OnScreenKeyboard
        isOpen={true}
        value={name}
        onChange={setName}
        onClose={() => setShowKeyboard(false)}
      />
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto scroll-hidden p-6" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-xl text-primary">
            {isEditing ? 'Edit Program' : 'Build Cure Program'}
          </DialogTitle>
        </DialogHeader>

        {/* Material Name */}
        <div className="flex items-center gap-4">
          <label className="text-foreground text-sm whitespace-nowrap">Name:</label>
          <div
            className="flex-1 h-10 flex items-center rounded-lg border border-input bg-transparent px-3 cursor-pointer hover:bg-accent/50 transition-colors"
            onClick={() => setShowKeyboard(true)}
          >
            <span className={name ? 'text-foreground text-sm' : 'text-muted-foreground text-sm'}>
              {name || 'Tap to enter name...'}
            </span>
          </div>
        </div>

        {/* Steps */}
        <div className="space-y-4">
          {steps.map((step, i) => (
            <div key={i} className="border border-border rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-primary text-sm font-medium">Step {step.step}</span>
                <Button variant="ghost" size="icon-xs" onClick={() => removeStep(i)} disabled={steps.length <= 1}>
                  <Trash2 size={14} className="text-destructive" />
                </Button>
              </div>

              <div className="flex items-center justify-between gap-4">
                <label className="text-foreground text-sm">Process Type</label>
                <Select value={step.process} onValueChange={v => updateStep(i, 'process', v)}>
                  <SelectTrigger className="w-[160px] h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Drying">Drying</SelectItem>
                    <SelectItem value="Heating">Heating</SelectItem>
                    <SelectItem value="Cure">Cure (405nm)</SelectItem>
                    <SelectItem value="Bleacher">Bleaching (450nm)</SelectItem>
                    <SelectItem value="Cooling">Cooling</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {step.process === 'Cooling' ? (
                <div className="flex items-center justify-between gap-4">
                  <label className="text-foreground text-sm">Cooling rate</label>
                  <TouchNumber
                    value={step.coolingRate ?? 5}
                    onChange={v => updateStep(i, 'coolingRate', v)}
                    min={1} max={20} step={1} suffix="°C/m"
                    className="w-[160px]"
                  />
                </div>
              ) : (
                <div className="flex items-center justify-between gap-4">
                  <label className="text-foreground text-sm">Temperature</label>
                  <TouchNumber
                    value={step.temperature}
                    onChange={v => updateStep(i, 'temperature', v)}
                    min={20} max={80} step={5} suffix="°C"
                    className="w-[160px]"
                  />
                </div>
              )}

              {false && (step.process === 'Cure' || step.process === 'Bleacher') && (
                <div className="flex items-center justify-between gap-4">
                  <label className="text-foreground text-sm">Intensity:</label>
                  <TouchNumber
                    value={step.intensity}
                    onChange={v => updateStep(i, 'intensity', v)}
                    min={0} max={100} step={5} suffix="%"
                    className="w-[160px]"
                  />
                </div>
              )}

              <div className="flex items-center justify-between gap-4">
                <label className="text-foreground text-sm">Time (Min):</label>
                <TouchNumber
                  value={step.time}
                  onChange={v => updateStep(i, 'time', v ?? 1)}
                  min={1} max={120} step={1} suffix=" min"
                  className="w-[160px]"
                />
              </div>

              {/* Cure/Bleacher options */}
              {(step.process === 'Cure' || step.process === 'Bleacher') && (
                <>
                  <div className="flex items-center justify-between gap-4">
                    <label className="text-foreground text-sm">Timer start:</label>
                    <Select value={step.timerMode ?? 'on-target'} onValueChange={v => updateStep(i, 'timerMode', v)}>
                      <SelectTrigger className="w-[160px] h-10">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="on-target">At temperature</SelectItem>
                        <SelectItem value="on-ramp">On ramp start</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-center justify-between gap-4">
                    <label className="text-foreground text-sm">UV Intensity:</label>
                    <TouchNumber
                      value={step.uvIntensity ?? 30}
                      onChange={v => updateStep(i, 'uvIntensity', v)}
                      min={5} max={100} step={5} suffix="%"
                      className="w-[160px]"
                    />
                  </div>

                  <div className="flex items-center justify-between gap-4">
                    <label className="text-foreground text-sm">UV starts:</label>
                    <Select value={step.uvStartMode ?? 'at-target'} onValueChange={v => updateStep(i, 'uvStartMode', v)}>
                      <SelectTrigger className="w-[160px] h-10">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="at-start">Immediately</SelectItem>
                        <SelectItem value="at-target">At temperature</SelectItem>
                        <SelectItem value="at-ramp-percent">At ramp %</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {step.uvStartMode === 'at-ramp-percent' && (
                    <div className="flex items-center justify-between gap-4">
                      <label className="text-foreground text-sm">Ramp %:</label>
                      <TouchNumber
                        value={step.uvRampPercent ?? 50}
                        onChange={v => updateStep(i, 'uvRampPercent', v)}
                        min={10} max={100} step={10} suffix="%"
                        className="w-[160px]"
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <Button variant="outline" onClick={addNewStep} className="gap-1">
            <Plus size={14} /> Add Step
          </Button>
          <span className="text-muted-foreground text-sm">
            <span className="text-foreground font-semibold">{steps.length}</span> steps · <span className="text-foreground font-semibold">{totalDuration} min</span>
          </span>
        </div>

        <DialogFooter className="flex-row gap-3">
          <Button variant="outline" size="sm" onClick={handleDownloadCsv} className="gap-1">
            <Download size={14} /> CSV
          </Button>
          <div className="flex-1" />
          <Button variant="outline" onClick={handleClose} className="min-w-[90px]">Cancel</Button>
          <Button onClick={handleSave} disabled={!name.trim() || steps.length === 0} className="min-w-[90px]">
            {isEditing ? 'Update' : 'Save Program'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
