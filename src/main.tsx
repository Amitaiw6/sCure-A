import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MaterialProvider } from '@/context/MaterialContext'
import { PrintHistoryProvider } from '@/context/PrintHistoryContext'
import { HardwareProvider } from '@/context/HardwareContext'
import { SystemConfigProvider } from '@/context/SystemConfigContext'
import { AlertsProvider } from '@/context/AlertsContext'
import { CureHistoryProvider } from '@/context/CureHistoryContext'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
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
    </BrowserRouter>
  </StrictMode>,
)
