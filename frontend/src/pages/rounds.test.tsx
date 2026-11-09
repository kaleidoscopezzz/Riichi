// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { selectOption } from '@/test/select-option'
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
  previewResult,
  correctResult,
  fetchResult,
  fetchResultCorrections,
  completeTournament,
  recordLottery,
  confirmLottery,
  voidLottery,
  replaceTable,
  reviewLegacy,
  type Lottery,
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
  previewResult: vi.fn(),
  correctResult: vi.fn(),
  fetchResult: vi.fn(),
  fetchResultCorrections: vi.fn(),
  completeTournament: vi.fn(),
  recordLottery: vi.fn(),
  confirmLottery: vi.fn(),
  voidLottery: vi.fn(),
  replaceTable: vi.fn(),
  reviewLegacy: vi.fn(),
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
  oka_override: null,
  status: 'started',
  created_by: 1,
  created_at: date,
  updated_at: date,
  started_at: date,
  participant_count: 4,
  expected_table_count: 1,
  participants: [],
  revision: 1,
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
          release_reason: '',
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
  vi.mocked(previewResult).mockResolvedValue({
    table_id: table.id,
    version: 0,
    complete: false,
    valid_total: false,
    total: '0',
    expected_total: '100000',
    difference: '-100000',
    scores: [],
  })
  vi.mocked(correctResult).mockResolvedValue({
    ...table.result!,
    version: 2,
    status: 'confirmed',
    correction_count: 1,
  })
  vi.mocked(fetchResult).mockResolvedValue(table.result!)
  vi.mocked(fetchResultCorrections).mockResolvedValue({ table_id: table.id, corrections: [] })
  vi.mocked(recordLottery).mockResolvedValue({
    id: 10,
    members: [1, 2, 3, 4],
    order: [4, 3, 2, 1],
    method: '签条',
    description: '现场',
    drawn_at: date,
    created_by_id: 1,
    created_at: date,
    confirmed_by_id: null,
    confirmed_at: null,
    voided_by_id: null,
    voided_at: null,
    void_reason: '',
    source_versions: [],
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
    await selectOption(u, '逻辑桌 A 物理桌', '107 · 空闲桌')
    expect(screen.queryByRole('option', { name: /维护桌/ })).toBeNull()
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    expect(generateRound).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '取消' }))
    expect(generateRound).not.toHaveBeenCalled()
    await u.click(screen.getByRole('button', { name: '选择物理桌并生成首轮' }))
    await selectOption(u, '逻辑桌 A 物理桌', '107 · 空闲桌')
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
    await selectOption(u, '逻辑桌 A 物理桌', '107 · 空闲桌')
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
    await u.click(screen.getByRole('button', { name: '再次确认成绩' }))
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
    await selectOption(u, '目标空闲物理桌', '107 · 空闲桌')
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
    for (let i = 0; i < 4; i++) await selectOption(u, `抽签顺位 ${i + 1}`, `快照选手${4 - i}`)
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
describe('进行中前轮成绩更正', () => {
  function prepare(confirmed = true) {
    const firstTable: RoundTable = {
      ...table,
      result: {
        ...table.result!,
        version: confirmed ? 1 : 0,
        status: confirmed ? 'confirmed' : 'draft',
        points: confirmed ? { '1': 40000, '2': 30000, '3': 20000, '4': 10000 } : {},
      },
    }
    const later: TournamentRound = {
      ...round,
      id: 7,
      round_number: 2,
      tables: [{ ...table, id: 21, round_id: 7, round_number: 2 }],
    }
    vi.mocked(fetchRounds).mockResolvedValue({
      results: [{ ...round, tables: [firstTable] }, later],
    })
    return { firstTable, later }
  }
  async function openFirst() {
    show()
    const user = userEvent.setup()
    await screen.findByRole('combobox', { name: '查看轮次' })
    await selectOption(user, '查看轮次', '第 1 轮')
    await user.click(screen.getByRole('button', { name: '更正第1轮第1桌成绩' }))
    return user
  }
  it('第二轮开始后仍可更正第一轮，保存后保持查看第一轮', async () => {
    const { firstTable, later } = prepare()
    const user = await openFirst()
    expect((screen.getByLabelText('快照选手1 终局点数') as HTMLInputElement).value).toBe('40000')
    await user.clear(screen.getByLabelText('快照选手1 终局点数'))
    await user.type(screen.getByLabelText('快照选手1 终局点数'), '35000')
    expect(screen.getByRole('button', { name: '保存更正' }).hasAttribute('disabled')).toBe(true)
    await user.clear(screen.getByLabelText('快照选手2 终局点数'))
    await user.type(screen.getByLabelText('快照选手2 终局点数'), '35000')
    vi.mocked(fetchRounds).mockResolvedValue({
      results: [
        {
          ...round,
          tables: [
            {
              ...firstTable,
              result: {
                ...firstTable.result!,
                version: 2,
                correction_count: 1,
                points: { '1': 35000, '2': 35000, '3': 20000, '4': 10000 },
              },
            },
          ],
        },
        later,
      ],
    })
    await user.click(screen.getByRole('button', { name: '保存更正' }))
    await waitFor(() =>
      expect(correctResult).toHaveBeenCalledWith(
        20,
        1,
        [
          { participant_id: 1, raw_points: 35000 },
          { participant_id: 2, raw_points: 35000 },
          { participant_id: 3, raw_points: 20000 },
          { participant_id: 4, raw_points: 10000 },
        ],
        '',
      ),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('combobox', { name: '查看轮次' }).textContent).toContain('第 1 轮')
    expect(await screen.findByText('已确认 · 更正 1 次')).toBeTruthy()
    expect(saveResult).not.toHaveBeenCalled()
  })
  it('更正拒绝空值与非法数字，允许全角负数和零', async () => {
    prepare()
    const user = await openFirst()
    const field = screen.getByLabelText('快照选手1 终局点数')
    await user.clear(field)
    expect(screen.getByRole('button', { name: '保存更正' }).hasAttribute('disabled')).toBe(true)
    await user.type(field, '-1.5')
    await user.tab()
    expect(field.getAttribute('aria-invalid')).toBe('true')
    expect(correctResult).not.toHaveBeenCalled()
    for (const [index, value] of ['-１０００', '0', '51000', '50000'].entries()) {
      const input = screen.getByLabelText(`快照选手${index + 1} 终局点数`)
      await user.clear(input)
      await user.type(input, value)
    }
    await user.click(screen.getByRole('button', { name: '保存更正' }))
    await waitFor(() =>
      expect(correctResult).toHaveBeenCalledWith(
        20,
        1,
        [
          { participant_id: 1, raw_points: -1000 },
          { participant_id: 2, raw_points: 0 },
          { participant_id: 3, raw_points: 51000 },
          { participant_id: 4, raw_points: 50000 },
        ],
        '',
      ),
    )
  })
  it('旧版本更正失败后不自动重试，载入最新值后使用新版本提交', async () => {
    const { firstTable } = prepare()
    const user = await openFirst()
    for (const [index, value] of ['35000', '35000'].entries()) {
      const input = screen.getByLabelText(`快照选手${index + 1} 终局点数`)
      await user.clear(input)
      await user.type(input, value)
    }
    vi.mocked(correctResult).mockRejectedValueOnce(
      new ApiError(409, 'stale_result', '成绩版本已变化。'),
    )
    await user.click(screen.getByRole('button', { name: '保存更正' }))
    await screen.findByRole('button', { name: '重新加载最新成绩' })
    expect(correctResult).toHaveBeenCalledTimes(1)
    vi.mocked(fetchResult).mockResolvedValueOnce({
      ...firstTable.result!,
      version: 2,
      points: { '1': 35000, '2': 35000, '3': 20000, '4': 10000 },
    })
    await user.click(screen.getByRole('button', { name: '重新加载最新成绩' }))
    await waitFor(() =>
      expect((screen.getByLabelText('快照选手1 终局点数') as HTMLInputElement).value).toBe('35000'),
    )
    for (const [index, value] of ['40000', '30000'].entries()) {
      const input = screen.getByLabelText(`快照选手${index + 1} 终局点数`)
      await user.clear(input)
      await user.type(input, value)
    }
    await user.click(screen.getByRole('button', { name: '保存更正' }))
    await waitFor(() => expect(vi.mocked(correctResult).mock.calls[1][1]).toBe(2))
  })
  it('更正提交期间禁用数字与关闭按钮', async () => {
    prepare()
    const user = await openFirst()
    for (const [index, value] of ['35000', '35000'].entries()) {
      const input = screen.getByLabelText(`快照选手${index + 1} 终局点数`)
      await user.clear(input)
      await user.type(input, value)
    }
    let finish!: (value: NonNullable<RoundTable['result']>) => void
    vi.mocked(correctResult).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    await user.click(screen.getByRole('button', { name: '保存更正' }))
    expect(screen.getByLabelText('快照选手1 终局点数').matches(':disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '关闭比赛操作' }).hasAttribute('disabled')).toBe(true)
    finish({ ...table.result!, version: 2, status: 'confirmed' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
  it('完赛后只能读取更正记录，显示原点数与新点数', async () => {
    const { firstTable } = prepare()
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, status: 'completed' })
    vi.mocked(fetchResultCorrections).mockResolvedValueOnce({
      table_id: 20,
      corrections: [
        {
          id: 1,
          from_version: 1,
          to_version: 2,
          before: firstTable.result!,
          after: {
            ...firstTable.result!,
            points: { '1': 35000, '2': 35000, '3': 20000, '4': 10000 },
          },
          corrected_by: 7,
          corrected_at: date,
          reason: '抄录修正',
        },
      ],
    })
    show()
    const user = userEvent.setup()
    await screen.findByRole('combobox', { name: '查看轮次' })
    await selectOption(user, '查看轮次', '第 1 轮')
    expect(screen.queryByRole('button', { name: '更正第1轮第1桌成绩' })).toBeNull()
    await user.click(screen.getByRole('button', { name: '查看第1轮第1桌成绩更正记录' }))
    expect(await screen.findByText('点数 40000 → 35000')).toBeTruthy()
    expect(screen.getByText('抄录修正')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '保存更正' })).toBeNull()
  })
  it('已有后续轮次时，历史未确认成绩仍可录入草稿', async () => {
    prepare(false)
    show()
    const user = userEvent.setup()
    await screen.findByRole('combobox', { name: '查看轮次' })
    await selectOption(user, '查看轮次', '第 1 轮')
    await user.click(screen.getByRole('button', { name: '录入第1桌成绩' }))
    await user.type(screen.getByLabelText('快照选手1 终局点数'), '-1000')
    await user.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    await waitFor(() =>
      expect(saveResult).toHaveBeenCalledWith(
        20,
        0,
        [
          { participant_id: 1, raw_points: -1000 },
          { participant_id: 2, raw_points: null },
          { participant_id: 3, raw_points: null },
          { participant_id: 4, raw_points: null },
        ],
        false,
      ),
    )
  })
})

const pendingLottery: Lottery = {
  id: 11,
  members: [1, 2, 3, 4],
  order: [2, 1, 4, 3],
  method: '现场签条',
  description: '全员公开监督',
  drawn_at: date,
  created_by_id: 7,
  created_at: date,
  confirmed_by_id: null,
  confirmed_at: null,
  voided_by_id: null,
  voided_at: null,
  void_reason: '',
  source_versions: [],
}
const tiedWs: Workspace = { ...ws, all_results_confirmed: true, unresolved_groups: [[1, 2, 3, 4]] }
async function openLottery() {
  vi.mocked(fetchTournament).mockResolvedValue({ ...t, round_count: 1 })
  show()
  const u = userEvent.setup()
  await u.click(await screen.findByRole('button', { name: '记录公开抽签 1' }))
  return u
}
async function fillLottery(u: ReturnType<typeof userEvent.setup>) {
  for (let i = 0; i < 4; i++) await selectOption(u, `抽签顺位 ${i + 1}`, `快照选手${4 - i}`)
  await u.type(screen.getByLabelText('抽签方式'), '现场签条')
  await u.type(screen.getByLabelText('实际抽签时间'), '2026-11-04T12:00')
  await u.type(screen.getByLabelText('公开过程说明'), '全员公开监督')
}
describe('公开抽签不能挑结果（F1）', () => {
  it('录入后不确认直接取消也已重新拉取；重开只显示待确认记录且不能再录', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue(tiedWs)
    const u = await openLottery()
    expect(fetchWorkspace).toHaveBeenCalledTimes(1)
    await fillLottery(u)
    const recorded = { ...pendingLottery, id: 10, order: [4, 3, 2, 1] }
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...tiedWs, lotteries: [recorded] })
    await u.click(screen.getByRole('button', { name: '保存公开抽签记录' }))
    await waitFor(() => expect(fetchWorkspace).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('button', { name: '二次确认抽签顺序' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '作废此记录' })).toBeTruthy()
    await u.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(confirmLottery).not.toHaveBeenCalled()
    expect(screen.getByText(/已有待二次确认的抽签记录/)).toBeTruthy()
    await u.click(screen.getByRole('button', { name: '记录公开抽签 1' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByText('待二次确认的抽签记录 #10')).toBeTruthy()
    expect(dialog.queryByRole('button', { name: '保存公开抽签记录' })).toBeNull()
    expect(dialog.queryByRole('combobox', { name: '抽签顺位 1' })).toBeNull()
    expect(dialog.queryByLabelText('抽签方式')).toBeNull()
    expect(recordLottery).toHaveBeenCalledTimes(1)
  })
  it('录入成功后关闭面板同样保留刷新后的待确认记录', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue(tiedWs)
    const u = await openLottery()
    await fillLottery(u)
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...tiedWs, lotteries: [pendingLottery] })
    await u.click(screen.getByRole('button', { name: '保存公开抽签记录' }))
    await waitFor(() => expect(fetchWorkspace).toHaveBeenCalledTimes(2))
    await u.click(screen.getByRole('button', { name: '关闭比赛操作' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await u.click(screen.getByRole('button', { name: '记录公开抽签 1' }))
    expect(screen.getByText('待二次确认的抽签记录 #11')).toBeTruthy()
  })
  it('已有待确认记录时展示顺序、方式、说明、时间、记录人，并只能确认或作废', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...tiedWs, lotteries: [pendingLottery] })
    const u = await openLottery()
    const dialog = within(screen.getByRole('dialog'))
    const order = dialog.getByRole('list', { name: '抽签顺序' })
    const items = within(order).getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      '第 1 位：快照选手2',
      '第 2 位：快照选手1',
      '第 3 位：快照选手4',
      '第 4 位：快照选手3',
    ])
    expect(dialog.getByText('现场签条')).toBeTruthy()
    expect(dialog.getByText('全员公开监督')).toBeTruthy()
    expect(dialog.getByText(new Date(date).toLocaleString('zh-CN'))).toBeTruthy()
    expect(dialog.getByText(/管理员 #7/)).toBeTruthy()
    expect(dialog.queryByRole('button', { name: '保存公开抽签记录' })).toBeNull()
    await u.click(dialog.getByRole('button', { name: '二次确认抽签顺序' }))
    await waitFor(() => expect(confirmLottery).toHaveBeenCalledWith(5, 11))
  })
  it('作废须填写原因（≤500字）并二次确认；作废后历史显示原因且无任何操作', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...tiedWs, lotteries: [pendingLottery] })
    const voided = {
      ...pendingLottery,
      voided_by_id: 7,
      voided_at: date,
      void_reason: '顺序录错',
    }
    vi.mocked(voidLottery).mockResolvedValue(voided)
    const u = await openLottery()
    await u.click(screen.getByRole('button', { name: '作废此记录' }))
    const reason = screen.getByLabelText('作废原因')
    expect(reason.getAttribute('maxlength')).toBe('500')
    expect(screen.getByRole('button', { name: '预览作废' }).hasAttribute('disabled')).toBe(true)
    await u.type(reason, '   ')
    expect(screen.getByRole('button', { name: '预览作废' }).hasAttribute('disabled')).toBe(true)
    await u.type(reason, '顺序录错 ')
    await u.click(screen.getByRole('button', { name: '预览作废' }))
    expect(voidLottery).not.toHaveBeenCalled()
    expect(screen.getByLabelText('作废确认').textContent).toContain('作废原因：顺序录错')
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...tiedWs, lotteries: [voided] })
    await u.click(screen.getByRole('button', { name: '确认作废' }))
    await waitFor(() => expect(voidLottery).toHaveBeenCalledWith(5, 11, '顺序录错'))
    await waitFor(() => expect(fetchWorkspace).toHaveBeenCalledTimes(2))
    const history = within(screen.getByRole('region', { name: '本组抽签记录历史' }))
    expect(history.getByText('记录 #11 · 已作废')).toBeTruthy()
    expect(history.getByText(/作废原因：顺序录错/)).toBeTruthy()
    expect(history.queryAllByRole('button')).toHaveLength(0)
    expect(screen.queryByRole('button', { name: '二次确认抽签顺序' })).toBeNull()
    expect(screen.getByRole('combobox', { name: '抽签顺位 1' })).toBeTruthy()
  })
  it('已作废记录只在历史中显示，不能确认或作废，也不阻止重新录入', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({
      ...tiedWs,
      lotteries: [{ ...pendingLottery, voided_at: date, voided_by_id: 7, void_reason: '录错' }],
    })
    const u = await openLottery()
    expect(screen.queryByRole('button', { name: '二次确认抽签顺序' })).toBeNull()
    expect(screen.queryByRole('button', { name: '作废此记录' })).toBeNull()
    const history = within(screen.getByRole('region', { name: '本组抽签记录历史' }))
    expect(history.getByText(/作废原因：录错/)).toBeTruthy()
    expect(history.queryAllByRole('button')).toHaveLength(0)
    await fillLottery(u)
    await u.click(screen.getByRole('button', { name: '保存公开抽签记录' }))
    await waitFor(() => expect(recordLottery).toHaveBeenCalledTimes(1))
  })
  it('来源成绩已变化的旧待确认记录不可操作，可以按新来源重新录入', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({
      ...tiedWs,
      source_versions: [{ table_id: 20, version: 3 }],
      lotteries: [{ ...pendingLottery, source_versions: [{ table_id: 20, version: 2 }] }],
    })
    await openLottery()
    expect(screen.queryByRole('button', { name: '二次确认抽签顺序' })).toBeNull()
    expect(screen.getByText(/待确认（来源成绩已变化，记录失效）/)).toBeTruthy()
    expect(screen.getByRole('combobox', { name: '抽签顺位 1' })).toBeTruthy()
  })
  it.each([
    ['lottery_pending', '该并列组已有待确认的抽签记录，请先确认或作废后再录入。'],
    ['lottery_voided', '抽签记录已作废。'],
    ['lottery_conflict', '已确认的抽签不能作废。'],
    ['tournament_completed', '赛事已完赛，抽签记录只读。'],
  ])('409 %s 显示后端消息并重新拉取数据', async (code, message) => {
    const error = new ApiError(409, code, message)
    const operation = {
      lottery_pending: recordLottery,
      lottery_voided: confirmLottery,
      lottery_conflict: voidLottery,
      tournament_completed: voidLottery,
    }[code]!
    vi.mocked(operation).mockRejectedValueOnce(error)
    const pending = code !== 'lottery_pending'
    vi.mocked(fetchWorkspace).mockResolvedValue({
      ...tiedWs,
      lotteries: pending ? [pendingLottery] : [],
    })
    const u = await openLottery()
    if (!pending) {
      await fillLottery(u)
      await u.click(screen.getByRole('button', { name: '保存公开抽签记录' }))
    } else if (code === 'lottery_voided') {
      await u.click(screen.getByRole('button', { name: '二次确认抽签顺序' }))
    } else {
      await u.click(screen.getByRole('button', { name: '作废此记录' }))
      await u.type(screen.getByLabelText('作废原因'), '录错')
      await u.click(screen.getByRole('button', { name: '预览作废' }))
      await u.click(screen.getByRole('button', { name: '确认作废' }))
    }
    expect((await screen.findByRole('alert')).textContent).toContain(message)
    await waitFor(() => expect(fetchWorkspace).toHaveBeenCalledTimes(2))
    expect(screen.getByText(/已自动重新读取工作台数据/)).toBeTruthy()
  })
})
describe('成绩点数严格解析（F3）', () => {
  it.each([
    ['1e3', '只能填写整数'],
    ['0x10', '只能填写整数'],
    ['1.5', '只能填写整数'],
    ['99999999999999999', '安全整数范围'],
  ])('非法输入 %s 在对应格子报错并阻止保存，不会静默存成 0', async (value, message) => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    await u.type(screen.getByLabelText('快照选手1 终局点数'), '25000')
    const bad = screen.getByLabelText('快照选手2 终局点数')
    await u.type(bad, value)
    await u.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    expect(saveResult).not.toHaveBeenCalled()
    expect(bad.getAttribute('aria-invalid')).toBe('true')
    const hint = document.getElementById(bad.getAttribute('aria-describedby')!)
    expect(hint?.textContent).toContain(message)
    expect(screen.getByLabelText('快照选手1 终局点数').getAttribute('aria-invalid')).toBeNull()
    expect(screen.getByText('已填写 1 / 4 · 实录合计 25000')).toBeTruthy()
    expect(screen.getByText('1 位选手的点数格式有误，未计入合计。')).toBeTruthy()
  })
  it('空白（含全角空格）视为未填写，全角数字与负号归一后保存', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    await u.type(screen.getByLabelText('快照选手1 终局点数'), ' ')
    await u.type(screen.getByLabelText('快照选手2 终局点数'), '\u3000')
    await u.type(screen.getByLabelText('快照选手3 终局点数'), '２５０００')
    await u.type(screen.getByLabelText('快照选手4 终局点数'), '\uFF0D100')
    expect(screen.getByText('已填写 2 / 4 · 实录合计 24900')).toBeTruthy()
    await u.click(screen.getByRole('button', { name: '保存成绩草稿' }))
    await waitFor(() =>
      expect(saveResult).toHaveBeenCalledWith(
        20,
        0,
        [
          { participant_id: 1, raw_points: null },
          { participant_id: 2, raw_points: null },
          { participant_id: 3, raw_points: 25000 },
          { participant_id: 4, raw_points: -100 },
        ],
        false,
      ),
    )
  })
  it('合计与确认校验使用同一解析：尾随空格、全角、Unicode 负号均可正式确认', async () => {
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '录入第1桌成绩' }))
    const values = ['25000 ', '２５０００', '\u2212100', '50100']
    for (const [i, v] of values.entries())
      await u.type(screen.getByLabelText(`快照选手${i + 1} 终局点数`), v)
    expect(screen.getByText('已填写 4 / 4 · 实录合计 100000')).toBeTruthy()
    await u.click(screen.getByRole('button', { name: '确认成绩' }))
    await u.click(screen.getByRole('button', { name: '再次确认成绩' }))
    await waitFor(() =>
      expect(saveResult).toHaveBeenCalledWith(
        20,
        0,
        [
          { participant_id: 1, raw_points: 25000 },
          { participant_id: 2, raw_points: 25000 },
          { participant_id: 3, raw_points: -100 },
          { participant_id: 4, raw_points: 50100 },
        ],
        true,
      ),
    )
  })
})
describe('完赛快照与两步确认（F5/F7/F9）', () => {
  it('完赛快照没有 unresolved_groups 时正常显示冠军', async () => {
    const snapshot: Workspace = { ...ws, status: 'completed', champion_id: 2 }
    delete snapshot.unresolved_groups
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, status: 'completed', round_count: 1 })
    vi.mocked(fetchWorkspace).mockResolvedValue(snapshot)
    show()
    await screen.findByText('CHAMPION / 个人冠军')
    expect(screen.getByRole('heading', { name: '快照选手2' })).toBeTruthy()
  })
  it('进行中工作台缺少 unresolved_groups 时不白屏', async () => {
    const preview: Workspace = { ...ws, all_results_confirmed: true }
    delete preview.unresolved_groups
    vi.mocked(fetchTournament).mockResolvedValue({ ...t, round_count: 1 })
    vi.mocked(fetchWorkspace).mockResolvedValue(preview)
    show()
    expect(await screen.findByText(/最终排名已确定/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /记录公开抽签/ })).toBeNull()
  })
  it('首轮预览后修改选桌退回预览前，必须重新预览才能提交', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...t,
      participant_count: 8,
      expected_table_count: 2,
    })
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    vi.mocked(fetchResources).mockResolvedValue({
      results: ['107', '307', '407'].map((no, i) => ({
        machine_id: i + 2,
        machine_no: no,
        name: '空闲桌',
        status: 'available' as const,
        assignable: true,
        active_allocation: null,
      })),
    })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '选择物理桌并生成首轮' }))
    await selectOption(u, '逻辑桌 A 物理桌', '107 · 空闲桌')
    await selectOption(u, '逻辑桌 B 物理桌', '307 · 空闲桌')
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    expect(screen.getByText('最终确认')).toBeTruthy()
    await selectOption(u, '逻辑桌 B 物理桌', '407 · 空闲桌')
    expect(screen.queryByText('最终确认')).toBeNull()
    expect(screen.queryByRole('button', { name: '确认生成轮次' })).toBeNull()
    await u.click(screen.getByRole('button', { name: '预览并确认' }))
    expect(generateRound).not.toHaveBeenCalled()
    expect(screen.getByText(/逻辑桌 B →\s*407/)).toBeTruthy()
    await u.click(screen.getByRole('button', { name: '确认生成轮次' }))
    await waitFor(() => expect(generateRound).toHaveBeenCalledWith(5, 1, [2, 4]))
  })
  it('兼容复核预览展示 A～D 物理桌、historical_only 与原因；修改后须重新预览', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({ ...ws, resource_state: 'review_required' })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '复核旧赛事' }))
    await selectOption(u, '逻辑桌 A 物理桌', '007 · 已占用')
    await u.type(screen.getByLabelText('复核说明'), '原占用仍有效')
    await u.click(screen.getByRole('button', { name: '预览复核' }))
    const summary = screen.getByLabelText('兼容复核摘要')
    expect(summary.textContent).toContain('逻辑桌 A → 物理桌 007 · 已占用')
    expect(summary.textContent).toContain('historical_only：否')
    expect(summary.textContent).toContain('复核原因：原占用仍有效')
    expect(reviewLegacy).not.toHaveBeenCalled()
    await u.click(screen.getByRole('checkbox'))
    expect(screen.queryByLabelText('兼容复核摘要')).toBeNull()
    await u.click(screen.getByRole('button', { name: '预览复核' }))
    expect(screen.getByLabelText('兼容复核摘要').textContent).toContain('historical_only：是')
    expect(screen.getByLabelText('兼容复核摘要').textContent).not.toContain('逻辑桌 A')
    await u.click(screen.getByRole('button', { name: '确认兼容复核' }))
    await waitFor(() => expect(reviewLegacy).toHaveBeenCalledWith(5, true, [], '原占用仍有效'))
  })
  it('物理桌占用历史分开显示建立原因与释放原因', async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue({
      ...ws,
      mapping: [
        {
          ...ws.mapping[0],
          history: [
            {
              id: 2,
              machine_id: 9,
              machine_no_snapshot: '009',
              status: 'released',
              source: 'replacement',
              reason: '故障替换',
              release_reason: '设备再次故障',
            },
            { ...ws.mapping[0].history[0] },
          ],
        },
      ],
    })
    show()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: '占用历史' }))
    const [released, active] = screen.getAllByRole('article')
    expect(within(released).getByText('建立原因')).toBeTruthy()
    expect(within(released).getByText('故障替换')).toBeTruthy()
    expect(within(released).getByText('释放原因')).toBeTruthy()
    expect(within(released).getByText('设备再次故障')).toBeTruthy()
    expect(within(active).getByText('原记录继承')).toBeTruthy()
    expect(within(active).queryByText('释放原因')).toBeNull()
  })
})
