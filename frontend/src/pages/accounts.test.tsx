// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation, type InitialEntry } from 'react-router-dom'
import { App } from '@/app'
import { AuthProvider } from '@/components/auth-provider'
import { ThemeProvider } from '@/components/theme-provider'
import { HealthContext } from '@/components/health-context'
import { api, ApiError } from '@/services/api'

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  api: vi.fn(),
}))
const user = {
  id: 1,
  username: 'test_account',
  is_staff: false,
  date_joined: '2026-11-03T00:00:00Z',
}
const profile = {
  id: 1,
  username: user.username,
  nickname: '测试昵称',
  date_joined: user.date_joined,
  created_at: user.date_joined,
  updated_at: user.date_joined,
}
const mocked = vi.mocked(api)
let current = ''
function LocationProbe() {
  const location = useLocation()
  current = `${location.pathname}${location.search}${location.hash}`
  return null
}
function show(path: InitialEntry = '/login') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <ThemeProvider>
        <HealthContext.Provider
          value={{
            status: 'connected',
            message: '后端服务运行正常',
            checkedAt: new Date(),
            check: vi.fn(),
          }}
        >
          <AuthProvider>
            <App />
          </AuthProvider>
        </HealthContext.Provider>
      </ThemeProvider>
    </MemoryRouter>,
  )
}
beforeEach(() => {
  mocked.mockReset()
  mocked.mockRejectedValue(new ApiError(403, 'not_authenticated', '请先登录。'))
})
afterEach(cleanup)
describe('账号页面及权限', () => {
  it('匿名访问受保护路由跳转登录页', async () => {
    show('/profile')
    expect(await screen.findByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy()
    expect(screen.queryByText('我的选手档案')).toBeNull()
  })
  it('注册路由只显示管理员登录，不提供表单或公开注册请求', async () => {
    show('/register')
    await screen.findByRole('button', { name: '登录' })
    expect(screen.queryByLabelText('确认密码')).toBeNull()
    expect(screen.queryByRole('link', { name: '创建账号' })).toBeNull()
    expect(mocked.mock.calls.some(([path]) => path === '/auth/register/')).toBe(false)
  })
  it('登录失败显示反馈并允许重试', async () => {
    mocked.mockImplementation(async (path) => {
      throw new ApiError(
        path === '/auth/login/' ? 400 : 403,
        path === '/auth/login/' ? 'invalid_credentials' : 'not_authenticated',
        '用户名或密码错误。',
      )
    })
    show()
    const keyboard = userEvent.setup()
    await keyboard.type(screen.getByLabelText('用户名'), 'test_account')
    await keyboard.type(screen.getByLabelText('密码'), 'wrong')
    await keyboard.click(await screen.findByRole('button', { name: '登录' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
  })
  it('通过me恢复管理员会话与管理菜单', async () => {
    mocked.mockResolvedValue({ ...user, is_staff: true })
    show('/dashboard')
    expect(await screen.findByRole('link', { name: '我的个人资料' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /^选手管理$/ })).toBeTruthy()
    expect(mocked).toHaveBeenCalledWith('/auth/me/')
  })
  it('普通用户直接访问管理员路由被拒绝', async () => {
    mocked.mockResolvedValue(user)
    show('/players')
    expect(await screen.findByRole('heading', { name: '无权访问' })).toBeTruthy()
    expect(mocked.mock.calls.some(([path]) => path.startsWith('/players/'))).toBe(false)
  })
  it('管理员显示选手菜单并查询真实接口', async () => {
    mocked.mockImplementation(async (path) =>
      path === '/auth/me/'
        ? { ...user, is_staff: true }
        : { count: 0, next: null, previous: null, results: [] },
    )
    show('/players')
    expect(await screen.findByText('没有匹配的选手')).toBeTruthy()
    expect(
      within(screen.getByRole('navigation', { name: '主导航' })).getByRole('link', {
        name: /^选手管理$/,
      }),
    ).toBeTruthy()
  })
  it('修改自己的昵称并显示保存结果', async () => {
    mocked.mockImplementation(async (path, options) =>
      path === '/auth/me/'
        ? { ...user, is_staff: true }
        : options?.method === 'PATCH'
          ? { ...profile, nickname: '新昵称' }
          : profile,
    )
    show('/profile')
    const input = await screen.findByLabelText('显示名称')
    const keyboard = userEvent.setup()
    await keyboard.clear(input)
    await keyboard.type(input, '新昵称')
    await keyboard.click(screen.getByRole('button', { name: '保存显示名称' }))
    expect(await screen.findByText('管理员显示名称已保存。')).toBeTruthy()
    expect(mocked).toHaveBeenCalledWith('/players/me/', {
      method: 'PATCH',
      body: { nickname: '新昵称' },
    })
  })
  it('恢复会话网络错误提供重试，不误判为匿名', async () => {
    mocked.mockRejectedValue(new ApiError(0, 'network_error', '连接失败'))
    show('/dashboard')
    expect(await screen.findByRole('button', { name: '重新连接' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: '欢迎回到 Riichi' })).toBeNull()
  })
  it('退出成功后回到登录页', async () => {
    mocked.mockImplementation(async (path) =>
      path === '/auth/me/' ? { ...user, is_staff: true } : { logged_out: true },
    )
    show('/dashboard')
    await userEvent.click(await screen.findByRole('button', { name: '退出' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy(),
    )
  })
})

const admin = { ...user, is_staff: true }
const emptyPage = { count: 0, next: null, previous: null, results: [] }
// The admin session is valid only between a successful /auth/login/ (or the initial
// state) and expire(); every other request then fails as not authenticated.
function session(signedIn = false) {
  mocked.mockImplementation(async (path) => {
    if (path === '/auth/login/') {
      signedIn = true
      return admin
    }
    if (!signedIn) throw new ApiError(403, 'not_authenticated', '请先登录。')
    return path === '/auth/me/' ? admin : emptyPage
  })
  return {
    expire() {
      signedIn = false
      act(() => {
        window.dispatchEvent(new Event('riichi-session-expired'))
      })
    },
  }
}
async function signIn() {
  const keyboard = userEvent.setup()
  await keyboard.type(await screen.findByLabelText('用户名'), 'test_account')
  await keyboard.type(screen.getByLabelText('密码'), 'test-only')
  await keyboard.click(screen.getByRole('button', { name: '登录' }))
}
describe('登录后回到原页面（F2）', () => {
  it('未登录访问 /players → 跳到 /login → 登录成功后回到 /players', async () => {
    session()
    show('/players')
    expect(await screen.findByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy()
    expect(current).toBe('/login')
    await signIn()
    expect(await screen.findByText('没有匹配的选手')).toBeTruthy()
    expect(current).toBe('/players')
  })
  it('会话过期后重新登录回到原页面，并保留 search 与 hash', async () => {
    const admin = session(true)
    show('/players?status=archived#list')
    expect(await screen.findByText('没有匹配的选手')).toBeTruthy()
    admin.expire()
    expect(await screen.findByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy()
    expect(current).toBe('/login')
    await signIn()
    expect(await screen.findByText('没有匹配的选手')).toBeTruthy()
    expect(current).toBe('/players?status=archived#list')
  })
  it('直接打开登录页，登录后进入仪表盘', async () => {
    session()
    show('/login')
    await signIn()
    await waitFor(() => expect(current).toBe('/dashboard'))
  })
  it.each([
    '//evil.example/players',
    'https://evil.example/players',
    '/\\evil.example',
    '/login',
    { pathname: '/register', search: '', hash: '' },
    { pathname: '//evil.example', search: '', hash: '' },
  ])('站外或认证页 from=%j 不会被跳转，退回仪表盘', async (from) => {
    session()
    show({ pathname: '/login', state: { from } })
    await signIn()
    await waitFor(() => expect(current).toBe('/dashboard'))
  })
})
