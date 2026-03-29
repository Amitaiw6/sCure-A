import { PlusCircle, ChevronRight } from 'lucide-react'

interface MaterialItemProps {
  label: string
  duration?: string
  isCommand?: boolean
  isSelected?: boolean
  onClick?: () => void
}

export default function MaterialItem({ label, duration, isCommand, isSelected, onClick }: MaterialItemProps) {
  return (
    <div
      onClick={onClick}
      className={`flex items-center justify-between rounded-2xl px-4 py-3 mb-2 transition-colors cursor-pointer group ${
        isSelected
          ? 'bg-[#1a1a1a] border border-sky-500/60'
          : 'bg-[#141414] border border-[#222] hover:bg-[#1a1a1a]'
      }`}
    >
      <div className="flex items-center gap-3">
        <PlusCircle size={20} className="text-gray-500" />
        <span className="text-gray-300 text-sm">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        {duration && (
          <span className={`text-xs font-medium ${isCommand ? 'text-cyan-400' : 'text-cyan-400'}`}>
            {duration}
          </span>
        )}
        <ChevronRight size={16} className="text-gray-500 group-hover:text-gray-300 transition-colors" />
      </div>
    </div>
  )
}
