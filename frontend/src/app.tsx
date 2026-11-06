import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppLayout } from '@/layouts/app-layout'
import { DashboardPage } from '@/pages/dashboard'
import { TournamentsPage } from '@/pages/tournaments'
import { SettingsPage } from '@/pages/settings'
import { NotFoundPage } from '@/pages/not-found'
import { AuthPage } from '@/pages/auth'
import { ProfilePage } from '@/pages/profile'
import { PlayersPage } from '@/pages/players'
import { RouteGuard } from '@/components/route-guard'
import { ErrorBoundary } from '@/components/error-boundary'
import { MachinesPage } from '@/pages/machines'
import { RoundsPage } from '@/pages/rounds'

export function App() {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary resetKey={pathname}>
      <Routes>
        <Route path="login" element={<AuthPage key="login" />} />
        <Route path="register" element={<Navigate to="/login" replace />} />
        <Route element={<RouteGuard admin />}>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route element={<RouteGuard admin />}>
              <Route path="tournaments" element={<TournamentsPage />} />
              <Route path="tournaments/:id/rounds" element={<RoundsPage />} />
              <Route path="players" element={<PlayersPage />} />
              <Route path="machines" element={<MachinesPage />} />
            </Route>
            <Route path="profile" element={<ProfilePage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
