import { useState } from 'react'
import { Folder, CheckCircle, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { useMaterials } from '@/context/MaterialContext'

interface ImportCsvModalProps {
  isOpen: boolean
  onClose: () => void
}

interface ImportResult {
  name: string
  success: boolean
}

export default function ImportCsvModal({ isOpen, onClose }: ImportCsvModalProps) {
  const { addMaterialFromCsv } = useMaterials()
  const [results, setResults] = useState<ImportResult[]>([])

  const openFilePicker = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.csv'
    input.multiple = true
    input.onchange = (e) => {
      const files = (e.target as HTMLInputElement).files
      if (!files || files.length === 0) return
      setResults([])
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        const reader = new FileReader()
        reader.onload = (event) => {
          const csvContent = event.target?.result as string
          const success = addMaterialFromCsv(file.name, csvContent)
          setResults(prev => [...prev, { name: file.name, success }])
        }
        reader.readAsText(file)
      }
    }
    input.click()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const files = e.dataTransfer.files
    if (files.length === 0) return
    setResults([])
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const reader = new FileReader()
      reader.onload = (event) => {
        const csvContent = event.target?.result as string
        const success = addMaterialFromCsv(file.name, csvContent)
        setResults(prev => [...prev, { name: file.name, success }])
      }
      reader.readAsText(file)
    }
  }

  const handleClose = () => {
    setResults([])
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[90vw] max-h-[85vh] overflow-y-auto scroll-hidden p-4" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-base">Import from CSV</DialogTitle>
          <DialogDescription className="text-xs">
            Upload CSV files. Each file becomes a material in your list.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-3">
          {/* Left: Drop zone */}
          <div
            onDragOver={e => e.preventDefault()}
            onDrop={handleDrop}
            onClick={openFilePicker}
            className="flex-1 border-2 border-dashed border-border rounded-xl p-4 text-center hover:border-muted-foreground transition-colors cursor-pointer flex flex-col items-center justify-center"
          >
            <Folder size={36} className="mb-2 text-yellow-400" />
            <p className="text-muted-foreground text-xs">
              Tap to browse or drag files
            </p>
            <p className="text-muted-foreground text-[10px] mt-1">Unlimited files</p>
          </div>

          {/* Right: Format example */}
          <div className="flex-1 border border-border rounded-xl p-3">
            <h3 className="text-muted-foreground text-xs font-semibold mb-2">Expected CSV Format</h3>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="text-left py-0.5 font-medium">Step</th>
                  <th className="text-left py-0.5 font-medium">Process</th>
                  <th className="text-left py-0.5 font-medium">Temp</th>
                  <th className="text-left py-0.5 font-medium">Int</th>
                  <th className="text-left py-0.5 font-medium">Time</th>
                </tr>
              </thead>
              <tbody className="text-foreground/80">
                <tr><td className="py-0.5 text-muted-foreground">1</td><td>Heating</td><td>40</td><td></td><td>10</td></tr>
                <tr><td className="py-0.5 text-muted-foreground">2</td><td className="font-bold">Drying</td><td className="font-bold">40</td><td>30</td><td className="font-bold">10</td></tr>
                <tr><td className="py-0.5 text-muted-foreground">3</td><td>Cure</td><td></td><td></td><td>10</td></tr>
                <tr><td className="py-0.5 text-muted-foreground">4</td><td>Cooling</td><td>25</td><td></td><td>5</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Import results */}
        {results.length > 0 && (
          <div className="space-y-1">
            {results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {r.success ? (
                  <CheckCircle size={14} className="text-green-500 shrink-0" />
                ) : (
                  <XCircle size={14} className="text-destructive shrink-0" />
                )}
                <span className={r.success ? 'text-foreground' : 'text-destructive'}>
                  {r.name} {r.success ? '— Added' : '— Invalid format'}
                </span>
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="flex-row gap-3">
          <Button variant="outline" onClick={handleClose} className="flex-1 h-9 text-xs">Cancel</Button>
          <Button onClick={handleClose} disabled={results.length === 0} className="flex-1 h-9 text-xs">Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
