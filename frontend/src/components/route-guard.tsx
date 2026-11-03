import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './auth-context'
import { Button } from './ui/button'

export function RouteGuard({ admin = false }: { admin?: boolean }) {
  const { user, loading, error, restore } = useAuth()
  const location = useLocation()
  if (loading)
    return (
      <div className="session-state" role="status">
        正在恢复登录会话…
      </div>
    )
  if (error)
    return (
      <div className="session-state" role="alert">
        <p>{error}</p>
        <Button onClick={() => void restore()}>重新连接</Button>
      </div>
    )
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (admin && !user.is_staff)
    return (
      <div className="session-state" role="alert">
        <h1>无权访问</h1>
        <p>此管理页面仅向管理员开放。</p>
        <a href="/dashboard">返回仪表盘</a>
      </div>
    )
  return <Outlet />
}
