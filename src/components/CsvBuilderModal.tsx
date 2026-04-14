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
import type { CureStep, Material, TimerMode, UvStartMode, CoolingMode } from '@/context/MaterialContext'

interface CsvBuilderModalProps {
  isOpen: boolean
  onClose: () => void
  editMaterial?: Material | null
}

type ProcessType = 'Heating' | 'Drying' | 'Cure' | 'Cooling' | 'Bleacher' | 'Nitrogen'

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
          temperature: proc === 'Nitrogen' ? null : proc === 'Cooling' ? (s.temperature ?? 25) : (s.temperature ?? 40),
          intensity: (proc === 'Cure' || proc === 'Bleacher') ? (s.intensity ?? 30) : null,
          coolingMode: proc === 'Cooling' ? (s.coolingMode ?? 'medium') : undefined,
          time: proc === 'Cooling' || proc === 'Nitrogen' ? 0 : (s.time || 10),
        }
      }
      return { ...s, [field]: value }
    }))
  }

  // Min temperature for a step: must be >= last non-cooling step's temp
  // A Cooling step in between resets the minimum back to 20
  const getMinTemp = (index: number): number => {
    for (let i = index - 1; i >= 0; i--) {
      if (steps[i].process === 'Cooling') return 20
      if (steps[i].temperature != null) return steps[i].temperature!
    }
    return 20
  }

  // For Cooling steps: max temp must be < the previous step's temperature
  const getCoolingMaxTemp = (index: number): number => {
    for (let i = index - 1; i >= 0; i--) {
      if (steps[i].temperature != null) return steps[i].temperature! - 5
    }
    return 75
  }

  // When temperature changes, also fix any following steps that are now below the new min
  const updateStepTemp = (index: number, value: number) => {
    setSteps(prev => {
      const next = [...prev]
      next[index] = { ...next[index], temperature: value }
      // Push up temperatures of following non-cooling steps (until a Cooling step)
      for (let i = index + 1; i < next.length; i++) {
        if (next[i].process === 'Cooling') break
        if (next[i].temperature != null && next[i].temperature! < value) {
          next[i] = { ...next[i], temperature: value }
        }
      }
      return next
    })
  }

  const totalDuration = steps.reduce((sum, s) => sum + (s.process === 'Cooling' || s.process === 'Nitrogen' ? 0 : (s.time || 0)), 0)

  // Nitrogen validation
  const nitrogenCount = steps.filter(s => s.process === 'Nitrogen').length
  const MAX_NITROGEN = 2

  // Get which processes are allowed after the previous step
  // Check if there was a Cooling step since the last Nitrogen
  const hadCoolingSinceLastN2 = (index: number): boolean => {
    for (let i = index - 1; i >= 0; i--) {
      if (steps[i].process === 'Cooling') return true
      if (steps[i].process === 'Nitrogen') return false
    }
    return true // no previous Nitrogen, so it's allowed
  }

  const getAllowedProcesses = (index: number): ProcessType[] => {
    const all: ProcessType[] = ['Drying', 'Heating', 'Cure', 'Bleacher', 'Cooling', 'Nitrogen']
    const prev = index > 0 ? steps[index - 1] : null

    // After Nitrogen: only Heating, Cure, or Bleacher allowed
    if (prev?.process === 'Nitrogen') {
      return ['Heating', 'Cure', 'Bleacher']
    }

    // Nitrogen only allowed after Cooling (and need Cooling between two N2 steps)
    if (!hadCoolingSinceLastN2(index)) {
      return all.filter(p => p !== 'Nitrogen')
    }

    return all
  }

  // Check if Nitrogen can be added (max 2 + must be after cooling)
  const canAddNitrogen = (index: number): boolean => {
    const currentIsNitrogen = steps[index]?.process === 'Nitrogen'
    if (currentIsNitrogen) return true
    if (nitrogenCount >= MAX_NITROGEN) return false
    if (!hadCoolingSinceLastN2(index)) return false
    return true
  }

  const generateCsv = () => {
    const header = 'Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,UVRampPercent,CoolingMode'
    const rows = steps.map(s => {
      const isCureOrBleacher = s.process === 'Cure' || s.process === 'Bleacher'
      return [
        s.step,
        s.process,
        s.process === 'Nitrogen' ? '' : (s.temperature ?? ''),
        s.process === 'Cooling' || s.process === 'Nitrogen' ? '' : s.time,
        isCureOrBleacher ? (s.timerMode ?? 'on-target') : '',
        isCureOrBleacher ? (s.uvIntensity ?? 30) : '',
        isCureOrBleacher ? (s.uvStartMode ?? 'at-target') : '',
        isCureOrBleacher && s.uvStartMode === 'at-ramp-percent' ? (s.uvRampPercent ?? 50) : '',
        s.process === 'Cooling' ? (s.coolingMode ?? 'medium') : '',
      ].join(',')
    })
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

  // After every N₂, there must be a Cooling or Drying step before program ends
  const hasN2WithoutCoolingOrDrying = (() => {
    let needsCoolingOrDrying = false
    for (const s of steps) {
      if (s.process === 'Nitrogen') needsCoolingOrDrying = true
      if (needsCoolingOrDrying && (s.process === 'Cooling' || s.process === 'Drying')) needsCoolingOrDrying = false
    }
    return needsCoolingOrDrying
  })()

  const handleSave = () => {
    if (!name.trim()) return
    if (steps.length === 0) return
    if (hasN2WithoutCoolingOrDrying) return

    if (isEditing && editMaterial) {
      updateMaterial(editMaterial.id, {
        name: name.trim(),
        steps,
        totalDuration,
      })
    } else {
      addMaterial({
        name: name.trim(),
        steps,
        totalDuration,
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
                    {getAllowedProcesses(i).map(proc => (
                      <SelectItem
                        key={proc}
                        value={proc}
                        disabled={proc === 'Nitrogen' && !canAddNitrogen(i)}
                      >
                        {proc === 'Cure' ? 'Cure (405nm)' : proc === 'Bleacher' ? 'Bleaching (450nm)' : proc === 'Nitrogen' ? 'N₂ Purge' : proc}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {step.process === 'Nitrogen' ? (
                <div className="text-muted-foreground text-xs px-1">
                  N₂ purge will run automatically if nitrogen is enabled on the system. Skipped otherwise.
                </div>
              ) : step.process === 'Cooling' ? (
                <>
                  <div className="flex items-center justify-between gap-4">
                    <label className="text-foreground text-sm">Target Temp</label>
                    <TouchNumber
                      value={step.temperature ?? 25}
                      onChange={v => updateStep(i, 'temperature', v)}
                      min={20} max={getCoolingMaxTemp(i)} step={5} suffix="°C"
                      className="w-[160px]"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <label className="text-foreground text-sm">Cooling Mode</label>
                    <Select value={step.coolingMode ?? 'medium'} onValueChange={v => updateStep(i, 'coolingMode', v)}>
                      <SelectTrigger className="w-[160px] h-10">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="fast">Fast</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="slow">Slow</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-between gap-4">
                  <label className="text-foreground text-sm">Temperature</label>
                  <TouchNumber
                    value={step.temperature}
                    onChange={v => updateStepTemp(i, v ?? getMinTemp(i))}
                    min={getMinTemp(i)} max={80} step={5} suffix="°C"
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

              {step.process !== 'Cooling' && step.process !== 'Nitrogen' && (
                <div className="flex items-center justify-between gap-4">
                  <label className="text-foreground text-sm">Time:</label>
                  <TouchNumber
                    value={step.time}
                    onChange={v => updateStep(i, 'time', v ?? 1)}
                    min={1} max={120} step={1} suffix=" min"
                    className="w-[160px]"
                  />
                </div>
              )}

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
          <Button onClick={handleSave} disabled={!name.trim() || steps.length === 0 || hasN2WithoutCoolingOrDrying} className="min-w-[90px]">
            {isEditing ? 'Update' : 'Save Program'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
