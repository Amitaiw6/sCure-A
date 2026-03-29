import { AlertTriangle } from 'lucide-react'

interface AbortModalProps {
  isOpen: boolean
  onClose: () => void
  onAbort: () => void
}

export default function AbortModal({ isOpen, onClose, onAbort }: AbortModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-[#141414] rounded-2xl p-8 max-w-md w-full mx-4 text-center">
        {/* Warning icon */}
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 bg-yellow-400 rounded-xl flex items-center justify-center">
            <AlertTriangle size={36} className="text-black" />
          </div>
        </div>

        <h2 className="text-2xl font-bold text-white mb-4">Abort Cure Process?</h2>

        <p className="text-gray-400 mb-2">
          This will <span className="text-red-500 font-semibold">immediately stop</span> the active heating cycle.
        </p>
        <p className="text-gray-400 mb-2">
          The material may be damaged and the cycle cannot be resumed.
        </p>
        <p className="text-gray-400 mb-6">Are you sure you want to abort?</p>

        {/* Buttons */}
        <div className="flex gap-4">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl border border-[#333] text-white font-semibold hover:bg-[#222] transition-colors"
          >
            Keep Running
          </button>
          <button
            onClick={onAbort}
            className="flex-1 py-3 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-500 transition-colors"
          >
            Yes, Abort
          </button>
        </div>
      </div>
    </div>
  )
}
