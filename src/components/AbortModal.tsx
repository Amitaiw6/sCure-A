import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'

interface AbortModalProps {
  isOpen: boolean
  onClose: () => void
  onAbort: () => void
}

export default function AbortModal({ isOpen, onClose, onAbort }: AbortModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md text-center" showCloseButton={false}>
        <DialogHeader className="items-center">
          <div className="w-16 h-16 bg-yellow-400 rounded-xl flex items-center justify-center mb-2">
            <AlertTriangle size={36} className="text-black" />
          </div>
          <DialogTitle className="text-2xl">Abort Cure Process?</DialogTitle>
          <DialogDescription>
            This will <span className="text-destructive font-semibold">immediately stop</span> the active heating cycle.
            The material may be damaged and the cycle cannot be resumed.
            Are you sure you want to abort?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="flex-row gap-3 sm:justify-center">
          <Button variant="outline" onClick={onClose} className="flex-1">
            Keep Running
          </Button>
          <Button variant="destructive" onClick={onAbort} className="flex-1 bg-destructive text-destructive-foreground hover:bg-destructive/90">
            Yes, Abort
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
