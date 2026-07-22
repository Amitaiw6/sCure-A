import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'

export type TimerMode = 'on-ramp' | 'on-target'
export type UvStartMode = 'at-start' | 'at-target'
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
  duplicateMaterial: (id: string) => Material | null
  removeMaterial: (id: string) => void
  favoriteIds: string[]
  toggleFavorite: (id: string) => void
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
      '',
      s.process === 'Cooling' ? (s.coolingMode ?? 'medium') : '',
    ].join(',')
  })
  return [header, ...rows].join('\n')
}

// CSV parsing — only used for user import
const VALID_PROCESSES = ['Heating', 'Drying', 'Cure', 'Cooling', 'Bleacher', 'Nitrogen'] as const
const VALID_TIMER_MODES: TimerMode[] = ['on-ramp', 'on-target']
const VALID_UV_START: UvStartMode[] = ['at-start', 'at-target']

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
      // Bleaching may run up to 12 hours (720 min); other processes cap at 120 min.
      const maxTime = proc === 'Bleacher' ? 720 : 120
      time = parseInt(cols[3])
      if (isNaN(time) || time < 1 || time > maxTime) {
        errors.push(`Row ${i}: Invalid time "${cols[3]}" (must be 1-${maxTime})`)
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

    // Temperature validation — hardware limits: the heater refuses targets
    // below 30°C (heating.target_min); cooling targets are 20-75°C.
    const temp = cols[2] ? Number(cols[2]) : null
    if (temp !== null) {
      const [tMin, tMax] = proc === 'Cooling' ? [20, 75] : [30, 80]
      if (isNaN(temp) || temp < tMin || temp > tMax) {
        errors.push(`Row ${i}: Invalid temperature "${cols[2]}" (must be ${tMin}-${tMax} for ${proc})`)
        continue
      }
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
    }

    // Cure/Bleacher extended fields
    if (proc === 'Cure' || proc === 'Bleacher') {
      const tm = cols[4] || ''
      if (tm && VALID_TIMER_MODES.includes(tm as TimerMode)) {
        step.timerMode = tm as TimerMode
      }

      // Hardware LED driver: below led_power.min_intensity (10%) the LEDs
      // stay dark, so anything under 10 is rejected here and by the backend.
      const uvInt = cols[5] ? Number(cols[5]) : null
      if (uvInt !== null) {
        if (isNaN(uvInt) || uvInt < 10 || uvInt > 100) {
          errors.push(`Row ${i}: Invalid UV intensity "${cols[5]}" (must be 10-100)`)
          continue
        }
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

    // After Nitrogen: only Cure or Bleaching is allowed
    if (prev?.process === 'Nitrogen') {
      if (s.process !== 'Cure' && s.process !== 'Bleacher') {
        errors.push(`Step ${s.step}: After nitrogen, only Cure or Bleaching is allowed`)
      }
    }

    // After the Cure/Bleaching that followed an N₂ purge: only Cooling is allowed
    if (prev && (prev.process === 'Cure' || prev.process === 'Bleacher')) {
      const prevPrev = i > 1 ? steps[i - 2] : null
      if (prevPrev?.process === 'Nitrogen' && s.process !== 'Cooling') {
        errors.push(`Step ${s.step}: After the Cure/Bleaching that follows N₂, only Cooling is allowed`)
      }
    }

    // Track N2 → must have a Cure/Bleacher after it, and a Cooling step to vent it
    if (s.process === 'Nitrogen') needsCoolingOrDrying = true
    if (needsCoolingOrDrying && s.process === 'Cooling') needsCoolingOrDrying = false

    // Temperature must go up (unless after Cooling)
    if (s.process !== 'Cooling' && s.process !== 'Nitrogen' && s.temperature != null) {
      if (lastTemp !== null && s.temperature < lastTemp) {
        errors.push(`Step ${s.step}: Temperature (${s.temperature}°C) cannot be lower than previous (${lastTemp}°C) without a Cooling step`)
      }
      lastTemp = s.temperature
    }
    // Cooling target must actually be below the temperature it cools from
    // (same rule as the step editor: at least 5°C below the previous step),
    // otherwise the hardware cooling loop terminates immediately as a no-op.
    if (s.process === 'Cooling') {
      if (lastTemp !== null && s.temperature != null && s.temperature > lastTemp - 5) {
        errors.push(`Step ${s.step}: Cooling target (${s.temperature}°C) must be at least 5°C below the previous step (${lastTemp}°C)`)
      }
      lastTemp = null
    }
  }

  if (needsCoolingOrDrying) {
    errors.push('Nitrogen must be vented — add a Cooling step after the N₂ purge')
  }

  // If program has N₂, must have at least one Cure/Bleacher after it
  const hasNitrogen = steps.some(s => s.process === 'Nitrogen')
  if (hasNitrogen) {
    let foundProcessAfterN2 = false
    let afterN2 = false
    for (const s of steps) {
      if (s.process === 'Nitrogen') afterN2 = true
      if (afterN2 && (s.process === 'Cure' || s.process === 'Bleacher')) { foundProcessAfterN2 = true; break }
    }
    if (!foundProcessAfterN2) {
      errors.push('Add a Cure or Bleaching step after N₂ purge')
    }
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

// Material programs are managed in PostgreSQL and read via the backend API.
// When the backend is unreachable (dev / offline), fall back to a bundled demo set.
import { DEMO_PRESETS, DEMO_USER_PROGRAMS } from '@/data/demo-data'

async function loadUserMaterials(): Promise<Material[]> {
  try {
    const res = await fetch(`${API_BASE}/api/materials/user`)
    if (res.ok) return await res.json()
  } catch { /* backend not available */ }
  return DEMO_USER_PROGRAMS
}

async function saveUserMaterials(materials: Material[]) {
  try {
    await fetch(`${API_BASE}/api/materials/user`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(materials),
    })
  } catch { /* backend not available */ }
}

async function loadPresets(): Promise<Material[]> {
  try {
    const res = await fetch(`${API_BASE}/api/materials/presets`)
    if (res.ok) return await res.json()
  } catch { /* backend not available */ }
  return DEMO_PRESETS
}

const MaterialContext = createContext<MaterialContextType | null>(null)

export function MaterialProvider({ children }: { children: ReactNode }) {
  const [materials, setMaterials] = useState<Material[]>([])
  const [selectedMaterialId, setSelectedMaterialId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [favoriteIds, setFavoriteIds] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem('scure-favorite-materials')
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  })

  // Persist favorites locally (works for presets and user materials alike)
  useEffect(() => {
    localStorage.setItem('scure-favorite-materials', JSON.stringify(favoriteIds))
  }, [favoriteIds])

  const toggleFavorite = useCallback((id: string) => {
    setFavoriteIds(prev => prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id])
  }, [])

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

  const duplicateMaterial = useCallback((id: string): Material | null => {
    const mat = materials.find(m => m.id === id)
    if (!mat) return null

    // Build a unique "<name> Copy" name (Copy, Copy 2, Copy 3, ...)
    const existingNames = materials.map(m => m.name)
    let copyName = `${mat.name} Copy`
    let n = 2
    while (existingNames.includes(copyName)) {
      copyName = `${mat.name} Copy ${n}`
      n++
    }

    const newMaterial: Material = {
      id: crypto.randomUUID(),
      name: copyName,
      steps: mat.steps.map(s => ({ ...s })),
      totalDuration: mat.totalDuration,
      createdAt: new Date().toISOString(),
      isPreset: false, // a copy is always an editable user material
    }

    // Append to the end, alongside newly created user materials
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
    return newMaterial
  }, [materials])

  const removeMaterial = useCallback((id: string) => {
    const mat = materials.find(m => m.id === id)
    if (mat?.isPreset) return
    setMaterials(prev => prev.filter(m => m.id !== id))
    setSelectedMaterialId(prev => prev === id ? null : prev)
    setFavoriteIds(prev => prev.filter(f => f !== id))
  }, [materials])

  const exportMaterialCsv = useCallback((id: string) => {
    const mat = materials.find(m => m.id === id)
    if (!mat) return
    const csv = stepsToCsv(mat.steps)
    downloadCsvFile(mat.name, csv)
  }, [materials])

  return (
    <MaterialContext.Provider value={{
      materials, addMaterial, updateMaterial, addMaterialFromCsv, duplicateMaterial, removeMaterial,
      favoriteIds, toggleFavorite,
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
