import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, AlertTriangle, ChevronRight, Play, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useMaterials } from '@/context/MaterialContext'
import { cn } from '@/lib/utils'
import type { PrintLog } from '@/context/PrintHistoryContext'

interface PrintHistoryModalProps {
  isOpen: boolean
  onClose: () => void
}

function StatusIcon({ status }: { status: PrintLog['status'] }) {
  switch (status) {
    case 'completed': return <CheckCircle size={16} className="text-green-500 shrink-0" />
    case 'aborted': return <AlertTriangle size={16} className="text-yellow-500 shrink-0" />
    case 'error': return <XCircle size={16} className="text-destructive shrink-0" />
  }
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export default function PrintHistoryModal({ isOpen, onClose }: PrintHistoryModalProps) {
  const navigate = useNavigate()
  const { logs } = usePrintHistory()
  const { materials, setSelectedMaterialId } = useMaterials()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const selectedLogs = logs.filter(l => selectedIds.has(l.id))
  const allSameMaterial = selectedLogs.length >= 2 &&
    selectedLogs.every(l => l.materialName === selectedLogs[0].materialName)
  const canCure = selectedLogs.length >= 1 && (selectedLogs.length === 1 || allSameMaterial)

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleCure = () => {
    if (!canCure) return
    const mat = materials.find(m => m.name === selectedLogs[0].materialName)
    if (mat) setSelectedMaterialId(mat.id)
    // Store selected IDs to remove after cure completes
    sessionStorage.setItem('scure-pending-cure-logs', JSON.stringify([...selectedIds]))
    setSelectedIds(new Set())
    onClose()
    navigate('/cure-process')
  }

  const handleClose = () => {
    setSelectedIds(new Set())
    onClose()
  }

  const handleSelectMaterial = (materialName: string) => {
    if (selectedIds.size > 0) return
    const mat = materials.find(m => m.name === materialName)
    if (mat) {
      setSelectedMaterialId(mat.id)
      onClose()
    }
  }

  // Validation message
  const getSelectionMessage = () => {
    if (selectedLogs.length === 0) return null
    if (selectedLogs.length >= 2 && !allSameMaterial) return '⚠ Cannot cure different materials together!'
    if (selectedLogs.length === 1) return `Ready to cure ${selectedLogs[0].materialName}`
    return `Ready to cure ${selectedLogs.length}× ${selectedLogs[0].materialName}`
  }

  const selectionMsg = getSelectionMessage()

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[90vw] max-h-[85vh] p-4" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-base">
            Print History ({logs.length})
            {selectedIds.size > 0 && (
              <span className="text-xs text-muted-foreground font-normal ml-2">
                — {selectedIds.size} selected
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        {/* Selection message */}
        {selectionMsg && (
          <div className={cn(
            'text-xs px-3 py-2 rounded-lg',
            canCure ? 'bg-green-500/10 text-green-400' : !allSameMaterial && selectedLogs.length >= 2 ? 'bg-destructive/10 text-destructive' : 'bg-secondary text-muted-foreground'
          )}>
            {selectionMsg}
          </div>
        )}

        <div className="overflow-y-auto scroll-hidden max-h-[55vh] space-y-1.5">
          {logs.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">No print history yet.</p>
          ) : (
            logs.map(log => {
              const hasMaterial = materials.some(m => m.name === log.materialName)
              const isSelected = selectedIds.has(log.id)

              return (
                <div
                  key={log.id}
                  className={cn(
                    'flex items-center gap-3 rounded-xl px-4 py-3 transition-colors',
                    isSelected
                      ? 'bg-primary/10 border border-primary/40'
                      : 'bg-card border border-transparent hover:bg-accent',
                    'cursor-pointer'
                  )}
                  onClick={() => {
                    if (selectedIds.size > 0 || isSelected) {
                      toggleSelect(log.id)
                    } else {
                      handleSelectMaterial(log.materialName)
                    }
                  }}
                  onContextMenu={e => { e.preventDefault(); toggleSelect(log.id) }}
                >
                  {/* Selection checkbox */}
                  <div
                    className={cn(
                      'w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0 touch-manipulation',
                      isSelected ? 'bg-primary border-primary' : 'border-border'
                    )}
                    onClick={e => { e.stopPropagation(); toggleSelect(log.id) }}
                  >
                    {isSelected && <Check size={14} className="text-primary-foreground" />}
                  </div>

                  <StatusIcon status={log.status} />
                  <div className="flex-1 min-w-0">
                    <span className="text-foreground text-sm font-medium block truncate">{log.printName}</span>
                    <span className="text-muted-foreground text-xs block truncate">{log.materialName}</span>
                  </div>
                  <span className="text-muted-foreground text-xs shrink-0">{formatDate(log.date)}</span>
                  <span className="text-cyan-400 text-xs shrink-0">{log.duration} min</span>
                  <span className="text-muted-foreground/50 text-[10px] shrink-0">{log.printerName}</span>
                  {!isSelected && hasMaterial && selectedIds.size === 0 && (
                    <ChevronRight size={14} className="text-muted-foreground shrink-0" />
                  )}
                </div>
              )
            })
          )}
        </div>

        <DialogFooter className="flex-row gap-3">
          {selectedIds.size > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
              className="text-xs"
            >
              Clear Selection
            </Button>
          )}
          <div className="flex-1" />
          <Button variant="outline" onClick={handleClose} className="min-w-[80px] text-xs">Close</Button>
          {canCure && (
            <Button onClick={handleCure} className="gap-1 min-w-[120px] text-xs">
              <Play size={14} fill="currentColor" />
              Cure Together
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
