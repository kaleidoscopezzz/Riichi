// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RoundsPage } from './rounds'
import { TournamentRoundSummary } from '@/components/tournament-round-summary'
import { App } from '@/app'
import { ThemeProvider } from '@/components/theme-provider'
import { AuthContext } from '@/components/auth-context'
import { HealthContext } from '@/components/health-context'
import { ApiError } from '@/services/api'
import { fetchTournament, type Tournament } from '@/services/tournaments'
import {
  fetchRounds,
  fetchResources,
  generateRound,
  type TournamentRound,
  type RoundTable,
} from '@/services/rounds'
import {
  fetchWorkspace,
  saveResult,
  completeTournament,
  recordLottery,
  confirmLottery,
  replaceTable,
  type Workspace,
} from '@/services/competition'
vi.mock('@/services/tournaments', async (original) => ({
  ...(await original<typeof import('@/services/tournaments')>()),
  fetchTournament: vi.fn(),
}))
vi.mock('@/services/rounds', async (original) => ({
  ...(await original<typeof import('@/services/rounds')>()),
  fetchRounds: vi.fn(),
  fetchResources: vi.fn(),
  generateRound: vi.fn(),
}))
vi.mock('@/services/competition', async (original) => ({
  ...(await original<typeof import('@/services/competition')>()),
  fetchWorkspace: vi.fn(),
  saveResult: vi.fn(),
  completeTournament: vi.fn(),
  recordLottery: vi.fn(),
  confirmLottery: vi.fn(),
  replaceTable: vi.fn(),
}))
const date = '2026-11-04T08:00:00Z'
const t: Tournament = {
  id: 5,
  name: '测试夹具赛事',
  description: '',
  round_count: 3,
  starting_points: 25000,
  return_points: 30000,
  uma: ['30', '10', '-10', '-30'],
  oka: '20',
  status: 'started',
  created_by: 1,
  created_at: date,
  updated_at: date,
  started_at: date,
  participant_count: 4,
  expected_table_count: 1,
  participants: [],
}
const table: RoundTable = {
  id: 20,
  round_id: 6,
  round_number: 1,
  tournament_id: 5,
  table_number: 1,
  created_at: date,
  seats: (['east', 'south', 'west', 'north'] as const).map((w, i) => ({
    id: i + 1,
    participant_id: i + 1,
    player_id: i + 1,
    display_name: `快照选手${i + 1}`,
    seat_wind: w,
  })),
  active_allocation: null,
  allocation_history: [],
  machine_snapshot: { machine_id: 1, machine_no: '007' },
  result: { table_id: 20, version: 0, status: 'draft', points: {}, scores: [], confirmed_at: null },
}
const round: TournamentRound = {
  id: 6,
  tournament_id: 5,
  round_number: 1,
  generated_at: date,
  generated_by: 1,
  created_at: date,
  tables: [table],
}
const fraction = { numerator: '0', denominator: '1' }
const ws: Workspace = {
  status: 'started',
  resource_state: 'fixed',
  mapping: [
    {
      id: 1,
      ordinal: 1,
      label: 'A',
      machine_id: 1,
      machine_no: '007',
      name: '真实物理桌',
      history: [
        {
          id: 1,
          machine_id: 1,
          machine_no_snapshot: '007',
          status: 'active',
          source: 'legacy_bridge_v1',
          reason: '原记录继承',
        },
      ],
    },
  ],
  standings: table.seats.map((s) => ({
    participant_id: s.participant_id,
    display_name: s.display_name,
    rank: 1,
    total: fraction,
    confirmed_rounds: 0,
    first_count: 0,
    second_count: 0,
    rounds: [],
  })),
  unresolved_groups: [],
  ready: false,
  all_results_confirmed: false,
  source_versions: [],
  lotteries: [],
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchTournament).mockResolvedValue(t)
  vi.mocked(fetchRounds).mockResolvedValue({ results: [round] })
  vi.mocked(fetchResources).mockResolvedValue({
    results: [
      {
        machine_id: 1,
        machine_no: '007',
        name: '已占用',
        status: 'available',
        assignable: false,
        active_allocation: null,
      },
      {
        machine_id: 2,
        machine_no: '107',
        name: '空闲桌',
        status: 'available',
        assignable: true,
        active_allocation: null,
      },
      {
        machine_id: 3,
        machine_no: '207',
        name: '维护桌',
        status: 'maintenance',
        assignable: false,
        active_allocation: null,
      },
    ],
  })
  vi.mocked(fetchWorkspace).mockResolvedValue(ws)
  vi.mocked(generateRound).mockResolvedValue(round)
  vi.mocked(saveResult).mockResolvedValue({ ...table.result!, version: 1 })
  vi.mocked(recordLottery).mockResolvedValue({
    id: 10,
    members: [1, 2, 3, 4],
    order: [4, 3, 2, 1],
    method: '签条',
    description: '现场',
    confirmed_at: null,
  })
})
afterEach(cleanup)
function show() {
  return render(
    <MemoryRouter initialEntries={['/tournaments/5/rounds']}>
      <Routes>
        <Route path="/tournaments/:id/rounds" element={<RoundsPage />} />
      </Routes>
    </MemoryRouter>,
  )
}
function showApp(admin = false, anonymous = false) {
  return render(
    <MemoryRouter initialEntries={['/tournaments/5/rounds']}>
      <ThemeProvider>
        <AuthContext.Provider
          value={{
            user: anonymous
              ? null
              : { id: 1, username: 'fixture', is_staff: admin, date_joined: date },
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
describe('完整比赛工作台', () => {
  it('旧分配历史只读保留稳定ID、编号快照和释放审计', async () => {
    vi.mocked(fetchRounds).mockResolvedValue({
      results: [
        {
          ...round,
          tables: [
            {
              ...table,
              allocation_history: [
                {
                  id: 10,
                  table_id: 20,
                  machine_id: 1,
                  machine_no: '008',
                  machine_no_snapshot: '007',
                  machine_status: 'retired',
                  status: 'released',
                  allocated_at: date,
                  allocated_by: 1,
                  released_at: date,
                  released_by: 2,
                  release_reason: '旧版真实释放',
                },
              ],
            },
          ],
        },
      ],
    })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '旧版轮次分配历史' }))
    expect(screen.getByRole('dialog').textContent).toContain('原分配 ID #10')
    expect(screen.getByRole('dialog').textContent).toContain('旧版真实释放')
    expect(screen.getByRole('dialog').textContent).toContain('当前编号 008')
    await u.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
  it('读取已持久化四风、映射和累计榜', async () => {
    show()
    expect(screen.getByRole('status')).toBeTruthy()
    await screen.findByText('实时累计榜 · 暂列')
    expect(screen.getAllByText('逻辑桌 A').length).toBe(2)
    for (const w of ['东', '南', '西', '北']) expect(screen.getByText(w)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /释放第/ })).toBeNull()
  })
  it.each([4, 8, 12, 16])('%i人显示正确选桌数量', async (size) => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...t,
      participant_count: size,
      expected_table_count: size / 4,
    })
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '选择物理桌并生成首轮' }))
    for (let i = 0; i < size / 4; i++)
      expect(screen.getByLabelText(`逻辑桌 ${'ABCD'[i]} 物理桌`)).toBeTruthy()
  })
  it('首轮必须显式选桌，预览二次确认，取消不写入', async () => {
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '选择物理桌并生成首轮' }))
    expect(screen.getByRole('button', { name: '预览并确认' }).hasAttribute('disabled')).toBe(true)
    await u.selectOptions(screen.getByLabelText('逻辑桌 A 物理桌'), '2')
    expect(screen.queryByRole('option', { name: /维护桌/ })).toBeNull()
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    expect(generateRound).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '取消' }))
    expect(generateRound).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '选择物理桌并生成首轮' }))
    await u.selectOptions(screen.getByLabelText('逻辑桌 A 物理桌'), '2')
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    await u.click(screen.getByRole('button', { name: '确认生成轮次' }))
    await waitFor(() => expect(generateRound).toHaveBeenCalledWith(5, 1, [2]))
  })
  it('生成请求未完成时禁止重复提交', async () => {
    let resolve!: (r: TournamentRound) => void
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    vi.mocked(generateRound).mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '选择物理桌并生成首轮' }))
    await u.selectOptions(screen.getByLabelText('逻辑桌 A 物理桌'), '2')
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    await u.click(screen.getByRole('button', { name: '确认生成轮次' }))
    expect(screen.getByRole('button', { name: '正在提交…' }).hasAttribute('disabled')).toBe(true)
    expect(generateRound).toHaveBeenCalledTimes(1)
    resolve(round)
  })
  it('草稿赛事不提供分桌入口', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, status: 'draft' })
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    await screen.findByText('赛事尚未启动')
    expect(screen.queryByRole('button', { name: '选择物理桌并生成首轮' })).toBeNull()
  })
  it('支持部分草稿、负数零、异常总和阻止确认', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    await u.type(screen.getByLabelText('快照选手1 终局点数'), '-1000')
    await u.type(screen.getByLabelText('快照选手2 终局点数'), '0')
    expect(screen.getByRole('button', { name: '确认成绩' }).hasAttribute('disabled')).toBe(true)
    await u.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    await waitFor(() =>
      expect(saveResult).toHaveBeenCalledWith(
        20,
        0,
        [
          { participant_id: 1, raw_points: -1000 },
          { participant_id: 2, raw_points: 0 },
          { participant_id: 3, raw_points: null },
          { participant_id: 4, raw_points: null },
        ],
        false,
      ),
    )
  })
  it('总和正确后二次确认，后端权威计分', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    for (const [i, p] of [-1000, 0, 51000, 50000].entries())
      await u.type(screen.getByLabelText(`快照选手${i + 1} 终局点数`), String(p))
    await u.click(screen.getByRole('button', { name: '确认成绩' }))
    expect(saveResult).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '再次确认并锁定成绩' }))
    await waitFor(() => expect(saveResult).toHaveBeenCalledWith(20, 0, expect.any(Array), true))
  })
  it('非法小数不可保存，不将显示近似值用于排序', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    await u.type(screen.getByLabelText('快照选手1 终局点数'), '1.5')
    await u.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('整数')
    expect(saveResult).not.toHaveBeenCalled()
  })
  it('409反馈保留表单且不自动重放', async () => {
    vi.mocked(saveResult).mockRejectedValueOnce(new ApiError(409, 'stale_result', '成绩版本已变化'))
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    await u.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    expect((await screen.findByRole('alert')).textContent).toContain('成绩版本已变化')
    expect(saveResult).toHaveBeenCalledTimes(1)
  })
  it('前轮未确认禁止下一轮，确认后生成沿用映射', async () => {
    const page = show()
    await screen.findByText('实时累计榜 · 暂列')
    expect(screen.getByRole('button', { name: '生成第 2 轮' }).hasAttribute('disabled')).toBe(true)
    page.unmount()
    vi.mocked(fetchRounds).mockResolvedValue({
      results: [
        { ...round, tables: [{ ...table, result: { ...table.result!, status: 'confirmed' } }] },
      ],
    })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '生成第 2 轮' }))
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    await u.click(screen.getByRole('button', { name: '确认生成轮次' }))
    await waitFor(() => expect(generateRound).toHaveBeenCalledWith(5, 2, undefined))
  })
  it('故障换桌必须空闲目标和原因，历史可查', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '占用历史' }))
    expect(await screen.findByText('原记录继承')).toBeTruthy()
    await u.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await u.click(screen.getByRole('button', { name: '故障换桌' }))
    await u.selectOptions(screen.getByLabelText('目标空闲物理桌'), '2')
    await u.type(screen.getByLabelText('故障及替换原因'), '设备故障')
    await u.click(screen.getByRole('button', { name: '预览替换' }))
    await u.click(screen.getByRole('button', { name: '确认故障替换' }))
    await waitFor(() => expect(replaceTable).toHaveBeenCalledWith(5, 1, 2, '设备故障'))
  })
  it('最终全同公开抽签，记录后二次确认才能完赛', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, round_count: 1 })
    vi.mocked(fetchWorkspace).mockResolvedValue({
      ...ws,
      all_results_confirmed: true,
      unresolved_groups: [[1, 2, 3, 4]],
    })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '记录公开抽签 1' }))
    for (let i = 0; i < 4; i++)
      await u.selectOptions(screen.getByLabelText(`抽签顺位 ${i + 1}`), String(4 - i))
    await u.type(screen.getByLabelText('抽签方式'), '现场签条')
    await u.type(screen.getByLabelText('实际抽签时间'), '2026-11-04T12:00')
    await u.type(screen.getByLabelText('公开过程说明'), '全员公开监督')
    await u.click(screen.getByRole('button', { name: '保存公开抽签记录' }))
    await screen.findByRole('button', { name: '二次确认抽签顺序' })
    expect(confirmLottery).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '二次确认抽签顺序' }))
    await waitFor(() => expect(confirmLottery).toHaveBeenCalledWith(5, 10))
  })
  it('完赛二次确认提交来源版本，完赛后刷新显示冠军', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, round_count: 1 })
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...ws, ready: true, all_results_confirmed: true })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '正式完赛' }))
    expect(completeTournament).not.toHaveBeenCalled()
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, status: 'completed' })
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...ws, status: 'completed', champion_id: 2 })
    await u.click(screen.getByRole('button', { name: '确认完赛并释放本场物理桌' }))
    await screen.findByText('CHAMPION / 个人冠军')
    expect(completeTournament).toHaveBeenCalledWith(5, [])
  })
  it('失败可刷新，恢复服务端座次，不重排', async () => {
    vi.mocked(fetchRounds).mockRejectedValueOnce(new Error('读取失败'))
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '重新加载工作台' }))
    await screen.findByText('实时累计榜 · 暂列')
    expect(generateRound).not.toHaveBeenCalled()
  })
  it('普通用户与匿名路由守卫保留', async () => {
    const page = showApp()
    expect(screen.getByRole('heading', { name: '无权访问' })).toBeTruthy()
    page.unmount()
    showApp(false, true)
    expect(await screen.findByLabelText('用户名')).toBeTruthy()
  })
  it('详情摘要只读取真实API', async () => {
    vi.mocked(fetchRounds).mockResolvedValue({
      results: [{ ...round, tables: [{ ...table, active_allocation: { id: 1 } as never }] }],
    })
    render(<TournamentRoundSummary id={5} />)
    await screen.findByText('1 台')
    expect(screen.getByText('1 轮')).toBeTruthy()
  })
})
