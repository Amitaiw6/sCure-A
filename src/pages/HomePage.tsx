import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import SectionHeader from '../components/SectionHeader'
import MaterialItem from '../components/MaterialItem'
import { Play } from 'lucide-react'

export default function HomePage() {
  const navigate = useNavigate()
  const [selectedIndex, setSelectedIndex] = useState<number | null>(1)

  const materials = [
    { label: 'st45', duration: '20min' },
    { label: 'Label text', duration: '30min' },
    { label: 'Label text', duration: '⌘C', isCommand: true },
    { label: 'Label text', duration: '⌘C', isCommand: true },
    { label: 'Label text' },
  ]

  return (
    <main className="px-4 pb-16 relative">
      {/* NFC Section */}
      <SectionHeader title="NFC" />
      <MaterialItem label="Label text" duration="15min" />

      {/* Material List Section */}
      <SectionHeader title="Material List" showActions />
      {materials.map((mat, i) => (
        <MaterialItem
          key={i}
          label={mat.label}
          duration={mat.duration}
          isCommand={mat.isCommand}
          isSelected={selectedIndex === i}
          onClick={() => setSelectedIndex(i)}
        />
      ))}

      {/* Start Cure Button */}
      <div className="fixed bottom-4 right-4">
        <button
          onClick={() => navigate('/cure-process')}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white font-semibold px-5 py-2.5 rounded-xl shadow-lg shadow-sky-600/30 transition-all active:scale-95 text-sm"
        >
          <span>Start Cure</span>
          <Play size={16} fill="currentColor" />
        </button>
      </div>
    </main>
  )
}
