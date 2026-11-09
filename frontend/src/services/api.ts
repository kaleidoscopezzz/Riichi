const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

/** DRF validation errors: message lists, nested dicts or per-item lists. */
export type FieldErrors = Record<string, unknown>

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: FieldErrors = {},
  ) {
    super(message)
  }
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = options.method || 'GET'
  let token: string | undefined
  if (method !== 'GET') {
    const csrf = await api<{ csrf_token: string }>('/auth/csrf/', { signal: options.signal })
    token = csrf.csrf_token
  }
  let response: Response
  try {
    response = await fetch(`${base}/api/v1${path}`, {
      method,
      credentials: 'include',
      signal: options.signal,
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { 'X-CSRFToken': token } : {}),
      },
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', '无法连接服务，请检查网络后重试。')
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const problem = payload?.error
    const error = new ApiError(
      response.status,
      problem?.code || 'request_failed',
      problem?.message || '请求失败，请稍后重试。',
      problem?.fields || {},
    )
    if (error.code === 'not_authenticated' && path !== '/auth/me/')
      window.dispatchEvent(new Event('riichi-session-expired'))
    throw error
  }
  if (!payload || !('data' in payload))
    throw new ApiError(0, 'invalid_response', '服务响应格式不正确。')
  return payload.data as T
}

export type User = { id: number; username: string; is_staff: boolean; date_joined: string }
export type Player = {
  id: number
  username?: string
  nickname: string
  is_active?: boolean
  can_delete?: boolean
  reference_count?: number
  date_joined?: string
  created_at: string
  updated_at: string
}
