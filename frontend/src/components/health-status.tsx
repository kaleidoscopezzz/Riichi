import { Check, CircleAlert, LoaderCircle, RefreshCw, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useHealth } from '@/components/health-context'

export function HealthBadge() {
  const { status } = useHealth()
  return (
    <span className={`health-chip health-${status}`} aria-live="polite">
      <span className="status-dot" />
      {status === 'loading'
        ? '正在连接'
        : status === 'connected'
          ? '服务已连接'
          : status === 'offline'
            ? '网络离线'
            : '服务未连接'}
    </span>
  )
}

export function HealthStatus() {
  const { status, message, checkedAt, check } = useHealth()
  const Icon =
    status === 'loading'
      ? LoaderCircle
      : status === 'connected'
        ? Check
        : status === 'offline'
          ? WifiOff
          : CircleAlert
  return (
    <section className="system-panel" aria-label="后端连接状态">
      <div className="section-heading">
        <div>
          <span className="eyebrow">SYSTEM STATUS</span>
          <h2>系统运行状态</h2>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={check}
          disabled={status === 'loading'}
          className="refresh-button"
        >
          <RefreshCw className={status === 'loading' ? 'animate-spin' : ''} />
          重新检查
        </Button>
      </div>
      <div className={`connection-summary health-${status}`} role="status" aria-live="polite">
        <span className="connection-icon">
          <Icon className={status === 'loading' ? 'animate-spin' : ''} size={21} />
        </span>
        <div>
          <h3>
            {status === 'connected'
              ? '后端连接正常'
              : status === 'loading'
                ? '正在连接后端服务'
                : status === 'offline'
                  ? '当前网络已离线'
                  : '后端服务暂未连接'}
          </h3>
          <p>{message}</p>
        </div>
        {status === 'connected' && (
          <Badge variant="outline" className="online-badge">
            正常
          </Badge>
        )}
      </div>
      <dl className="status-details">
        <div>
          <dt>API 服务</dt>
          <dd>Django REST Framework</dd>
        </div>
        <div>
          <dt>接口版本</dt>
          <dd className="mono">v1</dd>
        </div>
        <div>
          <dt>最近检查</dt>
          <dd>
            {status === 'loading' ? (
              <Skeleton className="h-4 w-20" />
            ) : (
              (checkedAt?.toLocaleTimeString('zh-CN', { hour12: false }) ?? '尚未检查')
            )}
          </dd>
        </div>
      </dl>
      <div className="panel-footnote">
        <span className="tiny-dot" />
        仅验证服务存活，不检查数据库就绪。
      </div>
    </section>
  )
}
