import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchHealth } from '@/services/health'
import { HealthContext, type HealthState } from '@/components/health-context'

export function HealthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<HealthState, 'check'>>({
    status: 'loading',
    message: '正在检查服务连接',
    checkedAt: null,
  })
  const request = useRef<AbortController | null>(null)
  const check = useCallback(() => {
    request.current?.abort()
    request.current = null
    if (!navigator.onLine) {
      setState({
        status: 'offline',
        message: '网络已断开，请恢复网络后重试',
        checkedAt: new Date(),
      })
      return
    }
    const controller = new AbortController()
    request.current = controller
    let timedOut = false
    const timer = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 8000)
    setState((previous) => ({ ...previous, status: 'loading', message: '正在检查服务连接' }))
    void fetchHealth(controller.signal)
      .then(() => {
        if (request.current === controller && !controller.signal.aborted)
          setState({ status: 'connected', message: '后端服务运行正常', checkedAt: new Date() })
      })
      .catch((error: unknown) => {
        if (request.current !== controller || (controller.signal.aborted && !timedOut)) return
        setState({
          status: 'error',
          message: timedOut
            ? '连接超时，请确认后端服务已启动'
            : error instanceof Error && error.message.startsWith('健康检查')
              ? error.message
              : '暂时无法连接后端，请确认服务已启动后重试',
          checkedAt: new Date(),
        })
      })
      .finally(() => window.clearTimeout(timer))
  }, [])
  useEffect(() => {
    check()
    window.addEventListener('online', check)
    window.addEventListener('offline', check)
    return () => {
      request.current?.abort()
      request.current = null
      window.removeEventListener('online', check)
      window.removeEventListener('offline', check)
    }
  }, [check])
  return <HealthContext.Provider value={{ ...state, check }}>{children}</HealthContext.Provider>
}
