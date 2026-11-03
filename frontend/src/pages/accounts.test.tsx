// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
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
function show(path = '/login') {
  return render(
    <MemoryRouter initialEntries={[path]}>
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
async function fillRegistration(password = 'Password!39A', confirm = password) {
  const keyboard = userEvent.setup()
  await keyboard.type(screen.getByLabelText('用户名'), 'new_account')
  await keyboard.type(screen.getByLabelText('选手昵称'), '测试选手')
  await keyboard.type(screen.getByLabelText('密码', { exact: true }), password)
  await keyboard.type(screen.getByLabelText('确认密码'), confirm)
  return keyboard
}
describe('账号页面及权限', () => {
  it('匿名访问受保护路由跳转登录页', async () => {
    show('/profile')
    expect(await screen.findByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy()
    expect(screen.queryByText('我的选手档案')).toBeNull()
  })
  it('注册表单检查确认密码，不发送无效写请求', async () => {
    show('/register')
    await screen.findByRole('button', { name: '注册账号' })
    const keyboard = await fillRegistration('Password!39A', 'different')
    await keyboard.click(screen.getByRole('button', { name: '注册账号' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(mocked.mock.calls.some(([path]) => path === '/auth/register/')).toBe(false)
  })
  it('注册表单检查密码长度', async () => {
    show('/register')
    const keyboard = await fillRegistration('short')
    await keyboard.click(screen.getByRole('button', { name: '注册账号' }))
    expect(await screen.findByText('密码至少需要 8 个字符。')).toBeTruthy()
  })
  it('显示API字段错误', async () => {
    mocked.mockImplementation(async (path) => {
      if (path === '/auth/register/')
        throw new ApiError(400, 'validation_error', '检查表单', {
          username: ['此用户名已被使用。'],
        })
      throw new ApiError(403, 'not_authenticated', '请先登录')
    })
    show('/register')
    const keyboard = await fillRegistration()
    await keyboard.click(screen.getByRole('button', { name: '注册账号' }))
    expect(await screen.findByText('用户名：此用户名已被使用。')).toBeTruthy()
  })
  it('注册成功后进入独立登录表单', async () => {
    mocked.mockImplementation(async (path) => {
      if (path === '/auth/register/') return user
      throw new ApiError(403, 'not_authenticated', '请先登录')
    })
    show('/register')
    const keyboard = await fillRegistration()
    await keyboard.click(screen.getByRole('button', { name: '注册账号' }))
    await keyboard.click(await screen.findByRole('link', { name: '前往登录' }))
    expect(await screen.findByRole('button', { name: '登录' })).toBeTruthy()
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
  it('通过me恢复普通用户会话并隐藏管理员菜单', async () => {
    mocked.mockResolvedValue(user)
    show('/dashboard')
    expect(await screen.findByRole('link', { name: '我的个人资料' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /^选手管理$/ })).toBeNull()
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
        ? user
        : options?.method === 'PATCH'
          ? { ...profile, nickname: '新昵称' }
          : profile,
    )
    show('/profile')
    const input = await screen.findByLabelText('选手昵称')
    const keyboard = userEvent.setup()
    await keyboard.clear(input)
    await keyboard.type(input, '新昵称')
    await keyboard.click(screen.getByRole('button', { name: '保存昵称' }))
    expect(await screen.findByText('选手昵称已保存。')).toBeTruthy()
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
    mocked.mockImplementation(async (path) => (path === '/auth/me/' ? user : { logged_out: true }))
    show('/dashboard')
    await userEvent.click(await screen.findByRole('button', { name: '退出' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy(),
    )
  })
})
