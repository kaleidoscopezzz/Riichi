// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ErrorBoundary } from './error-boundary'
import { Standings } from './competition-standings'
import { App } from '@/app'
import { ThemeProvider } from './theme-provider'
import { AuthContext } from './auth-context'
import { HealthContext } from './health-context'

const crash = vi.hoisted(() => ({ dashboard: false }))
vi.mock('@/pages/dashboard', async (original) => {
  const actual = await original<typeof import('@/pages/dashboard')>()
  return {
    ...actual,
    DashboardPage: () => {
      if (crash.dashboard) throw new Error('internal stack detail')
      return <actual.DashboardPage />
    },
  }
})

function Broken(): never {
  throw new Error('internal stack detail')
}
beforeEach(() => {
  crash.dashboard = false
  // React reports caught render errors to console.error; keep test output readable.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('应用级错误边界', () => {
  it('渲染异常显示中文友好错误页与重新加载按钮，不暴露内部信息', async () => {
    const reload = vi.fn()
    render(
      <ErrorBoundary reload={reload}>
        <Broken />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('heading', { name: '页面暂时无法显示' })).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('重新加载后即可继续操作')
    expect(document.body.textContent).not.toContain('internal stack detail')
    await userEvent.click(screen.getByRole('button', { name: '重新加载' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('resetKey 变化（如切换路由）后恢复正常渲染', () => {
    const view = render(
      <ErrorBoundary resetKey="/a">
        <Broken />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: '重新加载' })).toBeTruthy()
    view.rerender(
      <ErrorBoundary resetKey="/b">
        <p>恢复后的页面</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('恢复后的页面')).toBeTruthy()
  })

  it('App 内页面崩溃时不再整页白屏', () => {
    crash.dashboard = true
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ThemeProvider>
          <AuthContext.Provider
            value={{
              user: { id: 1, username: 'fixture', is_staff: true, date_joined: '' },
              loading: false,
              error: '',
              restore: vi.fn(),
              signIn: vi.fn(),
              signOut: vi.fn(),
            }}
          >
            <HealthContext.Provider
              value={{ status: 'connected', message: '正常', checkedAt: null, check: vi.fn() }}
            >
              <App />
            </HealthContext.Provider>
          </AuthContext.Provider>
        </ThemeProvider>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: '页面暂时无法显示' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeTruthy()
  })

  it('异常分数（分母为 0、负分母、负零）展示不抛异常', () => {
    render(
      <Standings
        completed={false}
        rows={[
          {
            participant_id: 1,
            display_name: '分母为零',
            rank: 1,
            total: { numerator: '5', denominator: '0' },
            confirmed_rounds: 0,
            first_count: 0,
            second_count: 0,
            rounds: [],
          },
          {
            participant_id: 2,
            display_name: '负分母',
            rank: 2,
            total: { numerator: '1', denominator: '-3' },
            confirmed_rounds: 0,
            first_count: 0,
            second_count: 0,
            rounds: [],
          },
          {
            participant_id: 3,
            display_name: '舍入为零',
            rank: 3,
            total: { numerator: '-1', denominator: '1000' },
            confirmed_rounds: 0,
            first_count: 0,
            second_count: 0,
            rounds: [],
          },
        ]}
      />,
    )
    const totals = [...document.querySelectorAll('td strong')].map((cell) => cell.textContent)
    expect(totals).toEqual(['—', '−0.33', '0.00'])
  })
})
