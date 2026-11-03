import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchHealth, healthEndpoint } from './health'

afterEach(() => vi.unstubAllGlobals())

describe('实际健康检查协议', () => {
  it('请求版本化接口并返回经过校验的服务信息', async () => {
    const payload = { status: 'ok', service: 'riichi-api', api_version: 'v1' }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchHealth()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/health/',
      expect.objectContaining({ cache: 'no-store', headers: { Accept: 'application/json' } }),
    )
    expect(healthEndpoint).toBe('/api/v1/health/')
  })

  it('HTTP 错误不能被当作已连接', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    await expect(fetchHealth()).rejects.toThrow('HTTP 503')
  })

  it.each([
    { status: 'down', service: 'riichi-api', api_version: 'v1' },
    { status: 'ok', service: 'another-api', api_version: 'v1' },
    { status: 'ok', service: 'riichi-api', api_version: 'v2' },
    null,
  ])('拒绝协议不匹配的响应：%j', async (payload) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))))
    await expect(fetchHealth()).rejects.toThrow('响应格式不符合约定')
  })

  it('拒绝服务器返回的 HTML，而不报告连接成功', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>upstream error</html>')))
    await expect(fetchHealth()).rejects.toBeInstanceOf(SyntaxError)
  })

  it('把取消信号传给 fetch，并保留网络错误', async () => {
    const controller = new AbortController()
    const error = new TypeError('Failed to fetch')
    const fetchMock = vi.fn().mockRejectedValue(error)
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchHealth(controller.signal)).rejects.toBe(error)
    expect(fetchMock).toHaveBeenCalledWith(
      healthEndpoint,
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
