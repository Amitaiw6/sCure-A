import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'

export interface CureStep {
  step: number
  process: 'Heating' | 'Drying' | 'Cure' | 'Cooling'
  temperature: number | null
  intensity: number | null
  time: number
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
  addMaterialFromCsv: (fileName: string, csvContent: string) => boolean
  removeMaterial: (id: string) => void
  selectedMaterialId: string | null
  setSelectedMaterialId: (id: string | null) => void
  getMaterialCsv: (id: string) => string | undefined
  isLoading: boolean
}

const STORAGE_KEY = 'scure-materials'

function stepsToCsv(steps: CureStep[]): string {
  const header = 'Step,Process,Temperature,Intensity,Time'
  const rows = steps.map(s =>
    `${s.step},${s.process},${s.temperature ?? ''},${s.intensity ?? ''},${s.time}`
  )
  return [header, ...rows].join('\n')
}

function parseCsv(csvContent: string): CureStep[] | null {
  const lines = csvContent.trim().split('\n')
  if (lines.length < 2) return null

  const header = lines[0].toLowerCase()
  if (!header.includes('process') && !header.includes('step')) return null

  const steps: CureStep[] = []
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',').map(c => c.trim())
    if (cols.length < 3) continue

    const process = cols[1] as CureStep['process']
    if (!['Heating', 'Drying', 'Cure', 'Cooling'].includes(process)) continue

    const rawTemp = cols[2] ? Number(cols[2]) : null
    const clampedTemp = rawTemp !== null ? Math.min(80, Math.max(20, rawTemp)) : null

    steps.push({
      step: parseInt(cols[0]) || i,
      process,
      temperature: clampedTemp,
      intensity: cols[3] ? Math.min(100, Math.max(0, Number(cols[3]))) : null,
      time: Math.min(120, Math.max(1, parseInt(cols[4]) || 10)),
    })
  }

  return steps.length > 0 ? steps : null
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
        const steps = parseCsv(csvContent)
        if (!steps) continue

        presets.push({
          id: `preset-${entry.name}`,
          name: entry.name,
          steps,
          totalDuration: steps.reduce((sum, s) => sum + s.time, 0),
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

  const addMaterialFromCsv = useCallback((fileName: string, csvContent: string): boolean => {
    const steps = parseCsv(csvContent)
    if (!steps) return false

    const name = fileName.replace(/\.csv$/i, '')
    const totalDuration = steps.reduce((sum, s) => sum + s.time, 0)

    const newMaterial: Material = {
      id: crypto.randomUUID(),
      name,
      steps,
      totalDuration,
      csvContent,
      createdAt: new Date().toISOString(),
      isPreset: false,
    }
    setMaterials(prev => [...prev, newMaterial])
    setSelectedMaterialId(newMaterial.id)
    return true
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
