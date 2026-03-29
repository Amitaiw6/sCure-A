import { Play } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function StartCureButton() {
  return (
    <div className="fixed bottom-4 right-4">
      <Button className="gap-2 rounded-xl px-5 py-2.5 shadow-lg">
        Start Cure
        <Play size={16} fill="currentColor" />
      </Button>
    </div>
  )
}
