import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MaterialItem from '@/components/MaterialItem'
import CsvBuilderModal from '@/components/CsvBuilderModal'
import ImportCsvModal from '@/components/ImportCsvModal'
import PrintHistoryModal from '@/components/PrintHistoryModal'
import { Button } from '@/components/ui/button'
import { Play, Upload, Trash2, Pencil, ChevronRight, CheckCircle, XCircle, AlertTriangle, Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useMaterials } from '@/context/MaterialContext'
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useSystemConfig } from '@/context/SystemConfigContext'
import { useHardware } from '@/context/HardwareContext'
import type { Material } from '@/context/MaterialContext'
import type { PrintLog } from '@/context/PrintHistoryContext'

function SmallStatusIcon({ status }: { status: PrintLog['status'] }) {
  switch (status) {
    case 'completed': return <CheckCircle size={14} className="text-green-500 shrink-0" />
    case 'aborted': return <AlertTriangle size={14} className="text-yellow-500 shrink-0" />
    case 'error': return <XCircle size={14} className="text-destructive shrink-0" />
  }
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function HomePage() {
  const navigate = useNavigate()
  const { materials, selectedMaterialId, setSelectedMaterialId, removeMaterial, isLoading } = useMaterials()
  const { recentLogs } = usePrintHistory()
  const { config } = useSystemConfig()
  const { state: hw } = useHardware()
  const hasOrg = !!config.organizationId
  const [showBuilder, setShowBuilder] = useState(false)
  const [n2Error, setN2Error] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editingMaterial, setEditingMaterial] = useState<Material | null>(null)
  const [selectedPrintId, setSelectedPrintId] = useState<string | null>(null)

  const handleEdit = (mat: Material) => {
    setEditingMaterial(mat)
    setShowBuilder(true)
  }

  const handleCloseBuilder = () => {
    setShowBuilder(false)
    setEditingMaterial(null)
  }

  // Resolve material from print selection or direct selection
  const selectedPrint = recentLogs.find(l => l.id === selectedPrintId)
  const materialFromPrint = selectedPrint ? materials.find(m => m.name === selectedPrint.materialName) : null
  const activeMaterialId = selectedMaterialId ?? materialFromPrint?.id ?? null

  const handleStartCure = () => {
    const mat = materials.find(m => m.id === activeMaterialId)
    if (!mat) return
    // If all non-nitrogen steps would be empty after filtering, can't run
    const nonN2Steps = mat.steps.filter(s => s.process !== 'Nitrogen')
    if (nonN2Steps.length === 0 && !hw.nitrogenMode) {
      setN2Error(true)
      return
    }
    // Ensure the material is selected in context before navigating
    if (activeMaterialId !== selectedMaterialId) {
      setSelectedMaterialId(activeMaterialId)
    }
    navigate('/cure-process')
  }

  return (
    <main className="px-4 pb-16 relative">
      {/* Recent Prints Section */}
      <div className="flex items-center justify-between mb-3 mt-4">
        <h2 className="text-white text-base font-semibold">Recent Prints</h2>
        {hasOrg && (
          <Button variant="ghost" size="sm" onClick={() => setShowHistory(true)} className="gap-1 text-xs text-muted-foreground">
            View All <ChevronRight size={14} />
          </Button>
        )}
      </div>

      {!hasOrg ? (
        <div className="bg-card rounded-xl px-4 py-4 flex items-center gap-3">
          <Building2 size={18} className="text-muted-foreground/50 shrink-0" />
          <div>
            <p className="text-muted-foreground text-sm">No organization</p>
            <p className="text-muted-foreground/50 text-[10px]">Connect to an organization in Settings to view print history</p>
          </div>
        </div>
      ) : recentLogs.length === 0 ? (
        <p className="text-muted-foreground text-sm py-3">No prints yet.</p>
      ) : (
        <div className="space-y-1.5">
          {recentLogs.map(log => {
            const matchingMaterial = materials.find(m => m.name === log.materialName)
            return (
              <div key={log.id} className={cn(
                  'flex items-center gap-3 rounded-xl px-4 py-2.5 cursor-pointer transition-colors',
                  selectedPrintId === log.id ? 'bg-primary/10 border border-primary/40' : 'bg-card border border-transparent hover:bg-accent'
                )}
                onClick={() => {
                  if (selectedPrintId === log.id) {
                    setSelectedPrintId(null)
                  } else {
                    setSelectedPrintId(log.id)
                    setSelectedMaterialId(null)
                  }
                }}
              >
                <SmallStatusIcon status={log.status} />
                <div className="flex-1 min-w-0">
                  <span className="text-foreground text-sm font-medium block truncate">{log.printName}</span>
                  <span className="text-muted-foreground text-xs block truncate">{log.materialName}</span>
                </div>
                <span className="text-cyan-400 text-xs shrink-0">{log.duration}min</span>
                <span className="text-muted-foreground text-xs shrink-0">{timeAgo(log.date)}</span>
                <span className="text-muted-foreground/50 text-[10px] shrink-0">{log.printerName}</span>
                <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              </div>
            )
          })}
        </div>
      )}

      {/* Material List Section */}
      <div className="flex items-center justify-between mb-3 mt-5">
        <h2 className="text-white text-base font-semibold">
          Material List
          <span className="text-muted-foreground text-xs font-normal ml-2">({materials.length})</span>
        </h2>
        <div className="flex items-center gap-2">
          {materials.length > 0 && (
            <Button
              variant={editMode ? 'destructive' : 'ghost'}
              size="sm"
              onClick={() => setEditMode(!editMode)}
              className="text-xs"
            >
              {editMode ? 'Done' : 'Edit'}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setShowImport(true)} className="gap-1 text-xs">
            <Upload size={14} />
            CSV
          </Button>
          <Button size="sm" onClick={() => { setEditingMaterial(null); setShowBuilder(true) }} className="gap-1 text-xs">
            + New
          </Button>
        </div>
      </div>

      {/* Material list */}
      {isLoading ? (
        <p className="text-muted-foreground text-sm text-center py-8">Loading materials...</p>
      ) : materials.length === 0 ? (
        <p className="text-muted-foreground text-sm text-center py-8">
          No materials yet. Upload a CSV or create a new program.
        </p>
      ) : (
        materials.map(mat => (
          <div key={mat.id} className="flex items-center gap-2">
            <div className="flex-1">
              <MaterialItem
                label={mat.name}
                duration={`${mat.totalDuration}min`}
                isSelected={selectedMaterialId === mat.id}
                isPreset={mat.isPreset}
                onClick={() => { setSelectedMaterialId(mat.id); setSelectedPrintId(null) }}
              />
            </div>
            {editMode && !mat.isPreset && (
              <>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => handleEdit(mat)}
                  className="shrink-0 mb-2"
                >
                  <Pencil size={16} className="text-primary" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => removeMaterial(mat.id)}
                  className="shrink-0 mb-2"
                >
                  <Trash2 size={16} className="text-destructive" />
                </Button>
              </>
            )}
          </div>
        ))
      )}

      {/* Start Cure Button */}
      <div className="fixed bottom-4 right-4">
        <Button onClick={handleStartCure} disabled={!activeMaterialId} className="gap-2 rounded-xl px-5 py-2.5 text-sm">
          Start Cure
          <Play size={16} fill="currentColor" />
        </Button>
      </div>

      {/* Modals */}
      <CsvBuilderModal isOpen={showBuilder} onClose={handleCloseBuilder} editMaterial={editingMaterial} />
      <ImportCsvModal isOpen={showImport} onClose={() => setShowImport(false)} />
      <PrintHistoryModal isOpen={showHistory} onClose={() => setShowHistory(false)} />

      {/* N2 Error Dialog */}
      {n2Error && (
        <div className="fixed inset-0 z-50 bg-background/95 flex flex-col items-center justify-center gap-5">
          <div className="w-20 h-20 rounded-full bg-destructive/20 flex items-center justify-center">
            <AlertTriangle size={48} className="text-destructive" />
          </div>
          <h2 className="text-foreground text-xl font-bold">Cannot Start Program</h2>
          <p className="text-muted-foreground text-sm text-center max-w-xs">
            This program contains only nitrogen purge steps, but nitrogen is not enabled on the system.
          </p>
          <p className="text-muted-foreground text-xs text-center max-w-xs">
            Enable nitrogen in Settings or choose a different program.
          </p>
          <button
            onClick={() => setN2Error(false)}
            className="bg-primary text-primary-foreground px-6 py-3 rounded-2xl font-semibold active:scale-95 transition-transform touch-manipulation mt-2"
          >
            OK
          </button>
        </div>
      )}
    </main>
  )
}
