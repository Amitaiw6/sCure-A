import { Play } from 'lucide-react'

export default function StartCureButton() {
  return (
    <div className="fixed bottom-6 right-6">
      <button className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white font-semibold px-6 py-3 rounded-2xl shadow-lg shadow-sky-600/30 transition-all hover:shadow-sky-500/40 active:scale-95">
        <span>Start Cure</span>
        <Play size={18} fill="currentColor" />
      </button>
    </div>
  )
}
