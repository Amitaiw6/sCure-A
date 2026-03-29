import { PlusCircle, ChevronRight } from 'lucide-react'

interface MaterialItemProps {
  label: string
  duration?: string
  isCommand?: boolean
}

export default function MaterialItem({ label, duration, isCommand }: MaterialItemProps) {
  return (
    <div className="flex items-center justify-between bg-gray-800/80 rounded-2xl px-5 py-4 mb-3 hover:bg-gray-700/80 transition-colors cursor-pointer group">
      <div className="flex items-center gap-3">
        <PlusCircle size={22} className="text-gray-500" />
        <span className="text-gray-300 text-base">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        {duration && (
          <span className={`text-sm font-medium ${isCommand ? 'text-cyan-400' : 'text-cyan-400'}`}>
            {duration}
          </span>
        )}
        <ChevronRight size={18} className="text-gray-500 group-hover:text-gray-300 transition-colors" />
      </div>
    </div>
  )
}
