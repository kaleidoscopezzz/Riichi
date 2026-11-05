// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { selectOption } from '@/test/select-option'
import { MemoryRouter } from 'react-router-dom'
import { TournamentsPage } from './tournaments'
import { App } from '@/app'
import { AuthContext } from '@/components/auth-context'
import { HealthContext } from '@/components/health-context'
import { ThemeProvider } from '@/components/theme-provider'
import { ApiError } from '@/services/api'
import {
  fetchTournaments,
  fetchTournament,
  saveTournament,
  startTournament,
  findPlayers,
  previewOka,
  type Tournament,
  type Page,
} from '@/services/tournaments'

vi.mock('@/services/tournaments', async (original) => ({
  ...(await original<typeof import('@/services/tournaments')>()),
  fetchTournaments: vi.fn(),
  fetchTournament: vi.fn(),
  saveTournament: vi.fn(),
  startTournament: vi.fn(),
  findPlayers: vi.fn(),
}))
const row: Tournament = {
  id: 1,
  name: '验证个人赛',
  description: '自动化测试夹具',
  round_count: 3,
  starting_points: 25000,
  return_points: 30000,
  uma: ['30', '10', '-10', '-30'],
  oka: '20',
  status: 'draft',
  created_by: 1,
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
  started_at: null,
  participant_count: 4,
  expected_table_count: 1,
  participants: [1, 2, 3, 4].map((id) => ({
    id,
    player_id: id,
    display_name: `选手${id}`,
    username: `user${id}`,
    is_active: true,
    display_name_snapshot: '',
  })),
}
const page = (rows = [row]): Page<Tournament> => ({
  count: rows.length,
  next: null,
  previous: null,
  results: rows,
})
const players = [1, 2, 3, 4].map((id) => ({
  id,
  nickname: `选手${id}`,
  username: `user${id}`,
  is_active: true,
  created_at: row.created_at,
  updated_at: row.created_at,
  date_joined: row.created_at,
}))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchTournaments).mockResolvedValue(page())
  vi.mocked(fetchTournament).mockResolvedValue(row)
  vi.mocked(saveTournament).mockResolvedValue(row)
  vi.mocked(startTournament).mockResolvedValue({
    ...row,
    status: 'started',
    started_at: row.created_at,
  })
  vi.mocked(findPlayers).mockResolvedValue({
    count: 4,
    next: null,
    previous: null,
    results: players,
  })
})
afterEach(cleanup)
async function openDetail() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '查看赛事 验证个人赛' }))
  await screen.findByRole('dialog')
  return user
}
function showApp(path: string, admin = false, anonymous = false) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ThemeProvider>
        <AuthContext.Provider
          value={{
            user: anonymous
              ? null
              : { id: 1, username: 'test-only', is_staff: admin, date_joined: row.created_at },
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

describe('赛事工作台', () => {
  it('API加载状态、真实列表及搜索分页', async () => {
    vi.mocked(fetchTournaments).mockResolvedValueOnce({ ...page(), next: '/next' })
    render(<TournamentsPage />)
    const user = userEvent.setup()
    expect(screen.getByRole('status').textContent).toContain('正在加载')
    await screen.findByText(row.name)
    await user.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() =>
      expect(fetchTournaments).toHaveBeenLastCalledWith(2, '', '', expect.any(AbortSignal)),
    )
    await user.type(screen.getByLabelText('搜索赛事名称'), '冬季')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() =>
      expect(fetchTournaments).toHaveBeenLastCalledWith(1, '冬季', '', expect.any(AbortSignal)),
    )
    await selectOption(user, '状态筛选', '已启动')
    await waitFor(() =>
      expect(fetchTournaments).toHaveBeenLastCalledWith(
        1,
        '冬季',
        'started',
        expect.any(AbortSignal),
      ),
    )
  })
  it('创建表单校验、精确Oka和原子草稿提交', async () => {
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect(screen.getByRole('alert').textContent).toContain('有效十进制')
    expect(saveTournament).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('赛事名称'), '新赛事')
    const start = screen.getByLabelText('开局点数')
    await user.clear(start)
    await user.type(start, '25001')
    expect(screen.getByText('+19.996')).toBeTruthy()
    const uma = screen.getByLabelText('第 1 名 Uma')
    await user.clear(uma)
    await user.type(uma, 'NaN')
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect(saveTournament).not.toHaveBeenCalled()
    await user.clear(uma)
    await user.type(uma, '30.125')
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '新赛事',
          starting_points: 25001,
          uma: ['30.125', '10', '-10', '-30'],
          participant_ids: [],
        }),
        undefined,
      ),
    )
  })
  it('选手分页搜索、去重和已选移除', async () => {
    vi.mocked(findPlayers).mockResolvedValue({
      count: 21,
      next: '/next',
      previous: null,
      results: players,
    })
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.click(screen.getByRole('combobox', { name: '搜索参赛选手' }))
    await user.click(await screen.findByRole('option', { name: /选手1.*选手 #1/ }))
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '加载更多选手' }))
    await waitFor(() =>
      expect(findPlayers).toHaveBeenLastCalledWith(2, '', expect.any(AbortSignal)),
    )
    await user.type(screen.getByLabelText('搜索参赛选手'), '选手1')
    await waitFor(() =>
      expect(findPlayers).toHaveBeenLastCalledWith(1, '选手1', expect.any(AbortSignal)),
    )
    await user.click(screen.getByRole('option', { name: /选手1.*选手 #1/ }))
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '移除 选手1（选手 #1）' }))
    expect(screen.getByText('已选 0 / 16 人')).toBeTruthy()
  })
  it('编辑草稿将配置及名单放在同一请求', async () => {
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '编辑草稿' }))
    await user.click(screen.getByRole('button', { name: '移除 选手1（选手 #1）' }))
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenCalledWith(
        expect.objectContaining({ participant_ids: [2, 3, 4] }),
        1,
      ),
    )
  })
  it('非法人数不能启动', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...row,
      participant_count: 3,
      participants: row.participants.slice(0, 3),
      expected_table_count: null,
    })
    render(<TournamentsPage />)
    await openDetail()
    expect(screen.getByRole('button', { name: '启动前检查' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('启动条件尚未满足')).toBeTruthy()
  })
  it('启动需要确认，取消不写API；成功冻结', async () => {
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '启动前检查' }))
    await screen.findByText('确认启动赛事')
    expect(startTournament).not.toHaveBeenCalled()
    expect(screen.getByText(/启动后规则和名单无法修改/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '暂不启动' }))
    expect(startTournament).not.toHaveBeenCalled()
    await openDetail()
    await user.click(screen.getByRole('button', { name: '启动前检查' }))
    await user.click(await screen.findByRole('button', { name: '确认启动并冻结' }))
    await waitFor(() => expect(startTournament).toHaveBeenCalledWith(1))
    expect((await screen.findByRole('status')).textContent).toContain('规则与名单已冻结')
  })
  it('已启动详情只读及昵称快照', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...row,
      status: 'started',
      started_at: row.created_at,
    })
    render(<TournamentsPage />)
    await openDetail()
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByText('选手1')).toBeTruthy()
    expect(dialog.queryByRole('button', { name: '编辑草稿' })).toBeNull()
    expect(dialog.queryByRole('button', { name: '启动前检查' })).toBeNull()
  })
  it('API字段错误反馈、列表失败重试与空状态', async () => {
    vi.mocked(fetchTournaments)
      .mockRejectedValueOnce(new Error('网络不可用'))
      .mockResolvedValueOnce(page([]))
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: '重新加载' }))
    await screen.findByText('第一场赛事，从这里开始')
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.type(screen.getByLabelText('赛事名称'), '测试')
    vi.mocked(saveTournament).mockRejectedValueOnce(
      new ApiError(400, 'invalid', '输入有误', { participant_ids: ['账号已停用'] }),
    )
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('参赛名单：账号已停用')
  })
  it('启动冲突可见，不自动重试', async () => {
    vi.mocked(startTournament).mockRejectedValueOnce(
      new ApiError(409, 'already_started', '赛事已经启动'),
    )
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '启动前检查' }))
    await user.click(await screen.findByRole('button', { name: '确认启动并冻结' }))
    expect((await screen.findByRole('alert')).textContent).toContain('赛事已经启动')
    expect(startTournament).toHaveBeenCalledTimes(1)
  })
  it('精确Oka支持负值与小数', () => {
    expect(previewOka('25001', '30000')).toBe('+19.996')
    expect(previewOka('30000', '25000')).toBe('-20')
    expect(previewOka('', '1')).toBe('—')
  })
  it('普通用户菜单不显示赛事且直达拒绝', async () => {
    const app = showApp('/dashboard')
    expect(screen.queryByRole('link', { name: '赛事管理' })).toBeNull()
    expect(screen.queryByRole('link', { name: '进入赛事管理' })).toBeNull()
    app.unmount()
    showApp('/tournaments')
    expect(screen.getByRole('heading', { name: '无权访问' })).toBeTruthy()
    expect(fetchTournaments).not.toHaveBeenCalled()
  })
  it('匿名跳转登录，管理员可以读取赛事', async () => {
    const app = showApp('/tournaments', false, true)
    expect(await screen.findByLabelText('用户名')).toBeTruthy()
    app.unmount()
    showApp('/tournaments', true)
    expect(await screen.findByText(row.name)).toBeTruthy()
  })
})
