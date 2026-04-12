import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'

export type TimerMode = 'on-ramp' | 'on-target'
export type UvStartMode = 'at-start' | 'at-target' | 'at-ramp-percent'

export interface CureStep {
  step: number
  process: 'Heating' | 'Drying' | 'Cure' | 'Cooling' | 'Bleacher'
  temperature: number | null
  intensity: number | null
  time: number
  uvIntensity?: number | null
  timerMode?: TimerMode
  uvStartMode?: UvStartMode
  uvRampPercent?: number
  coolingRate?: number | null
}

export interface Material {
  id: string
  name: string
  steps: CureStep[]
  totalDuration: number
  csvContent: string
  createdAt: string
  isPreset: boolean
}

interface MaterialContextType {
  materials: Material[]
  addMaterial: (material: Omit<Material, 'id' | 'createdAt' | 'isPreset'>) => void
  updateMaterial: (id: string, data: { name: string; steps: CureStep[]; totalDuration: number; csvContent: string }) => void
  addMaterialFromCsv: (fileName: string, csvContent: string) => { success: boolean; errors: string[] }
  removeMaterial: (id: string) => void
  selectedMaterialId: string | null
  setSelectedMaterialId: (id: string | null) => void
  getMaterialCsv: (id: string) => string | undefined
  isLoading: boolean
}

const STORAGE_KEY = 'scure-materials'

function stepsToCsv(steps: CureStep[]): string {
  const header = 'Step,Process,Temperature,Intensity,Time,CoolingRate,UvIntensity,TimerMode,UvStartMode,UvRampPercent'
  const rows = steps.map(s =>
    `${s.step},${s.process},${s.temperature ?? ''},${s.intensity ?? ''},${s.time},${s.coolingRate ?? ''},${s.uvIntensity ?? ''},${s.timerMode ?? ''},${s.uvStartMode ?? ''},${s.uvRampPercent ?? ''}`
  )
  return [header, ...rows].join('\n')
}

const VALID_PROCESSES = ['Heating', 'Drying', 'Cure', 'Cooling', 'Bleacher'] as const
const VALID_TIMER_MODES: TimerMode[] = ['on-ramp', 'on-target']
const VALID_UV_START: UvStartMode[] = ['at-start', 'at-target', 'at-ramp-percent']

export interface CsvParseResult {
  steps: CureStep[] | null
  errors: string[]
}

function parseCsv(csvContent: string): CsvParseResult {
  const errors: string[] = []
  const lines = csvContent.trim().split('\n')

  if (lines.length < 2) {
    return { steps: null, errors: ['CSV must have a header row and at least one data row'] }
  }

  const header = lines[0].toLowerCase()
  if (!header.includes('process') && !header.includes('step')) {
    return { steps: null, errors: ['Missing required header: "Step" or "Process"'] }
  }

  const steps: CureStep[] = []
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',').map(c => c.trim())
    if (cols.length < 5) {
      errors.push(`Row ${i}: Not enough columns (need at least 5)`)
      continue
    }

    const process = cols[1]
    if (!VALID_PROCESSES.includes(process as any)) {
      errors.push(`Row ${i}: Invalid process "${process}" (must be Heating, Drying, Cure, or Cooling)`)
      continue
    }

    const proc = process as CureStep['process']
    const time = parseInt(cols[4])
    if (isNaN(time) || time < 1 || time > 120) {
      errors.push(`Row ${i}: Invalid time "${cols[4]}" (must be 1-120)`)
      continue
    }

    const step: CureStep = {
      step: parseInt(cols[0]) || i,
      process: proc,
      temperature: null,
      intensity: null,
      time,
    }

    // Temperature validation per process
    if (proc === 'Cooling') {
      const rate = cols[5] ? Number(cols[5]) : null
      if (rate !== null && (isNaN(rate) || rate < 1 || rate > 20)) {
        errors.push(`Row ${i}: Invalid cooling rate "${cols[5]}" (must be 1-20)`)
        continue
      }
      step.coolingRate = rate ?? 5
    } else {
      const temp = cols[2] ? Number(cols[2]) : null
      if (temp !== null && (isNaN(temp) || temp < 20 || temp > 80)) {
        errors.push(`Row ${i}: Invalid temperature "${cols[2]}" (must be 20-80)`)
        continue
      }
      step.temperature = temp ?? 40
    }

    // Intensity - for Cure and Bleacher
    if (proc === 'Cure' || proc === 'Bleacher') {
      const intensity = cols[3] ? Number(cols[3]) : null
      if (intensity !== null && (isNaN(intensity) || intensity < 0 || intensity > 100)) {
        errors.push(`Row ${i}: Invalid intensity "${cols[3]}" (must be 0-100)`)
        continue
      }
      step.intensity = intensity ?? 30

      // Optional extended fields
      const uvInt = cols[6] ? Number(cols[6]) : null
      if (uvInt !== null) {
        if (isNaN(uvInt) || uvInt < 0 || uvInt > 100) {
          errors.push(`Row ${i}: Invalid UV intensity "${cols[6]}" (must be 0-100)`)
          continue
        }
        step.uvIntensity = uvInt
      }

      const tm = cols[7] || ''
      if (tm && !VALID_TIMER_MODES.includes(tm as TimerMode)) {
        errors.push(`Row ${i}: Invalid timer mode "${tm}" (must be on-ramp or on-target)`)
        continue
      }
      if (tm) step.timerMode = tm as TimerMode

      const usm = cols[8] || ''
      if (usm && !VALID_UV_START.includes(usm as UvStartMode)) {
        errors.push(`Row ${i}: Invalid UV start mode "${usm}" (must be at-start, at-target, or at-ramp-percent)`)
        continue
      }
      if (usm) step.uvStartMode = usm as UvStartMode

      const rp = cols[9] ? Number(cols[9]) : null
      if (rp !== null && (isNaN(rp) || rp < 10 || rp > 100)) {
        errors.push(`Row ${i}: Invalid ramp percent "${cols[9]}" (must be 10-100)`)
        continue
      }
      if (rp !== null) step.uvRampPercent = rp
    } else if (proc !== 'Cooling') {
      // Heating/Drying should NOT have intensity
      if (cols[3] && Number(cols[3]) > 0) {
        errors.push(`Row ${i}: ${proc} should not have intensity`)
        continue
      }
    }

    steps.push(step)
  }

  if (steps.length === 0) {
    return { steps: null, errors: errors.length > 0 ? errors : ['No valid steps found'] }
  }

  return { steps, errors }
}

function downloadCsvFile(name: string, csvContent: string) {
  const blob = new Blob([csvContent], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function loadUserMaterials(): Material[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return []
}

async function loadPresets(): Promise<Material[]> {
  try {
    const res = await fetch('/materials/presets/index.json')
    if (!res.ok) return []

    const index: { name: string; file: string }[] = await res.json()
    const presets: Material[] = []

    for (const entry of index) {
      try {
        const csvRes = await fetch(`/materials/presets/${entry.file}`)
        if (!csvRes.ok) continue
        const csvContent = await csvRes.text()
        const result = parseCsv(csvContent)
        if (!result.steps) continue

        presets.push({
          id: `preset-${entry.name}`,
          name: entry.name,
          steps: result.steps,
          totalDuration: result.steps.reduce((sum, s) => sum + s.time, 0),
          csvContent,
          createdAt: '',
          isPreset: true,
        })
      } catch { /* skip */ }
    }

    return presets
  } catch {
    return []
  }
}

const MaterialContext = createContext<MaterialContextType | null>(null)

export function MaterialProvider({ children }: { children: ReactNode }) {
  const [materials, setMaterials] = useState<Material[]>([])
  const [selectedMaterialId, setSelectedMaterialId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const presets = await loadPresets()
      const userMaterials = loadUserMaterials()
      const all = [...presets, ...userMaterials]
      setMaterials(all)
      if (all.length > 0) setSelectedMaterialId(all[0].id)
      setIsLoading(false)
    }
    load()
  }, [])

  // Only save user materials (not presets)
  useEffect(() => {
    if (!isLoading) {
      const userOnly = materials.filter(m => !m.isPreset)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(userOnly))
    }
  }, [materials, isLoading])

  const addMaterial = useCallback((data: Omit<Material, 'id' | 'createdAt' | 'isPreset'>) => {
    const csvContent = data.csvContent || stepsToCsv(data.steps)
    const newMaterial: Material = {
      ...data,
      csvContent,
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      isPreset: false,
    }
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
    downloadCsvFile(data.name, csvContent)
  }, [])

  const addMaterialFromCsv = useCallback((fileName: string, csvContent: string): { success: boolean; errors: string[] } => {
    const result = parseCsv(csvContent)
    if (!result.steps || result.errors.length > 0) return { success: false, errors: result.errors }

    const name = fileName.replace(/\.csv$/i, '')
    const totalDuration = result.steps.reduce((sum, s) => sum + s.time, 0)

    const newMaterial: Material = {
      id: crypto.randomUUID(),
      name,
      steps: result.steps,
      totalDuration,
      csvContent,
      createdAt: new Date().toISOString(),
      isPreset: false,
    }
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
    return { success: true, errors: result.errors }
  }, [])

  const updateMaterial = useCallback((id: string, data: { name: string; steps: CureStep[]; totalDuration: number; csvContent: string }) => {
    const mat = materials.find(m => m.id === id)
    if (mat?.isPreset) return
    setMaterials(prev => prev.map(m => m.id === id ? { ...m, ...data } : m))
  }, [materials])

  const removeMaterial = useCallback((id: string) => {
    // Cannot remove presets
    const mat = materials.find(m => m.id === id)
    if (mat?.isPreset) return

    setMaterials(prev => prev.filter(m => m.id !== id))
    setSelectedMaterialId(prev => prev === id ? null : prev)
  }, [materials])

  const getMaterialCsv = useCallback((id: string) => {
    return materials.find(m => m.id === id)?.csvContent
  }, [materials])

  return (
    <MaterialContext.Provider value={{
      materials, addMaterial, updateMaterial, addMaterialFromCsv, removeMaterial,
      selectedMaterialId, setSelectedMaterialId, getMaterialCsv, isLoading
    }}>
      {children}
    </MaterialContext.Provider>
  )
}

export function useMaterials() {
  const ctx = useContext(MaterialContext)
  if (!ctx) throw new Error('useMaterials must be used within MaterialProvider')
  return ctx
}
