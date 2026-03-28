import { useNavigate } from 'react-router-dom'
import SectionHeader from '../components/SectionHeader'
import MaterialItem from '../components/MaterialItem'
import { Play } from 'lucide-react'

export default function HomePage() {
  const navigate = useNavigate()

  return (
    <main className="px-6 pb-24">
      {/* NFC Section */}
      <SectionHeader title="NFC" />
      <MaterialItem label="Label text" duration="15min" />

      {/* Material List Section */}
      <SectionHeader title="Material List" showActions />
      <MaterialItem label="st45" duration="20min" />
      <MaterialItem label="Label text" duration="30min" />
      <MaterialItem label="Label text" duration="⌘C" isCommand />
      <MaterialItem label="Label text" duration="⌘C" isCommand />
      <MaterialItem label="Label text" />

      {/* Start Cure Button */}
      <div className="fixed bottom-6 right-6">
        <button
          onClick={() => navigate('/cure-process')}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white font-semibold px-6 py-3 rounded-2xl shadow-lg shadow-sky-600/30 transition-all hover:shadow-sky-500/40 active:scale-95"
        >
          <span>Start Cure</span>
          <Play size={18} fill="currentColor" />
        </button>
      </div>
    </main>
  )
}
