// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { MachinesPage } from './machines'
import { App } from '@/app'
import { AuthContext } from '@/components/auth-context'
import { HealthContext } from '@/components/health-context'
import { ThemeProvider } from '@/components/theme-provider'
import { ApiError } from '@/services/api'
import {
  fetchMachines,
  fetchMachine,
  saveMachine,
  retireMachine,
  type Machine,
  type MachinePage,
} from '@/services/machines'

vi.mock('@/services/machines', async (original) => ({
  ...(await original<typeof import('@/services/machines')>()),
  fetchMachines: vi.fn(),
  fetchMachine: vi.fn(),
  saveMachine: vi.fn(),
  retireMachine: vi.fn(),
}))
const machine: Machine = {
  id: 9,
  machine_no: '107',
  name: '验证设备',
  location: '验证区域',
  status: 'available',
  description: '仅测试夹具',
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
}
function page(rows: Machine[] = [machine], active = 1): MachinePage {
  return {
    count: rows.length,
    next: null,
    previous: null,
    results: rows,
    summary: {
      active,
      available: active,
      maintenance: 0,
      disabled: 0,
      retired: rows.filter((row) => row.status === 'retired').length,
    },
  }
}
const list = vi.mocked(fetchMachines),
  detail = vi.mocked(fetchMachine),
  save = vi.mocked(saveMachine),
  retire = vi.mocked(retireMachine)
beforeEach(() => {
  vi.clearAllMocks()
  list.mockResolvedValue(page())
  detail.mockResolvedValue(machine)
  save.mockResolvedValue(machine)
  retire.mockResolvedValue({ ...machine, status: 'retired' })
})
afterEach(cleanup)
async function openNew() {
  const user = userEvent.setup()
  await screen.findByRole('button', { name: '新建设备' })
  await waitFor(() =>
    expect(screen.getByRole('button', { name: '新建设备' }).hasAttribute('disabled')).toBe(false),
  )
  await user.click(screen.getByRole('button', { name: '新建设备' }))
  return user
}
function showApp(path: string, admin = false, anonymous = false) {
  const user = anonymous
    ? null
    : { id: 1, username: 'test-only-user', is_staff: admin, date_joined: machine.created_at }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ThemeProvider>
        <AuthContext.Provider
          value={{
            user,
            loading: false,
            error: '',
            restore: vi.fn(),
            signIn: vi.fn(),
            signOut: vi.fn(),
          }}
        >
          <HealthContext.Provider
            value={{ status: 'connected', message: '正常', checkedAt: new Date(), check: vi.fn() }}
          >
            <App />
          </HealthContext.Provider>
        </AuthContext.Provider>
      </ThemeProvider>
    </MemoryRouter>,
  )
}

describe('设备管理工作台', () => {
  it('读取真实API契约并显示加载与设备列表', async () => {
    let resolve!: (value: MachinePage) => void
    list.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done
      }),
    )
    render(<MachinesPage />)
    expect(screen.getByRole('status').textContent).toContain('正在加载')
    resolve(page())
    expect(await screen.findByText('验证设备')).toBeTruthy()
    expect(list).toHaveBeenCalledWith(1, '', '', expect.any(AbortSignal))
    expect(screen.getByRole('table', { name: '设备列表' })).toBeTruthy()
  })
  it('新建表单拒绝编号和空白名称', async () => {
    render(<MachinesPage />)
    const user = await openNew()
    await user.type(screen.getByLabelText('设备编号'), 'abc')
    await user.type(screen.getByLabelText('设备名称'), '新设备')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(await screen.findByText('设备编号必须为 1～3 位数字。')).toBeTruthy()
    await user.clear(screen.getByLabelText('设备编号'))
    await user.type(screen.getByLabelText('设备编号'), '8')
    await user.clear(screen.getByLabelText('设备名称'))
    await user.type(screen.getByLabelText('设备名称'), '   ')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(await screen.findByText('设备名称不能为空。')).toBeTruthy()
    expect(save).not.toHaveBeenCalled()
  })
  it('新建设备成功，刷新列表并恢复按钮焦点', async () => {
    render(<MachinesPage />)
    const user = await openNew()
    await user.type(screen.getByLabelText('设备编号'), '8')
    await user.type(screen.getByLabelText('设备名称'), '新设备')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(await screen.findByText('设备 107 已保存。')).toBeTruthy()
    expect(save).toHaveBeenCalledWith(
      { machine_no: '8', name: '新设备', location: '', description: '', status: 'available' },
      undefined,
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(list.mock.calls.length).toBeGreaterThan(1)
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: '新建设备' })),
    )
  })
  it('先获取设备详情，再编辑资料和状态', async () => {
    render(<MachinesPage />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '编辑设备 107' }))
    await screen.findByRole('dialog', { name: '编辑设备' })
    expect(detail).toHaveBeenCalledWith(9)
    await user.clear(screen.getByLabelText('设备名称'))
    await user.type(screen.getByLabelText('设备名称'), '检修设备')
    await user.selectOptions(screen.getByLabelText('设备状态'), 'maintenance')
    await user.click(screen.getByRole('button', { name: '保存修改' }))
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        expect.objectContaining({ name: '检修设备', status: 'maintenance' }),
        9,
      ),
    )
  })
  it('容量已满时禁用创建，并解释维护停用也占容量', async () => {
    list.mockResolvedValue(page([machine], 4))
    render(<MachinesPage />)
    await screen.findByText('现役容量已满')
    expect(screen.getByRole('button', { name: '新建设备' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('维护中与停用设备同样占用容量')).toBeTruthy()
  })
  it('退役需要明确确认，取消不会发送请求', async () => {
    render(<MachinesPage />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '退役设备 107' }))
    const dialog = await screen.findByRole('dialog', { name: '确认退役设备' })
    expect(within(dialog).getByText(/此操作不可直接撤销/)).toBeTruthy()
    expect(retire).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '取消退役' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(retire).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '退役设备 107' }))
    await user.click(await screen.findByRole('button', { name: '确认退役' }))
    expect(await screen.findByText('设备 107 已退役，历史档案已保留。')).toBeTruthy()
    expect(retire).toHaveBeenCalledWith(9)
  })
  it('已退役设备仅能查看，不提供编辑或恢复', async () => {
    const historical = { ...machine, status: 'retired' as const }
    list.mockResolvedValue(page([historical], 0))
    detail.mockResolvedValue(historical)
    render(<MachinesPage />)
    await screen.findByText('验证设备')
    expect(screen.queryByRole('button', { name: '编辑设备 107' })).toBeNull()
    expect(screen.queryByRole('button', { name: '退役设备 107' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '查看设备 107 详情' }))
    await screen.findByText('已退役 · 历史资料只读，不能重新启用。')
    expect(screen.queryByRole('button', { name: '保存修改' })).toBeNull()
  })
  it('编号名称搜索与状态筛选重置分页', async () => {
    render(<MachinesPage />)
    await screen.findByText('验证设备')
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('搜索设备编号或名称'), '  107 ')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(1, '107', '', expect.any(AbortSignal)),
    )
    await user.selectOptions(screen.getByLabelText('状态筛选'), 'retired')
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(1, '107', 'retired', expect.any(AbortSignal)),
    )
  })
  it('展示服务端字段错误，保留表单', async () => {
    save.mockRejectedValue(
      new ApiError(400, 'validation_error', '输入有误', { machine_no: ['编号冲突'] }),
    )
    render(<MachinesPage />)
    const user = await openNew()
    await user.type(screen.getByLabelText('设备编号'), '8')
    await user.type(screen.getByLabelText('设备名称'), '设备')
    await user.click(screen.getByRole('button', { name: '创建设备' }))
    expect(await screen.findByText('设备编号：编号冲突')).toBeTruthy()
    expect(screen.getByRole('dialog')).toBeTruthy()
  })
  it('列表网络错误可重试，空数据不伪造统计', async () => {
    list.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValueOnce(page([], 0))
    render(<MachinesPage />)
    await userEvent.click(await screen.findByRole('button', { name: '重新加载' }))
    expect(await screen.findByText('还没有设备档案')).toBeTruthy()
    expect(screen.queryByText('验证设备')).toBeNull()
  })
  it('Esc可关闭未保存表单，键盘焦点返回创建入口', async () => {
    render(<MachinesPage />)
    const user = await openNew()
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})

describe('设备路由权限', () => {
  it('普通用户直接访问设备页面被拒绝，且不读取设备', async () => {
    showApp('/machines')
    expect(await screen.findByRole('heading', { name: '无权访问' })).toBeTruthy()
    expect(list).not.toHaveBeenCalled()
  })
  it('普通用户导航和仪表盘不显示设备入口', async () => {
    showApp('/dashboard')
    expect(await screen.findByRole('heading', { name: '仪表盘' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /麻将机管理/ })).toBeNull()
  })
  it('匿名用户跳转登录', async () => {
    showApp('/machines', false, true)
    expect(await screen.findByRole('heading', { name: '欢迎回到 Riichi' })).toBeTruthy()
    expect(list).not.toHaveBeenCalled()
  })
  it('管理员可以访问设备页面', async () => {
    showApp('/machines', true)
    expect(await screen.findByRole('heading', { name: '设备台账' })).toBeTruthy()
    expect(await screen.findByText('验证设备')).toBeTruthy()
  })
})
