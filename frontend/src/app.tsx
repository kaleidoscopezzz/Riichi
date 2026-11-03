import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/layouts/app-layout'
import { DashboardPage } from '@/pages/dashboard'
import { PlaceholderPage } from '@/pages/placeholder'
import { SettingsPage } from '@/pages/settings'
import { NotFoundPage } from '@/pages/not-found'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="tournaments" element={<PlaceholderPage />} />
        <Route path="players" element={<PlaceholderPage />} />
        <Route path="machines" element={<PlaceholderPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
