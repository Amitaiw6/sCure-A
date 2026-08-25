import { Link } from 'react-router-dom'
import { SlidersHorizontal, ThermometerSun, ChevronRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Developer Mode tool registry — add new tools here (plus their route in App.tsx).
const DEV_TOOLS: { path: string; title: string; description: string; icon: LucideIcon }[] = [
  {
    path: '/dev/led-calibration',
    title: 'LED Intensity Calibration',
    description: 'Per-zone calibration factors (Back / Door / Left / Right) that define the calibrated system LED power.',
    icon: SlidersHorizontal,
  },
  {
    path: '/dev/hdt-calibration',
    title: 'Material HDT Calibration',
    description: 'Automatic 10–90% power sweep against a material HDT limit, measured on the PicoLog TC-08 (CH1).',
    icon: ThermometerSun,
  },
]

export default function DevMenuPage() {
  return (
    <main className="p-4 flex flex-col gap-3">
      <h2 className="text-muted-foreground text-xs font-semibold tracking-widest uppercase">Developer Tools</h2>
      {DEV_TOOLS.map(tool => (
        <Link
          key={tool.path}
          to={tool.path}
          className="flex items-center gap-4 bg-card rounded-xl p-4 hover:bg-accent/60 active:bg-accent transition-colors touch-manipulation"
        >
          <div className="w-12 h-12 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center shrink-0">
            <tool.icon size={24} className="text-amber-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-foreground text-base font-semibold">{tool.title}</div>
            <div className="text-muted-foreground text-xs leading-snug">{tool.description}</div>
          </div>
          <ChevronRight size={20} className="text-muted-foreground shrink-0" />
        </Link>
      ))}
    </main>
  )
}
