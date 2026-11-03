import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
afterEach(() => vi.unstubAllGlobals())
describe('Cookie与CSRF请求管理', () => {
  it('写请求先获取新CSRF并携带Cookie，不自动重试写操作', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: { csrf_token: 'test-only-csrf' } })),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { ok: true } })))
    vi.stubGlobal('fetch', fetcher)
    await api('/auth/login/', { method: 'POST', body: { username: 'test', password: 'test-only' } })
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[1][1]).toMatchObject({
      credentials: 'include',
      headers: { 'X-CSRFToken': 'test-only-csrf' },
    })
  })
  it('网络与非JSON错误有明确反馈', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(api('/auth/me/')).rejects.toBeInstanceOf(ApiError)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('upstream', { status: 502 })))
    await expect(api('/auth/me/')).rejects.toMatchObject({ status: 502, code: 'request_failed' })
  })
})
