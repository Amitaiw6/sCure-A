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
