export type HealthResponse = { status: 'ok'; service: 'riichi-api'; api_version: 'v1' }

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const healthEndpoint = `${base}/api/v1/health/`

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(healthEndpoint, {
    signal,
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  if (!response.ok) throw new Error(`服务暂不可用（HTTP ${response.status}）`)
  const data: unknown = await response.json()
  if (
    !data ||
    typeof data !== 'object' ||
    !('status' in data) ||
    data.status !== 'ok' ||
    !('service' in data) ||
    data.service !== 'riichi-api' ||
    !('api_version' in data) ||
    data.api_version !== 'v1'
  )
    throw new Error('健康检查响应格式不符合约定')
  return data as HealthResponse
}
