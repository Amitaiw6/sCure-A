import { Pencil, Plus } from 'lucide-react'

interface SectionHeaderProps {
  title: string
  showActions?: boolean
}

export default function SectionHeader({ title, showActions = false }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-3 mt-5">
      <h2 className="text-white text-base font-semibold">{title}</h2>
      {showActions && (
        <div className="flex items-center gap-2">
          <button className="w-7 h-7 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-gray-400 hover:bg-[#252525] hover:text-white transition-colors">
            <Pencil size={14} />
          </button>
          <button className="w-7 h-7 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-gray-400 hover:bg-[#252525] hover:text-white transition-colors">
            <Plus size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
