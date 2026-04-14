import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'

export type TimerMode = 'on-ramp' | 'on-target'
export type UvStartMode = 'at-start' | 'at-target' | 'at-ramp-percent'
export type CoolingMode = 'fast' | 'medium' | 'slow'

export interface CureStep {
  step: number
  process: 'Heating' | 'Drying' | 'Cure' | 'Cooling' | 'Bleacher' | 'Nitrogen'
  temperature: number | null
  intensity: number | null
  time: number
  uvIntensity?: number | null
  timerMode?: TimerMode
  uvStartMode?: UvStartMode
  uvRampPercent?: number
  coolingMode?: CoolingMode
}

export interface Material {
  id: string
  name: string
  steps: CureStep[]
  totalDuration: number
  createdAt: string
  isPreset: boolean
}

interface MaterialContextType {
  materials: Material[]
  addMaterial: (material: Omit<Material, 'id' | 'createdAt' | 'isPreset'>) => void
  updateMaterial: (id: string, data: { name: string; steps: CureStep[]; totalDuration: number }) => void
  addMaterialFromCsv: (fileName: string, csvContent: string) => { success: boolean; errors: string[] }
  removeMaterial: (id: string) => void
  selectedMaterialId: string | null
  setSelectedMaterialId: (id: string | null) => void
  exportMaterialCsv: (id: string) => void
  isLoading: boolean
}

const API_BASE = 'http://localhost:3001'

// CSV generation — only used for user export/download
export function stepsToCsv(steps: CureStep[]): string {
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

// CSV parsing — only used for user import
const VALID_PROCESSES = ['Heating', 'Drying', 'Cure', 'Cooling', 'Bleacher', 'Nitrogen'] as const
const VALID_TIMER_MODES: TimerMode[] = ['on-ramp', 'on-target']
const VALID_UV_START: UvStartMode[] = ['at-start', 'at-target', 'at-ramp-percent']

export interface CsvParseResult {
  steps: CureStep[] | null
  errors: string[]
}

export function parseCsv(csvContent: string): CsvParseResult {
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
    if (cols.length < 4) {
      errors.push(`Row ${i}: Not enough columns (need at least 4)`)
      continue
    }

    const process = cols[1]
    if (!VALID_PROCESSES.includes(process as any)) {
      errors.push(`Row ${i}: Invalid process "${process}" (must be Heating, Drying, Cure, Cooling or Bleacher)`)
      continue
    }

    const proc = process as CureStep['process']

    // Nitrogen and Cooling don't need time
    let time = 0
    if (proc !== 'Cooling' && proc !== 'Nitrogen') {
      time = parseInt(cols[3])
      if (isNaN(time) || time < 1 || time > 120) {
        errors.push(`Row ${i}: Invalid time "${cols[3]}" (must be 1-120)`)
        continue
      }
    }

    const step: CureStep = {
      step: parseInt(cols[0]) || i,
      process: proc,
      temperature: null,
      intensity: null,
      time,
    }

    // Nitrogen has no temperature
    if (proc === 'Nitrogen') {
      steps.push(step)
      continue
    }

    // Temperature validation
    const temp = cols[2] ? Number(cols[2]) : null
    if (temp !== null && (isNaN(temp) || temp < 20 || temp > 80)) {
      errors.push(`Row ${i}: Invalid temperature "${cols[2]}" (must be 20-80)`)
      continue
    }
    step.temperature = temp ?? (proc === 'Cooling' ? 25 : 40)

    if (proc === 'Cooling') {
      const cm = cols[8] || ''
      const validModes: CoolingMode[] = ['fast', 'medium', 'slow']
      if (cm && validModes.includes(cm as CoolingMode)) {
        step.coolingMode = cm as CoolingMode
      } else {
        step.coolingMode = 'medium'
      }
    } else {
    }

    // Cure/Bleacher extended fields
    if (proc === 'Cure' || proc === 'Bleacher') {
      const tm = cols[4] || ''
      if (tm && VALID_TIMER_MODES.includes(tm as TimerMode)) {
        step.timerMode = tm as TimerMode
      }

      const uvInt = cols[5] ? Number(cols[5]) : null
      if (uvInt !== null && !isNaN(uvInt) && uvInt >= 0 && uvInt <= 100) {
        step.uvIntensity = uvInt
      }

      const usm = cols[6] || ''
      if (usm && VALID_UV_START.includes(usm as UvStartMode)) {
        step.uvStartMode = usm as UvStartMode
      }

      const rp = cols[7] ? Number(cols[7]) : null
      if (rp !== null && !isNaN(rp) && rp >= 10 && rp <= 100) {
        step.uvRampPercent = rp
      }
    }

    steps.push(step)
  }

  if (steps.length === 0) {
    return { steps: null, errors: errors.length > 0 ? errors : ['No valid steps found'] }
  }

  // Validate step sequence rules
  let n2Count = 0
  let needsCoolingOrDrying = false
  let lastTemp: number | null = null

  for (let i = 0; i < steps.length; i++) {
    const s = steps[i]
    const prev = i > 0 ? steps[i - 1] : null

    // Max 2 Nitrogen steps
    if (s.process === 'Nitrogen') {
      n2Count++
      if (n2Count > 2) {
        errors.push(`Step ${s.step}: Maximum 2 nitrogen purge steps allowed`)
      }
    }

    // Nitrogen only after Cooling (except first step)
    if (s.process === 'Nitrogen' && prev && prev.process !== 'Cooling') {
      // Check if there was a cooling since last N2
      let hadCooling = false
      for (let j = i - 1; j >= 0; j--) {
        if (steps[j].process === 'Cooling') { hadCooling = true; break }
        if (steps[j].process === 'Nitrogen') break
      }
      if (!hadCooling && prev) {
        errors.push(`Step ${s.step}: Nitrogen purge requires a Cooling step before it`)
      }
    }

    // After Nitrogen: only Heating, Cure, or Bleacher
    if (prev?.process === 'Nitrogen') {
      if (s.process === 'Cooling' || s.process === 'Drying' || s.process === 'Nitrogen') {
        errors.push(`Step ${s.step}: After nitrogen, only Heating, Cure, or Bleacher is allowed`)
      }
    }

    // Track N2 → must have Cooling/Drying before end
    if (s.process === 'Nitrogen') needsCoolingOrDrying = true
    if (needsCoolingOrDrying && (s.process === 'Cooling' || s.process === 'Drying')) needsCoolingOrDrying = false

    // Temperature must go up (unless after Cooling)
    if (s.process !== 'Cooling' && s.process !== 'Nitrogen' && s.temperature != null) {
      if (lastTemp !== null && s.temperature < lastTemp) {
        errors.push(`Step ${s.step}: Temperature (${s.temperature}°C) cannot be lower than previous (${lastTemp}°C) without a Cooling step`)
      }
      lastTemp = s.temperature
    }
    if (s.process === 'Cooling') lastTemp = null
  }

  if (needsCoolingOrDrying) {
    errors.push('After nitrogen purge, a Cooling or Drying step is required before the end of the program')
  }

  if (errors.length > 0) {
    return { steps: null, errors }
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

async function loadUserMaterials(): Promise<Material[]> {
  try {
    const res = await fetch(`${API_BASE}/api/materials/user`)
    if (res.ok) return await res.json()
  } catch { /* API not available */ }
  // Fallback: load from static file (dev mode)
  try {
    const res = await fetch('/materials/user_materials.json')
    if (res.ok) return await res.json()
  } catch { /* ignore */ }
  return []
}

async function saveUserMaterials(materials: Material[]) {
  try {
    await fetch(`${API_BASE}/api/materials/user`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(materials),
    })
  } catch { /* API not available in dev mode */ }
}

async function loadPresets(): Promise<Material[]> {
  try {
    const res = await fetch('/materials/presets/presets.json')
    if (!res.ok) return []

    const data: { name: string; steps: CureStep[] }[] = await res.json()
    return data.map(entry => ({
      id: `preset-${entry.name}`,
      name: entry.name,
      steps: entry.steps,
      totalDuration: entry.steps.reduce((sum, s) => sum + (s.time || 0), 0),
      createdAt: '',
      isPreset: true,
    }))
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
      const [presets, userMaterials] = await Promise.all([loadPresets(), loadUserMaterials()])
      const all = [...presets, ...userMaterials]
      setMaterials(all)
      if (all.length > 0) setSelectedMaterialId(all[0].id)
      setIsLoading(false)
    }
    load()
  }, [])

  // Save user materials to server JSON file
  const saveRef = useRef(false)
  useEffect(() => {
    if (!isLoading) {
      if (!saveRef.current) { saveRef.current = true; return } // skip initial
      const userOnly = materials.filter(m => !m.isPreset)
      saveUserMaterials(userOnly)
    }
  }, [materials, isLoading])

  const addMaterial = useCallback((data: Omit<Material, 'id' | 'createdAt' | 'isPreset'>) => {
    const newMaterial: Material = {
      ...data,
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      isPreset: false,
    }
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
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
      createdAt: new Date().toISOString(),
      isPreset: false,
    }
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
    return { success: true, errors: result.errors }
  }, [])

  const updateMaterial = useCallback((id: string, data: { name: string; steps: CureStep[]; totalDuration: number }) => {
    const mat = materials.find(m => m.id === id)
    if (mat?.isPreset) return
    setMaterials(prev => prev.map(m => m.id === id ? { ...m, ...data } : m))
  }, [materials])

  const removeMaterial = useCallback((id: string) => {
    const mat = materials.find(m => m.id === id)
    if (mat?.isPreset) return
    setMaterials(prev => prev.filter(m => m.id !== id))
    setSelectedMaterialId(prev => prev === id ? null : prev)
  }, [materials])

  const exportMaterialCsv = useCallback((id: string) => {
    const mat = materials.find(m => m.id === id)
    if (!mat) return
    const csv = stepsToCsv(mat.steps)
    downloadCsvFile(mat.name, csv)
  }, [materials])

  return (
    <MaterialContext.Provider value={{
      materials, addMaterial, updateMaterial, addMaterialFromCsv, removeMaterial,
      selectedMaterialId, setSelectedMaterialId, exportMaterialCsv, isLoading
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
