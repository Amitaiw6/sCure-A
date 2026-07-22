import { useState, useEffect } from 'react'
import type { ProcessType, StepData, TimerMode, UvStartMode, CoolingMode } from './StepCard'
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


interface StepModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: Omit<StepData, 'id'>) => void
  onDelete?: () => void
  editStep?: StepData | null
  stepNumber: number
  minTemp?: number
  maxCoolingTemp?: number
}

const processTypes: ProcessType[] = ['Drying', 'Heating', 'Cure', 'Bleacher', 'Cooling', 'Nitrogen']

// Hardware limits (io_controller/components.json): the heater refuses targets
// below 30°C and the UV LEDs stay dark below 10% intensity.
const HEAT_MIN_TEMP = 30
const UV_MIN_INTENSITY = 10

export default function StepModal({ isOpen, onClose, onSave, onDelete, editStep, stepNumber, minTemp = HEAT_MIN_TEMP, maxCoolingTemp = 75 }: StepModalProps) {
  const [processType, setProcessType] = useState<ProcessType>('Cooling')
  const [tempValue, setTempValue] = useState<number | null>(25)
  const [intensityValue, setIntensityValue] = useState<number | null>(null)
  const [time, setTime] = useState<number>(10)
  const [uvIntensity, setUvIntensity] = useState<number | null>(null)
  const [timerMode, setTimerMode] = useState<TimerMode>('on-target')
  const [uvStartMode, setUvStartMode] = useState<UvStartMode>('at-target')
  const [, setUvRampPercent] = useState<number>(50)
  const [coolingMode, setCoolingMode] = useState<CoolingMode>('medium')

  useEffect(() => {
    if (editStep) {
      setProcessType(editStep.processType)
      setTempValue(editStep.temperature ?? null)
      setIntensityValue(editStep.intensity ?? null)
      setTime(editStep.time)
      setUvIntensity(editStep.uvIntensity ?? null)
      setTimerMode(editStep.timerMode ?? 'on-target')
      setUvStartMode(editStep.uvStartMode ?? 'at-target')
      setUvRampPercent(editStep.uvRampPercent ?? 50)
      setCoolingMode(editStep.coolingMode ?? 'medium')
    } else {
      setProcessType('Cooling')
      setTempValue(25)
      setIntensityValue(null)
      setTime(10)
      setUvIntensity(null)
      setTimerMode('on-target')
      setUvStartMode('at-target')
      setUvRampPercent(50)
      setCoolingMode('medium')
    }
  }, [editStep, isOpen])

  const isEdit = !!editStep

  const handleProcessChange = (v: string) => {
    const proc = v as ProcessType
    setProcessType(proc)
    if (proc === 'Heating') {
      setTempValue(prev => Math.max(prev ?? 40, HEAT_MIN_TEMP))
      setIntensityValue(null)
      setUvIntensity(null)
    } else if (proc === 'Cooling') {
      setTempValue(prev => prev ?? 25)
      setIntensityValue(null)
      setUvIntensity(null)
      setCoolingMode(prev => prev ?? 'medium')
    } else if (proc === 'Nitrogen') {
      setTempValue(null)
      setIntensityValue(null)
      setUvIntensity(null)
    } else if (proc === 'Drying') {
      setTempValue(prev => Math.max(prev ?? 40, HEAT_MIN_TEMP))
      setIntensityValue(null)
      setUvIntensity(null)
    } else {
      setTempValue(prev => Math.max(prev ?? 40, HEAT_MIN_TEMP))
      setIntensityValue(prev => prev ?? 30)
    }
  }

  const isCureOrBleacher = processType === 'Cure' || processType === 'Bleacher'
  const showIntensity = processType === 'Cure' || processType === 'Bleacher'

  const handleSave = () => {
    const data: Omit<StepData, 'id'> = {
      stepNumber,
      processType,
      time,
    }
    if (tempValue !== null) data.temperature = tempValue
    if (processType === 'Cooling') data.coolingMode = coolingMode
    if (showIntensity && intensityValue !== null) data.intensity = intensityValue
    if (isCureOrBleacher) {
      data.timerMode = timerMode
      data.uvIntensity = uvIntensity ?? 30
      data.uvStartMode = uvStartMode
    }
    onSave(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[380px] p-6" showCloseButton={false}>
        {/* Header */}
        <DialogHeader className="flex-row items-center justify-between">
          <DialogTitle className="text-lg">{isEdit ? 'Edit Step' : 'Add Step'}</DialogTitle>
          <span className="text-muted-foreground text-sm">Step {stepNumber}</span>
        </DialogHeader>

        {/* Fields */}
        <div className="space-y-4 mt-2">
          {/* Process Type */}
          <div className="flex items-center justify-between gap-4">
            <label className="text-foreground text-sm whitespace-nowrap">Process Type</label>
            <Select value={processType} onValueChange={handleProcessChange}>
              <SelectTrigger className="w-[160px] h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {processTypes.map(pt => (
                  <SelectItem key={pt} value={pt}>{pt === 'Bleacher' ? 'Bleaching (450nm)' : pt === 'Cure' ? 'Cure (405nm)' : pt}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Temperature (hidden for Nitrogen) */}
          {processType !== 'Nitrogen' && (
            <div className="flex items-center justify-between gap-4">
              <label className="text-foreground text-sm whitespace-nowrap">
                {processType === 'Cooling' ? 'Target Temp' : 'Temperature'}
              </label>
              <TouchNumber
                value={tempValue}
                onChange={setTempValue}
                min={processType === 'Cooling' ? 20 : Math.max(minTemp, HEAT_MIN_TEMP)}
                max={processType === 'Cooling' ? maxCoolingTemp : 80}
                step={5}
                suffix="°C"
                className="w-[160px]"
              />
            </div>
          )}

          {/* Nitrogen info */}
          {processType === 'Nitrogen' && (
            <div className="text-muted-foreground text-xs px-1">
              N₂ purge will run automatically if nitrogen is enabled. Skipped otherwise.
            </div>
          )}

          {/* Cooling Mode */}
          {processType === 'Cooling' && (
            <div className="flex items-center justify-between gap-4">
              <label className="text-foreground text-sm whitespace-nowrap">Cooling Mode</label>
              <Select value={coolingMode} onValueChange={v => setCoolingMode(v as CoolingMode)}>
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
          )}

          {/* Intensity - hidden, UV Intensity used instead */}
          {false && showIntensity && (
            <div className="flex items-center justify-between gap-4">
              <label className="text-foreground text-sm whitespace-nowrap">Intensity:</label>
              <TouchNumber
                value={intensityValue}
                onChange={setIntensityValue}
                min={0}
                max={100}
                step={5}
                suffix="%"
                className="w-[160px]"
              />
            </div>
          )}

          {/* Time - not shown for Cooling/Nitrogen */}
          {processType !== 'Cooling' && processType !== 'Nitrogen' && (
            <div className="flex items-center justify-between gap-4">
              <label className="text-foreground text-sm whitespace-nowrap">Time:</label>
              <TouchNumber
                value={time}
                onChange={v => setTime(v ?? 1)}
                min={1}
                max={processType === 'Bleacher' ? 720 : 120}
                step={1}
                suffix="min"
                className="w-[160px]"
              />
            </div>
          )}

          {/* Heating-only options */}
          {isCureOrBleacher && (
            <>
              {/* Timer Mode */}
              <div className="flex items-center justify-between gap-4">
                <label className="text-foreground text-sm whitespace-nowrap">Timer start:</label>
                <Select value={timerMode} onValueChange={v => setTimerMode(v as TimerMode)}>
                  <SelectTrigger className="w-[160px] h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="on-ramp">On ramp start</SelectItem>
                    <SelectItem value="on-target">At temperature</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* UV intensity + start mode */}
              <div className="flex items-center justify-between gap-4">
                <label className="text-foreground text-sm whitespace-nowrap">UV Intensity:</label>
                <TouchNumber
                  value={uvIntensity ?? 30}
                  onChange={v => setUvIntensity(v)}
                  min={UV_MIN_INTENSITY}
                  max={100}
                  step={5}
                  suffix="%"
                  className="w-[160px]"
                />
              </div>

              <div className="flex items-center justify-between gap-4">
                <label className="text-foreground text-sm whitespace-nowrap">UV starts:</label>
                <Select value={uvStartMode} onValueChange={v => setUvStartMode(v as UvStartMode)}>
                  <SelectTrigger className="w-[160px] h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="at-start">On ramp start</SelectItem>
                    <SelectItem value="at-target">At temperature</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
        </div>

        {/* Buttons */}
        <DialogFooter className="flex-row gap-3 mt-4">
          {isEdit && onDelete && (
            <Button variant="destructive" onClick={onDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90 border border-destructive">
              Delete
            </Button>
          )}
          <div className="flex-1" />
          <Button variant="outline" onClick={onClose} className="min-w-[90px]">Cancel</Button>
          <Button onClick={handleSave} className="min-w-[90px]">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
