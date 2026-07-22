import { useState } from 'react'
import { CheckCircle, XCircle, Loader2, Upload, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { fetchUpdatePackage, updateSoftware } from '@/services/hardware-api'
import { verifyUpdatePackage } from '@/lib/compliance'

interface UpdateModalProps {
  isOpen: boolean
  onClose: () => void
}

interface UpdateStep {
  step: string
  status: string
}

export default function UpdateModal({ isOpen, onClose }: UpdateModalProps) {
  const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [steps, setSteps] = useState<UpdateStep[]>([])
  const [message, setMessage] = useState('')
  const [version, setVersion] = useState('')

  // Mark the current (last) running step as failed and stop the update.
  const failHere = (msg: string) => {
    setSteps(prev => [
      ...prev.slice(0, -1),
      { ...prev[prev.length - 1], status: 'error' },
    ])
    setMessage(msg)
    setStatus('error')
  }

  const handleUpdate = async () => {
    setStatus('running')
    setSteps([
      { step: 'Finding USB drive...', status: 'running' },
    ])

    await new Promise(r => setTimeout(r, 700))
    setSteps(prev => [
      { ...prev[0], status: 'ok' },
      { step: 'Looking for update package...', status: 'running' },
    ])

    // Locate the package + its expected checksum
    const pkgRes = await fetchUpdatePackage()
    if (!pkgRes.ok || !pkgRes.package) {
      failHere(pkgRes.message)
      return
    }

    setSteps(prev => [
      ...prev.slice(0, -1),
      { ...prev[prev.length - 1], status: 'ok' },
      { step: 'Verifying integrity (SHA-256)...', status: 'running' },
    ])

    // EN 18031 secure-update control: a corrupt/tampered/unsigned package is rejected.
    const verify = await verifyUpdatePackage(pkgRes.package.bytes, pkgRes.package.expectedSha256)
    if (!verify.ok) {
      failHere(verify.reason)
      return
    }

    setSteps(prev => [
      ...prev.slice(0, -1),
      { ...prev[prev.length - 1], status: 'ok' },
      { step: 'Installing update...', status: 'running' },
    ])

    // Actual API call
    const result = await updateSoftware()

    if (result.ok) {
      setSteps(prev => [
        ...prev.slice(0, -1),
        { ...prev[prev.length - 1], status: 'ok' },
      ])
      setVersion(result.version || pkgRes.package!.version || '')
      setMessage(result.message)
      setStatus('success')
    } else {
      failHere(result.message)
    }
  }

  const handleClose = () => {
    if (status === 'running') return
    setStatus('idle')
    setSteps([])
    setMessage('')
    setVersion('')
    onClose()
    if (status === 'success') {
      window.location.reload()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[400px] p-4" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Upload size={16} />
            Software Update
          </DialogTitle>
        </DialogHeader>

        {status === 'idle' && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-xs">
              Insert a USB drive with a <span className="text-foreground font-mono">.scu</span> update file, then press Update.
            </p>
            <div className="bg-secondary rounded-lg p-3 text-xs space-y-1">
              <p className="text-muted-foreground">The update will:</p>
              <p className="text-foreground">1. Find the update file on USB</p>
              <p className="text-foreground">2. Verify integrity (SHA-256)</p>
              <p className="text-foreground">3. Backup current version</p>
              <p className="text-foreground">4. Install new version</p>
              <p className="text-foreground">5. Restart services</p>
            </div>
          </div>
        )}

        {status !== 'idle' && (
          <div className="space-y-2">
            {steps.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {s.status === 'running' ? (
                  <Loader2 size={14} className="text-primary animate-spin shrink-0" />
                ) : s.status === 'ok' ? (
                  <CheckCircle size={14} className="text-green-500 shrink-0" />
                ) : (
                  <XCircle size={14} className="text-destructive shrink-0" />
                )}
                <span className={s.status === 'error' ? 'text-destructive' : 'text-foreground'}>{s.step}</span>
              </div>
            ))}

            {status === 'success' && (
              <div className="bg-green-500/10 rounded-lg p-3 mt-2">
                <p className="text-green-400 text-xs font-semibold">Update successful!</p>
                {version && <p className="text-green-400/80 text-[10px]">Version: {version}</p>}
                <p className="text-muted-foreground text-[10px] mt-1">System will reload.</p>
              </div>
            )}

            {status === 'error' && (
              <div className="bg-destructive/10 rounded-lg p-3 mt-2">
                <p className="text-destructive text-xs font-semibold">Update failed</p>
                <p className="text-destructive/80 text-[10px]">{message}</p>
                <p className="text-muted-foreground text-[10px] mt-1">Previous version was restored.</p>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="flex-row gap-3">
          {status !== 'running' && (
            <Button variant="outline" onClick={handleClose} className="flex-1 text-xs h-9">
              {status === 'success' ? 'Restart Now' : 'Cancel'}
            </Button>
          )}
          {status === 'idle' && (
            <Button onClick={handleUpdate} className="flex-1 text-xs h-9 gap-1">
              <RefreshCw size={13} /> Update
            </Button>
          )}
          {status === 'error' && (
            <Button onClick={handleUpdate} className="flex-1 text-xs h-9 gap-1">
              <RefreshCw size={13} /> Retry
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
