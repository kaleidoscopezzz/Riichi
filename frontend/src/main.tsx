import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from '@/app'
import { ThemeProvider } from '@/components/theme-provider'
import { HealthProvider } from '@/components/health-provider'
import { AuthProvider } from '@/components/auth-provider'
import '@/styles/globals.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <HealthProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </HealthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
