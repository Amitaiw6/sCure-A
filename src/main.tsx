import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, HashRouter } from 'react-router-dom'
import { MaterialProvider } from '@/context/MaterialContext'
import { PrintHistoryProvider } from '@/context/PrintHistoryContext'
import { HardwareProvider } from '@/context/HardwareContext'
import { SystemConfigProvider } from '@/context/SystemConfigContext'
import { AlertsProvider } from '@/context/AlertsContext'
import { CureHistoryProvider } from '@/context/CureHistoryContext'
import './index.css'
import App from './App.tsx'

// When opened directly from a file (the offline single-file design build), use hash
// routing so navigation stays inside the document instead of escaping to file:///.
// Served / dev builds keep normal history routing.
const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter

// The whole UI is designed on a fixed 800x480 canvas (#root). Stretch it to
// fill the physical screen — 1280x720 on the device's DSI panel, any size in
// the Windows desktop window. CSS alone can't do this (scale needs unitless
// numbers, calc(100vw/800) yields a length), so compute the factors here.
export const DESIGN_W = 800
export const DESIGN_H = 480
function fitToScreen() {
  const root = document.getElementById('root')
  if (root) root.style.scale =
    `${window.innerWidth / DESIGN_W} ${window.innerHeight / DESIGN_H}`
}
window.addEventListener('resize', fitToScreen)
fitToScreen()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <SystemConfigProvider>
        <HardwareProvider>
          <AlertsProvider>
            <CureHistoryProvider>
              <MaterialProvider>
                <PrintHistoryProvider>
                  <App />
                </PrintHistoryProvider>
              </MaterialProvider>
            </CureHistoryProvider>
          </AlertsProvider>
        </HardwareProvider>
      </SystemConfigProvider>
    </Router>
  </StrictMode>,
)
