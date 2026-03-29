import { useState, useEffect } from 'react'
import type { ProcessType, StepData } from './StepCard'
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
}

const processTypes: ProcessType[] = ['Heating', 'Drying', 'Cure', 'Cooling']

export default function StepModal({ isOpen, onClose, onSave, onDelete, editStep, stepNumber }: StepModalProps) {
  const [processType, setProcessType] = useState<ProcessType>('Cooling')
  const [tempValue, setTempValue] = useState<number | null>(25)
  const [intensityValue, setIntensityValue] = useState<number | null>(null)
  const [time, setTime] = useState<number>(10)

  useEffect(() => {
    if (editStep) {
      setProcessType(editStep.processType)
      setTempValue(editStep.temperature ?? null)
      setIntensityValue(editStep.intensity ?? null)
      setTime(editStep.time)
    } else {
      setProcessType('Cooling')
      setTempValue(25)
      setIntensityValue(null)
      setTime(10)
    }
  }, [editStep, isOpen])

  const isEdit = !!editStep

  const handleProcessChange = (v: string) => {
    const proc = v as ProcessType
    setProcessType(proc)
    if (proc === 'Heating' || proc === 'Cooling') {
      setTempValue(prev => prev ?? 40)
      setIntensityValue(null)
    } else if (proc === 'Drying') {
      setTempValue(prev => prev ?? 40)
      setIntensityValue(prev => prev ?? 30)
    } else {
      setTempValue(null)
      setIntensityValue(prev => prev ?? 30)
    }
  }

  const showTemp = processType !== 'Cure'
  const showIntensity = processType === 'Drying' || processType === 'Cure'

  const handleSave = () => {
    const data: Omit<StepData, 'id'> = {
      stepNumber,
      processType,
      time,
    }
    if (showTemp && tempValue !== null) data.temperature = tempValue
    if (showIntensity && intensityValue !== null) data.intensity = intensityValue
    onSave(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[380px] p-6" showCloseButton={false}>
        {/* Header */}
        <DialogHeader className="flex-row items-center justify-between">
          <DialogTitle className="text-primary text-lg">{isEdit ? 'Edit Step' : 'Add Step'}</DialogTitle>
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
                  <SelectItem key={pt} value={pt}>{pt}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Temperature */}
          {showTemp && (
            <div className="flex items-center justify-between gap-4">
              <label className="text-foreground text-sm whitespace-nowrap">Temperature</label>
              <TouchNumber
                value={tempValue}
                onChange={setTempValue}
                min={20}
                max={80}
                step={5}
                suffix="deg"
                className="w-[160px]"
              />
            </div>
          )}

          {/* Intensity */}
          {showIntensity && (
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

          {/* Time */}
          <div className="flex items-center justify-between gap-4">
            <label className="text-foreground text-sm whitespace-nowrap">Time (Min):</label>
            <TouchNumber
              value={time}
              onChange={v => setTime(v ?? 1)}
              min={1}
              max={120}
              step={1}
              suffix="min"
              className="w-[160px]"
            />
          </div>
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
