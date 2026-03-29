import { Pencil, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface SectionHeaderProps {
  title: string
  showActions?: boolean
  onAdd?: () => void
  onEdit?: () => void
}

export default function SectionHeader({ title, showActions = false, onAdd, onEdit }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-3 mt-5">
      <h2 className="text-white text-base font-semibold">{title}</h2>
      {showActions && (
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon-sm" onClick={onEdit}>
            <Pencil size={14} />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onAdd}>
            <Plus size={14} />
          </Button>
        </div>
      )}
    </div>
  )
}
