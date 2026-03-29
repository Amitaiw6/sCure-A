import { useRef } from 'react'
import { Folder } from 'lucide-react'

interface ImportCsvModalProps {
  isOpen: boolean
  onClose: () => void
  onImport: (file: File) => void
}

export default function ImportCsvModal({ isOpen, onClose, onImport }: ImportCsvModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onImport(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) onImport(file)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-[#141414] rounded-2xl p-6 w-[560px] mx-4">
        <h2 className="text-xl font-bold text-white mb-2">Import from CSV</h2>
        <p className="text-gray-400 text-sm mb-5">
          Upload a CSV file with step definitions. The file will be parsed and steps added to the current sequence.
        </p>

        {/* Drop zone */}
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={handleDrop}
          className="border-2 border-dashed border-[#333] rounded-xl p-8 text-center mb-5 hover:border-gray-400 transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          <Folder size={48} className="mx-auto mb-3 text-yellow-400" />
          <p className="text-gray-400 text-sm">
            Drag & drop a CSV file here, or <span className="text-sky-400 hover:underline">browse</span>
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

        {/* Expected format */}
        <div className="border border-[#333] rounded-xl p-4 mb-5">
          <h3 className="text-gray-400 text-sm font-semibold mb-3">Expected Csv Format</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400">
                <th className="text-left py-1 font-medium">Step</th>
                <th className="text-left py-1 font-medium">Process</th>
                <th className="text-left py-1 font-medium">Temperature</th>
                <th className="text-left py-1 font-medium">Intensity</th>
                <th className="text-left py-1 font-medium">Time</th>
              </tr>
            </thead>
            <tbody className="text-gray-300">
              <tr><td className="py-1 text-gray-500">1</td><td className="py-1">Heating</td><td className="py-1">40</td><td className="py-1"></td><td className="py-1">10</td></tr>
              <tr><td className="py-1 text-gray-500">2</td><td className="py-1 font-bold">Drying</td><td className="py-1 font-bold">40</td><td className="py-1">30</td><td className="py-1 font-bold">10</td></tr>
              <tr><td className="py-1 text-gray-500">3</td><td className="py-1">Cure</td><td className="py-1"></td><td className="py-1"></td><td className="py-1">10</td></tr>
              <tr><td className="py-1 text-gray-500">4</td><td className="py-1">Cooling</td><td className="py-1">25</td><td className="py-1"></td><td className="py-1">5</td></tr>
            </tbody>
          </table>
        </div>

        {/* Buttons */}
        <div className="flex gap-4">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl border border-[#333] text-gray-400 font-semibold hover:bg-[#222] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl border border-[#333] text-gray-400 font-semibold hover:bg-[#222] transition-colors"
          >
            Import Steps
          </button>
        </div>
      </div>
    </div>
  )
}
