import { useState, useEffect, useRef, useCallback } from 'react'
import { Plus, Trash2, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TouchNumber } from '@/components/ui/touch-number'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import OnScreenKeyboard from '@/components/OnScreenKeyboard'
import { useMaterials } from '@/context/MaterialContext'
import { exportCsvToUsb } from '@/services/hardware-api'
import type { CureStep, Material } from '@/context/MaterialContext'

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
  const [showSaveError, setShowSaveError] = useState(false)
  const [csvMsg, setCsvMsg] = useState<{ text: string; error: boolean } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const isEditing = !!editMaterial

  // Load data when editing
  useEffect(() => {
    setCsvMsg(null)
    if (editMaterial) {
      setName(editMaterial.name)
      setSteps([...editMaterial.steps])
    } else {
      setName('')
      setSteps([emptyStep(1)])
    }
  }, [editMaterial, isOpen])

  const scrollToStep = useCallback((index: number) => {
    requestAnimationFrame(() => {
      const container = scrollRef.current
      if (!container) return
      const cards = container.querySelectorAll<HTMLElement>('[data-step-card]')
      const card = cards[index]
      if (!card) return
      const scrollLeft = card.offsetLeft - (container.clientWidth / 2) + (card.clientWidth / 2)
      container.scrollTo({ left: scrollLeft, behavior: 'smooth' })
    })
  }, [])

  const addNewStep = () => {
    setSteps(prev => {
      const base = emptyStep(prev.length + 1)
      const last = prev[prev.length - 1]
      const beforeLast = prev[prev.length - 2]
      let newStep: CureStep = base
      if (last?.process === 'Nitrogen') {
        // Only Cure/Bleaching may follow an N₂ purge — default to Cure
        newStep = { ...base, process: 'Cure', intensity: 30 }
      } else if (beforeLast?.process === 'Nitrogen' && (last?.process === 'Cure' || last?.process === 'Bleacher')) {
        // After the Cure/Bleaching that followed N₂ — only Cooling is allowed
        newStep = { ...base, process: 'Cooling', temperature: 25, coolingMode: 'medium', time: 0 }
      }
      const next = [...prev, newStep]
      scrollToStep(next.length - 1)
      return next
    })
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

  // Min temperature for a heat-type step: must be >= last non-cooling step's
  // temp, and never below the hardware heating floor (heating.target_min=30 —
  // the heater driver refuses lower targets). A Cooling step in between
  // resets the minimum back to that floor.
  const HEAT_MIN_TEMP = 30
  const getMinTemp = (index: number): number => {
    for (let i = index - 1; i >= 0; i--) {
      if (steps[i].process === 'Cooling') return HEAT_MIN_TEMP
      if (steps[i].temperature != null) return Math.max(steps[i].temperature!, HEAT_MIN_TEMP)
    }
    return HEAT_MIN_TEMP
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
    const prevPrev = index > 1 ? steps[index - 2] : null

    // After Nitrogen: only Cure or Bleaching allowed
    if (prev?.process === 'Nitrogen') {
      return ['Cure', 'Bleacher']
    }

    // After the Cure/Bleaching that followed an N₂ purge: only Cooling (vent)
    if (prevPrev?.process === 'Nitrogen' && (prev?.process === 'Cure' || prev?.process === 'Bleacher')) {
      return ['Cooling']
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
        '',
        s.process === 'Cooling' ? (s.coolingMode ?? 'medium') : '',
      ].join(',')
    })
    return [header, ...rows].join('\n')
  }

  const browserDownloadCsv = (csv: string, filename: string) => {
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDownloadCsv = async () => {
    const csv = generateCsv()
    const filename = `${name || 'untitled'}.csv`
    // Primary path: write the CSV to the USB drive connected to the machine.
    const res = await exportCsvToUsb(filename, csv)
    if (res.ok) {
      setCsvMsg({ text: res.message || 'Saved to USB', error: false })
      return
    }
    // Fallback (dev, or no USB connected): hand the file to the browser.
    browserDownloadCsv(csv, filename)
    setCsvMsg({
      text: res.message?.includes('No USB')
        ? 'No USB drive — downloaded the file instead'
        : 'Downloaded the file',
      error: true,
    })
  }

  const hasNitrogen = steps.some(s => s.process === 'Nitrogen')

  // Each N₂ purge must be followed by a Cure/Bleaching step, then a Cooling step:
  //   N₂ → (Cure | Bleaching) → Cooling
  const n2BlockError = (() => {
    for (let i = 0; i < steps.length; i++) {
      if (steps[i].process !== 'Nitrogen') continue
      const next = steps[i + 1]
      const after = steps[i + 2]
      if (!next || (next.process !== 'Cure' && next.process !== 'Bleacher')) {
        return 'After N₂ purge, add a Cure or Bleaching step'
      }
      if (!after || after.process !== 'Cooling') {
        return 'After the Cure/Bleaching that follows N₂, add a Cooling step'
      }
    }
    return null
  })()

  // Validation error message
  const saveError = (() => {
    if (!name.trim()) return 'Enter a program name'
    if (steps.length === 0) return 'Add at least one step'
    if (hasNitrogen && n2BlockError) return n2BlockError
    return null
  })()

  const handleSave = () => {
    if (saveError) return

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
      {/* Fixed 550x460 dialog per the design reference (design-handoff/sCure-UI.html) */}
      <DialogContent className="!w-[550px] !max-w-[550px] h-[460px] max-h-[460px] p-0 gap-0 flex flex-col overflow-hidden" showCloseButton={false}>
        {/* Top bar */}
        <div className="flex items-center gap-4 px-4 py-2 shrink-0 border-b border-border">
          <DialogHeader className="p-0">
            <DialogTitle className="text-lg whitespace-nowrap">
              {isEditing ? 'Edit Program' : 'Build Cure Program'}
            </DialogTitle>
          </DialogHeader>
          <label className="text-foreground text-sm whitespace-nowrap ml-auto">Name:</label>
          <div
            className="w-[260px] h-10 flex items-center rounded-lg border border-input bg-transparent px-3 cursor-pointer hover:bg-accent/50 transition-colors"
            onClick={() => setShowKeyboard(true)}
          >
            <span className={name ? 'text-foreground text-sm' : 'text-muted-foreground text-sm'}>
              {name || 'Tap to enter name...'}
            </span>
          </div>
        </div>

        {/* Steps - horizontal scroll */}
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden scroll-hidden px-4 py-3" style={{ WebkitOverflowScrolling: 'touch', touchAction: 'pan-x' }}>
          <div className="flex gap-3 h-full items-center">
            {steps.map((step, i) => (
              <div key={i} data-step-card className="border border-border rounded-xl p-3 shrink-0 w-[240px] overflow-y-auto scroll-hidden max-h-full">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-primary text-sm font-medium">Step {step.step}</span>
                  <Button variant="ghost" size="icon-xs" onClick={() => removeStep(i)} disabled={steps.length <= 1}>
                    <Trash2 size={14} className="text-destructive" />
                  </Button>
                </div>

                <div className="space-y-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <label className="text-foreground text-sm">Process</label>
                    <Select value={step.process} onValueChange={v => updateStep(i, 'process', v)}>
                      <SelectTrigger className="w-[140px] h-9">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent position="popper" side="bottom" sideOffset={4}>
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
                      N₂ purge runs automatically if nitrogen is enabled.
                    </div>
                  ) : step.process === 'Cooling' ? (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <label className="text-foreground text-sm">Target Temp</label>
                        <TouchNumber
                          value={step.temperature ?? 25}
                          onChange={v => updateStep(i, 'temperature', v)}
                          min={20} max={getCoolingMaxTemp(i)} step={5} suffix="°C"
                          className="w-[140px]"
                        />
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <label className="text-foreground text-sm">Cooling Mode</label>
                        <Select value={step.coolingMode ?? 'medium'} onValueChange={v => updateStep(i, 'coolingMode', v)}>
                          <SelectTrigger className="w-[140px] h-9">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent position="popper" side="bottom" sideOffset={4}>
                            <SelectItem value="fast">Fast</SelectItem>
                            <SelectItem value="medium">Medium</SelectItem>
                            <SelectItem value="slow">Slow</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <label className="text-foreground text-sm">Temperature</label>
                      <TouchNumber
                        value={step.temperature}
                        onChange={v => updateStepTemp(i, v ?? getMinTemp(i))}
                        min={getMinTemp(i)} max={80} step={5} suffix="°C"
                        className="w-[140px]"
                      />
                    </div>
                  )}

                  {false && (step.process === 'Cure' || step.process === 'Bleacher') && (
                    <div className="flex items-center justify-between gap-3">
                      <label className="text-foreground text-sm">Intensity:</label>
                      <TouchNumber
                        value={step.intensity}
                        onChange={v => updateStep(i, 'intensity', v)}
                        min={0} max={100} step={5} suffix="%"
                        className="w-[140px]"
                      />
                    </div>
                  )}

                  {step.process !== 'Cooling' && step.process !== 'Nitrogen' && (
                    <div className="flex items-center justify-between gap-3">
                      <label className="text-foreground text-sm">Time:</label>
                      <TouchNumber
                        value={step.time}
                        onChange={v => updateStep(i, 'time', v ?? 1)}
                        min={1} max={step.process === 'Bleacher' ? 720 : 120} step={1} suffix=" min"
                        className="w-[140px]"
                      />
                    </div>
                  )}

                  {/* Cure/Bleacher options */}
                  {(step.process === 'Cure' || step.process === 'Bleacher') && (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <label className="text-foreground text-sm">Timer start:</label>
                        <Select value={step.timerMode ?? 'on-target'} onValueChange={v => updateStep(i, 'timerMode', v)}>
                          <SelectTrigger className="w-[140px] h-9">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent position="popper" side="bottom" sideOffset={4}>
                            <SelectItem value="on-ramp">On ramp start</SelectItem>
                            <SelectItem value="on-target">At temperature</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="flex items-center justify-between gap-3">
                        <label className="text-foreground text-sm">UV Intensity:</label>
                        <TouchNumber
                          value={step.uvIntensity ?? 30}
                          onChange={v => updateStep(i, 'uvIntensity', v)}
                          min={10} max={100} step={5} suffix="%"
                          className="w-[140px]"
                        />
                      </div>

                      <div className="flex items-center justify-between gap-3">
                        <label className="text-foreground text-sm">UV starts:</label>
                        <Select value={step.uvStartMode ?? 'at-target'} onValueChange={v => updateStep(i, 'uvStartMode', v)}>
                          <SelectTrigger className="w-[140px] h-9">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent position="popper" side="bottom" sideOffset={4}>
                            <SelectItem value="at-start">On ramp start</SelectItem>
                            <SelectItem value="at-target">At temperature</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}

            {/* Add Step */}
            <button
              onClick={addNewStep}
              className="border border-dashed border-border rounded-xl shrink-0 w-[70px] self-stretch flex flex-col items-center justify-center gap-2 hover:border-primary/50 hover:bg-accent/30 transition-colors touch-manipulation"
            >
              <Plus size={20} className="text-muted-foreground" />
              <span className="text-muted-foreground text-[10px]">Add Step</span>
            </button>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="shrink-0 border-t border-border px-4 py-2">
          {showSaveError && saveError && (
            <div className="text-destructive text-xs text-center mb-1.5">{saveError}</div>
          )}
          {csvMsg && (
            <div className={`text-xs text-center mb-1.5 ${csvMsg.error ? 'text-yellow-500' : 'text-green-500'}`}>{csvMsg.text}</div>
          )}
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" onClick={handleDownloadCsv} className="gap-1">
              <Download size={14} /> CSV
            </Button>
            <span className="text-muted-foreground text-sm whitespace-nowrap">
              <span className="text-foreground font-semibold">{steps.length}</span> steps · <span className="text-foreground font-semibold">{totalDuration} min</span>
            </span>
            <div className="flex-1" />
            <Button variant="outline" onClick={handleClose} className="min-w-[90px]">Cancel</Button>
            <Button
              onClick={() => { if (saveError) { setShowSaveError(true) } else { handleSave() } }}
              onPointerDown={() => { if (saveError) setShowSaveError(true) }}
              onPointerLeave={() => setShowSaveError(false)}
              className={`min-w-[120px] ${saveError ? 'opacity-50' : ''}`}
            >
              {isEditing ? 'Update' : 'Save Program'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
