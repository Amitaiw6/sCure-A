import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, AlertTriangle, ChevronRight, Play, Check, Filter, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
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
import { usePrintHistory } from '@/context/PrintHistoryContext'
import { useMaterials } from '@/context/MaterialContext'
import { useSystemConfig } from '@/context/SystemConfigContext'
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
  const { config } = useSystemConfig()
  const hasOrg = !!config.organizationId
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showFilters, setShowFilters] = useState(false)
  const [filterMaterial, setFilterMaterial] = useState<string>('all')
  const [filterPrinter, setFilterPrinter] = useState<string>('all')
  const [filterDateFrom, setFilterDateFrom] = useState<string>('')
  const [filterDateTo, setFilterDateTo] = useState<string>('')

  // Unique values for filter dropdowns
  const uniqueMaterials = useMemo(() => [...new Set(logs.map(l => l.materialName))].sort(), [logs])
  const uniquePrinters = useMemo(() => [...new Set(logs.map(l => l.printerName))].sort(), [logs])

  // Filtered logs
  const filteredLogs = useMemo(() => {
    return logs.filter(l => {
      if (filterMaterial !== 'all' && l.materialName !== filterMaterial) return false
      if (filterPrinter !== 'all' && l.printerName !== filterPrinter) return false
      if (filterDateFrom) {
        const from = new Date(filterDateFrom)
        if (new Date(l.date) < from) return false
      }
      if (filterDateTo) {
        const to = new Date(filterDateTo + 'T23:59:59')
        if (new Date(l.date) > to) return false
      }
      return true
    })
  }, [logs, filterMaterial, filterPrinter, filterDateFrom, filterDateTo])

  const activeFilterCount = [
    filterMaterial !== 'all',
    filterPrinter !== 'all',
    !!filterDateFrom,
    !!filterDateTo,
  ].filter(Boolean).length

  const clearFilters = () => {
    setFilterMaterial('all')
    setFilterPrinter('all')
    setFilterDateFrom('')
    setFilterDateTo('')
  }

  const selectedLogs = filteredLogs.filter(l => selectedIds.has(l.id))
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
          <div className="flex items-center justify-between">
            <DialogTitle className="text-base">
              Print History ({filteredLogs.length}{filteredLogs.length !== logs.length ? `/${logs.length}` : ''})
              {selectedIds.size > 0 && (
                <span className="text-xs text-muted-foreground font-normal ml-2">
                  — {selectedIds.size} selected
                </span>
              )}
            </DialogTitle>
            <Button
              variant={showFilters ? 'default' : 'outline'}
              size="sm"
              className="text-xs h-7 gap-1"
              onClick={() => setShowFilters(!showFilters)}
            >
              <Filter size={12} />
              Filters
              {activeFilterCount > 0 && (
                <span className="bg-primary-foreground text-primary w-4 h-4 rounded-full text-[10px] flex items-center justify-center font-bold">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </div>
        </DialogHeader>

        {/* Filters */}
        {showFilters && (
          <div className="flex items-center gap-2 flex-wrap bg-secondary/50 rounded-lg p-2">
            <Select value={filterMaterial} onValueChange={setFilterMaterial}>
              <SelectTrigger className="w-[140px] h-8 text-xs">
                <SelectValue placeholder="Material" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Materials</SelectItem>
                {uniqueMaterials.map(m => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={filterPrinter} onValueChange={setFilterPrinter}>
              <SelectTrigger className="w-[140px] h-8 text-xs">
                <SelectValue placeholder="Printer" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Printers</SelectItem>
                {uniquePrinters.map(p => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="flex items-center gap-1">
              <span className="text-muted-foreground text-[10px]">From:</span>
              <input
                type="date"
                value={filterDateFrom}
                onChange={e => setFilterDateFrom(e.target.value)}
                className="bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground h-8 touch-manipulation"
              />
            </div>

            <div className="flex items-center gap-1">
              <span className="text-muted-foreground text-[10px]">To:</span>
              <input
                type="date"
                value={filterDateTo}
                onChange={e => setFilterDateTo(e.target.value)}
                className="bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground h-8 touch-manipulation"
              />
            </div>

            {activeFilterCount > 0 && (
              <Button variant="ghost" size="sm" className="text-xs h-7 gap-1 text-muted-foreground" onClick={clearFilters}>
                <X size={12} /> Clear
              </Button>
            )}
          </div>
        )}

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
          {filteredLogs.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">
              {logs.length === 0 ? 'No print history yet.' : 'No results match the filters.'}
            </p>
          ) : (
            filteredLogs.map(log => {
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
                  {hasOrg && <span className="text-muted-foreground/50 text-sm shrink-0">{log.printerName}</span>}
                  <ChevronRight size={14} className="text-muted-foreground shrink-0" />
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
