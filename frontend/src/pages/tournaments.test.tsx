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
  oka_override: null,
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
    is_active: true,
    display_name_snapshot: '',
  })),
  revision: 1,
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
  it('自定义 0 保存为无头名赏，开局和返还原点保持独立', async () => {
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.type(screen.getByLabelText('赛事名称'), '无头名赏赛事')
    expect(screen.queryByLabelText('头名赏 Oka')).toBeNull()
    await selectOption(user, '头名赏设置', '自定义（可为 0）')
    expect((screen.getByLabelText('头名赏 Oka') as HTMLInputElement).value).toBe('0')
    expect(screen.getByText('0（无头名赏）')).toBeTruthy()
    expect(screen.getByText(/四人积分合计可能不为 0/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenCalledWith(
        expect.objectContaining({
          oka_override: '0',
          starting_points: 25000,
          return_points: 30000,
        }),
        undefined,
      ),
    )
  })
  it('编辑已保存的零头名赏，可精确保存自定义小数且不随点数变化', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({ ...row, oka: '0', oka_override: '0' })
    render(<TournamentsPage />)
    const user = await openDetail()
    expect(screen.getByText('头名赏 Oka · 自定义')).toBeTruthy()
    expect(screen.getByText('0（无头名赏）')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '编辑草稿' }))
    expect(screen.getByRole('combobox', { name: '头名赏设置' }).textContent).toContain('自定义')
    const input = screen.getByLabelText('头名赏 Oka')
    const value = '12.123456789012345678901234567890123456789'
    await user.clear(input)
    await user.type(input, value)
    await user.clear(screen.getByLabelText('开局点数'))
    await user.type(screen.getByLabelText('开局点数'), '26000')
    expect((input as HTMLInputElement).value).toBe(value)
    expect(screen.getByText(value)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenCalledWith(
        expect.objectContaining({
          oka_override: value,
          starting_points: 26000,
          return_points: 30000,
          revision: 1,
        }),
        row.id,
      ),
    )
  })
  it('切回自动推导时提交 null，并恢复精确点差预览', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...row,
      oka: '0',
      oka_override: '0',
      starting_points: 25001,
    })
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '编辑草稿' }))
    await selectOption(user, '头名赏设置', '自动推导')
    expect(screen.queryByLabelText('头名赏 Oka')).toBeNull()
    expect(screen.getByText('+19.996')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenCalledWith(
        expect.objectContaining({ oka_override: null, starting_points: 25001 }),
        row.id,
      ),
    )
  })
  it('自定义 Oka 拒绝空值、负数、科学计数法和非有限数', async () => {
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.type(screen.getByLabelText('赛事名称'), '严格 Oka 校验')
    await selectOption(user, '头名赏设置', '自定义（可为 0）')
    const input = screen.getByLabelText('头名赏 Oka')
    for (const invalid of ['', '-1', '1e3', 'NaN', 'Infinity', '1/3']) {
      await user.clear(input)
      if (invalid) await user.type(input, invalid)
      await user.click(screen.getByRole('button', { name: '保存草稿' }))
      expect(screen.getByRole('alert').textContent).toContain('非负十进制数')
      expect(saveTournament).not.toHaveBeenCalled()
    }
    expect(input.getAttribute('maxlength')).toBe('64')
  })
  it('Oka 的服务端字段错误以中文显示，保留当前输入供修正', async () => {
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.type(screen.getByLabelText('赛事名称'), '配置错误反馈')
    await selectOption(user, '头名赏设置', '自定义（可为 0）')
    vi.mocked(saveTournament).mockRejectedValueOnce(
      new ApiError(400, 'invalid', '输入有误', { oka_override: ['无效的头名赏。'] }),
    )
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('头名赏 Oka：无效的头名赏。')
    expect((screen.getByLabelText('头名赏 Oka') as HTMLInputElement).value).toBe('0')
  })
  it('启动前确认与启动后详情显示实际的零头名赏', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({ ...row, oka: '0', oka_override: '0' })
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '启动前检查' }))
    expect(screen.getByText('0（无头名赏）')).toBeTruthy()
    expect(screen.getByText('头名赏 Oka · 自定义')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '暂不启动' }))
    vi.mocked(fetchTournament).mockResolvedValue({
      ...row,
      status: 'started',
      oka: '0',
      oka_override: '0',
    })
    await openDetail()
    expect(screen.getByText('0（无头名赏）')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '编辑草稿' })).toBeNull()
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

describe('草稿乐观并发与参赛者契约（F9）', () => {
  it('保存草稿带上 revision；409 stale_tournament 提示后端消息并可载入最新草稿', async () => {
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '编辑草稿' }))
    vi.mocked(saveTournament).mockRejectedValueOnce(
      new ApiError(409, 'stale_tournament', '赛事草稿已被他人修改，请刷新后再保存。'),
    )
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect(saveTournament).toHaveBeenLastCalledWith(
      expect.objectContaining({ revision: 1, participant_ids: [1, 2, 3, 4] }),
      1,
    )
    expect((await screen.findByRole('alert')).textContent).toContain('赛事草稿已被他人修改')
    vi.mocked(fetchTournament).mockResolvedValueOnce({
      ...row,
      name: '他人修改后的赛事',
      revision: 2,
      participants: row.participants.slice(0, 2),
      participant_count: 2,
      oka: '0',
      oka_override: '0',
    })
    await user.click(screen.getByRole('button', { name: '重新加载最新草稿' }))
    expect(((await screen.findByLabelText('赛事名称')) as HTMLInputElement).value).toBe(
      '他人修改后的赛事',
    )
    expect(await screen.findByText(/已载入最新草稿/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '重新加载最新草稿' })).toBeNull()
    expect(screen.getByText('已选 2 / 16 人')).toBeTruthy()
    expect((screen.getByLabelText('头名赏 Oka') as HTMLInputElement).value).toBe('0')
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await waitFor(() =>
      expect(saveTournament).toHaveBeenLastCalledWith(
        expect.objectContaining({
          name: '他人修改后的赛事',
          revision: 2,
          participant_ids: [1, 2],
          oka_override: '0',
        }),
        1,
      ),
    )
  })
  it('其他 409 不显示重新加载入口；新建草稿不带 revision', async () => {
    render(<TournamentsPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '创建赛事' }))
    await user.type(screen.getByLabelText('赛事名称'), '新赛事')
    vi.mocked(saveTournament).mockRejectedValueOnce(
      new ApiError(409, 'tournament_frozen', '赛事已启动，配置和名单已冻结。'),
    )
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('已冻结')
    expect(screen.queryByRole('button', { name: '重新加载最新草稿' })).toBeNull()
    expect(vi.mocked(saveTournament).mock.calls[0][0]).not.toHaveProperty('revision')
  })
  it('载入时发现赛事已启动则提示不可编辑，并禁用保存', async () => {
    render(<TournamentsPage />)
    const user = await openDetail()
    await user.click(screen.getByRole('button', { name: '编辑草稿' }))
    vi.mocked(saveTournament).mockRejectedValueOnce(
      new ApiError(409, 'stale_tournament', '赛事草稿已被他人修改，请刷新后再保存。'),
    )
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    vi.mocked(fetchTournament).mockResolvedValueOnce({ ...row, status: 'started', revision: 3 })
    await user.click(await screen.findByRole('button', { name: '重新加载最新草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('已不是草稿')
    expect(screen.getByRole('button', { name: '保存草稿' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('combobox', { name: '头名赏设置' }).hasAttribute('disabled')).toBe(true)
  })
  it('参赛者详情不依赖内部用户名', async () => {
    render(<TournamentsPage />)
    await openDetail()
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByText('选手1')).toBeTruthy()
    expect(dialog.queryByText(/user\d/)).toBeNull()
    expect(row.participants[0]).not.toHaveProperty('username')
  })
})
