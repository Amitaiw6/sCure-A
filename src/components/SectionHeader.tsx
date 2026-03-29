import { Pencil, Plus } from 'lucide-react'

interface SectionHeaderProps {
  title: string
  showActions?: boolean
}

export default function SectionHeader({ title, showActions = false }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-4 mt-8">
      <h2 className="text-white text-lg font-semibold">{title}</h2>
      {showActions && (
        <div className="flex items-center gap-2">
          <button className="w-8 h-8 rounded-lg bg-gray-700/50 flex items-center justify-center text-gray-400 hover:bg-gray-600 hover:text-white transition-colors">
            <Pencil size={16} />
          </button>
          <button className="w-8 h-8 rounded-lg bg-gray-700/50 flex items-center justify-center text-gray-400 hover:bg-gray-600 hover:text-white transition-colors">
            <Plus size={16} />
          </button>
        </div>
      )}
    </div>
  )
}
