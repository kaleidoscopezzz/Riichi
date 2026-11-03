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
  fetchTable,
  fetchAllocationHistory,
  generateRound,
  reassignMachine,
  releaseMachine,
  type TournamentRound,
  type MachineResource,
  type Allocation,
  type RoundTable,
} from '@/services/rounds'

vi.mock('@/services/tournaments', async (original) => ({
  ...(await original<typeof import('@/services/tournaments')>()),
  fetchTournament: vi.fn(),
}))
vi.mock('@/services/rounds', async (original) => ({
  ...(await original<typeof import('@/services/rounds')>()),
  fetchRounds: vi.fn(),
  fetchResources: vi.fn(),
  fetchTable: vi.fn(),
  fetchAllocationHistory: vi.fn(),
  generateRound: vi.fn(),
  reassignMachine: vi.fn(),
  releaseMachine: vi.fn(),
}))
const date = '2026-11-03T08:00:00Z'
const tournament: Tournament = {
  id: 5,
  name: '轮次测试赛事',
  description: '仅测试夹具',
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
const allocation: Allocation = {
  id: 10,
  table_id: 20,
  machine_id: 1,
  machine_no: '007',
  machine_no_snapshot: '007',
  machine_status: 'available',
  status: 'active',
  allocated_at: date,
  allocated_by: 1,
  released_at: null,
  released_by: null,
  release_reason: '',
}
const table: RoundTable = {
  id: 20,
  round_id: 6,
  round_number: 1,
  tournament_id: 5,
  table_number: 1,
  created_at: date,
  seats: (['east', 'south', 'west', 'north'] as const).map((wind, i) => ({
    id: i + 1,
    participant_id: i + 1,
    player_id: i + 1,
    display_name: `快照选手${i + 1}`,
    seat_wind: wind,
  })),
  active_allocation: allocation,
  allocation_history: [allocation],
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
const resources: MachineResource[] = [
  {
    machine_id: 1,
    machine_no: '007',
    name: '验证设备一',
    status: 'available',
    assignable: false,
    active_allocation: {
      id: 10,
      table_id: 20,
      table_number: 1,
      round_number: 1,
      tournament_id: 5,
      tournament_name: '轮次测试赛事',
    },
  },
  {
    machine_id: 2,
    machine_no: '107',
    name: '验证设备二',
    status: 'available',
    assignable: true,
    active_allocation: null,
  },
  {
    machine_id: 3,
    machine_no: '207',
    name: '维护设备',
    status: 'maintenance',
    assignable: false,
    active_allocation: null,
  },
]
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchTournament).mockResolvedValue(tournament)
  vi.mocked(fetchRounds).mockResolvedValue({ results: [round] })
  vi.mocked(fetchResources).mockResolvedValue({ results: resources })
  vi.mocked(fetchTable).mockResolvedValue(table)
  vi.mocked(fetchAllocationHistory).mockResolvedValue({ results: [allocation] })
  vi.mocked(generateRound).mockImplementation(async () => {
    vi.mocked(fetchRounds).mockResolvedValue({ results: [round] })
    return round
  })
  vi.mocked(reassignMachine).mockResolvedValue(table)
  vi.mocked(releaseMachine).mockResolvedValue({ ...table, active_allocation: null })
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
              : { id: 1, username: 'qa-fixture', is_staff: admin, date_joined: date },
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

describe('首轮分桌工作台', () => {
  it('赛事详情摘要读取真实轮次与本赛事占用数', async () => {
    render(<TournamentRoundSummary id={5} />)
    expect(screen.getByRole('status').textContent).toContain('正在读取')
    await screen.findByText('1 台')
    expect(screen.getByText('1 轮')).toBeTruthy()
  })
  it('生成请求未结束时禁用重复确认', async () => {
    let resolve!: (value: TournamentRound) => void
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    vi.mocked(generateRound).mockReturnValueOnce(
      new Promise((done) => {
        resolve = done
      }),
    )
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '生成第一轮分桌' }))
    await user.click(await screen.findByRole('button', { name: '确认生成首轮' }))
    expect(screen.getByRole('button', { name: '正在提交…' }).hasAttribute('disabled')).toBe(true)
    expect(generateRound).toHaveBeenCalledTimes(1)
    vi.mocked(fetchRounds).mockResolvedValue({ results: [round] })
    resolve(round)
    await screen.findByText('逻辑桌 1')
  })
  it('加载持久化座次和真实设备，区分状态与占用', async () => {
    show()
    expect(screen.getByRole('status').textContent).toContain('正在读取')
    await screen.findByText('逻辑桌 1')
    for (const name of ['快照选手1', '快照选手2', '快照选手3', '快照选手4'])
      expect(screen.getByText(name)).toBeTruthy()
    for (const wind of ['东', '南', '西', '北'])
      expect(screen.getByText(wind, { exact: true })).toBeTruthy()
    expect(screen.getByText('当前空闲 · 可分配')).toBeTruthy()
    expect(screen.getByText('维护中')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '生成第一轮分桌' })).toBeNull()
    expect(screen.queryByText(/积分排名/)).toBeNull()
  })
  it.each([4, 8, 12, 16])('%i人显示正确所需桌数与设备数', async (size) => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...tournament,
      participant_count: size,
      expected_table_count: size / 4,
    })
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '生成第一轮分桌' }))
    await screen.findByRole('dialog')
    expect(screen.getByText(`${size / 4} 桌 / ${size / 4} 台`)).toBeTruthy()
  })
  it('草稿不提供生成入口', async () => {
    vi.mocked(fetchTournament).mockResolvedValue({
      ...tournament,
      status: 'draft',
      started_at: null,
    })
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    await screen.findByText('赛事尚未启动')
    expect(screen.queryByRole('button', { name: '生成第一轮分桌' })).toBeNull()
  })
  it('生成先确认，取消不写入，确认后从API恢复分桌', async () => {
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '生成第一轮分桌' }))
    await user.click(await screen.findByRole('button', { name: '取消' }))
    expect(generateRound).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '生成第一轮分桌' }))
    await user.click(await screen.findByRole('button', { name: '确认生成首轮' }))
    await screen.findByText('逻辑桌 1')
    expect(generateRound).toHaveBeenCalledTimes(1)
    expect(fetchRounds).toHaveBeenCalledWith(5, expect.any(AbortSignal))
    expect(screen.queryByRole('button', { name: '生成第一轮分桌' })).toBeNull()
  })
  it('资源不足显示原因，禁止确认部分生成', async () => {
    vi.mocked(fetchRounds).mockResolvedValue({ results: [] })
    vi.mocked(fetchResources).mockResolvedValue({
      results: resources.map((r) => ({ ...r, assignable: false })),
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '生成第一轮分桌' }))
    await screen.findByRole('dialog')
    expect(screen.getByRole('button', { name: '确认生成首轮' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('alert').textContent).toContain('不会部分生成')
    expect(generateRound).not.toHaveBeenCalled()
  })
  it('调整设备先选空闲目标并明确确认', async () => {
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '调整第1桌设备' }))
    await screen.findByRole('dialog')
    expect(reassignMachine).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '确认调整设备' }).hasAttribute('disabled')).toBe(true)
    await user.selectOptions(screen.getByLabelText('目标空闲设备'), '2')
    expect(screen.queryByRole('option', { name: /维护设备/ })).toBeNull()
    await user.click(screen.getByRole('button', { name: '确认调整设备' }))
    await waitFor(() => expect(reassignMachine).toHaveBeenCalledWith(20, 2))
  })
  it('占用历史读取API，保留稳定machineId和分配快照', async () => {
    vi.mocked(fetchAllocationHistory).mockResolvedValue({
      results: [
        {
          ...allocation,
          status: 'released',
          released_at: date,
          released_by: 1,
          release_reason: '历史释放',
          machine_no: '008',
        },
      ],
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '查看第1桌设备历史' }))
    await screen.findByText('历史释放')
    expect(fetchAllocationHistory).toHaveBeenCalledWith(20)
    expect(screen.getByRole('dialog').textContent).toContain('稳定 machineId #1')
    expect(screen.getByText('设备 007')).toBeTruthy()
  })
  it('释放确认与原因，成功后座次保留且没有重新开启按钮', async () => {
    vi.mocked(releaseMachine).mockImplementation(async () => {
      vi.mocked(fetchRounds).mockResolvedValue({
        results: [{ ...round, tables: [{ ...table, active_allocation: null }] }],
      })
      return { ...table, active_allocation: null }
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '释放第1桌设备' }))
    await screen.findByRole('dialog')
    expect(screen.getByText(/本阶段不支持重新开启/)).toBeTruthy()
    expect(releaseMachine).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('释放说明（可选）'), '实体使用结束')
    await user.click(screen.getByRole('button', { name: '确认释放设备' }))
    await screen.findByText('设备已释放')
    expect(releaseMachine).toHaveBeenCalledWith(20, '实体使用结束')
    expect(screen.getByText('快照选手1')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '释放第1桌设备' })).toBeNull()
  })
  it('409冲突显示，不自动重放写入', async () => {
    vi.mocked(reassignMachine).mockRejectedValueOnce(
      new ApiError(409, 'machine_occupied', '设备已被其他赛事占用'),
    )
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '调整第1桌设备' }))
    await user.selectOptions(await screen.findByLabelText('目标空闲设备'), '2')
    await user.click(screen.getByRole('button', { name: '确认调整设备' }))
    expect((await screen.findByRole('alert')).textContent).toContain('设备已被其他赛事占用')
    expect(reassignMachine).toHaveBeenCalledTimes(1)
  })
  it('刷新恢复同一座次，不重新随机；失败后可重试', async () => {
    vi.mocked(fetchRounds).mockRejectedValueOnce(new Error('网络验证失败'))
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '重新加载工作台' }))
    await screen.findByText('逻辑桌 1')
    await user.click(screen.getByRole('button', { name: '刷新工作台' }))
    await screen.findByText('快照选手1')
    expect(generateRound).not.toHaveBeenCalled()
  })
  it('Sheet Escape关闭，普通用户及匿名访问被阻止', async () => {
    const page = show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '查看第1桌设备历史' }))
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    page.unmount()
    const app = showApp(false)
    expect(screen.getByRole('heading', { name: '无权访问' })).toBeTruthy()
    app.unmount()
    showApp(false, true)
    expect(await screen.findByLabelText('用户名')).toBeTruthy()
  })
})
