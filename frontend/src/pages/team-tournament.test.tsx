// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { TeamTournamentPage } from './team-tournament'
import { teamTournament, teamWorkspace, teamPlan } from '@/test/team-fixtures'
import {
  fetchTeam,
  fetchTeamWorkspace,
  fetchTeamPlans,
  fetchTeamBatches,
  fetchTeamPlan,
  confirmTeamPlans,
  type TeamStage,
} from '@/services/teams'
import { fetchResources } from '@/services/rounds'
import { ApiError } from '@/services/api'
vi.mock('@/services/teams', async (original) => ({
  ...(await original<typeof import('@/services/teams')>()),
  fetchTeam: vi.fn(),
  fetchTeamWorkspace: vi.fn(),
  fetchTeamPlans: vi.fn(),
  fetchTeamBatches: vi.fn(),
  fetchTeamPlan: vi.fn(),
  confirmTeamPlans: vi.fn(),
}))
vi.mock('@/services/rounds', async (original) => ({
  ...(await original<typeof import('@/services/rounds')>()),
  fetchResources: vi.fn(),
}))
afterEach(cleanup)
const stage = (id: number, label: string): TeamStage => ({
  id,
  stage_number: id,
  cycle: 1,
  position_label: label,
  games_per_team: 2,
  match_count: 2,
  confirmed_matches: 0,
  representatives: teamTournament.teams.map((team) => ({
    team_id: team.id,
    member_id: team.members[0].id,
    locked: false,
  })),
})
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchTeam).mockResolvedValue({
    ...teamTournament,
    status: 'started',
    team_settings: { ...teamTournament.team_settings, schedule_mode: 'positions' },
  })
  vi.mocked(fetchTeamWorkspace).mockResolvedValue({
    ...teamWorkspace,
    stages: [stage(1, '先锋'), stage(2, '次峰')],
    current_stage_id: 1,
  })
  vi.mocked(fetchTeamPlans).mockResolvedValue({
    results: [teamPlan],
    count: 1,
    page: 1,
    has_next: false,
  })
  vi.mocked(fetchTeamBatches).mockResolvedValue({ results: [], count: 0, page: 1, has_next: false })
  vi.mocked(fetchResources).mockResolvedValue({ results: [] })
  vi.mocked(confirmTeamPlans).mockResolvedValue({})
})
function show() {
  return render(
    <MemoryRouter initialEntries={['/tournaments/6/team']}>
      <Routes>
        <Route path="tournaments/:id/team" element={<TeamTournamentPage />} />
      </Routes>
    </MemoryRouter>,
  )
}
describe('团队工作台数据与刷新', () => {
  it('刷新期间禁用位置操作，完成后只打开最新位置避免旧阶段卡住', async () => {
    show()
    const user = userEvent.setup()
    await screen.findByText(/第 1 循环 · 先锋，已确认/)
    let resolve!: (value: typeof teamWorkspace) => void
    const next = new Promise<typeof teamWorkspace>((r) => {
      resolve = r
    })
    vi.mocked(fetchTeamWorkspace).mockReturnValueOnce(next)
    await user.click(screen.getByRole('button', { name: '刷新团队工作台' }))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '编辑本位置代表名单' }).hasAttribute('disabled'),
      ).toBe(true),
    )
    expect(screen.getByRole('button', { name: '预览下一开赛时段' }).hasAttribute('disabled')).toBe(
      true,
    )
    await act(async () =>
      resolve({
        ...teamWorkspace,
        stages: [stage(1, '先锋'), stage(2, '次峰')],
        current_stage_id: 2,
      }),
    )
    await screen.findByText(/第 1 循环 · 次峰，已确认/)
    await user.click(screen.getByRole('button', { name: '编辑本位置代表名单' }))
    expect(screen.getByRole('dialog').getAttribute('aria-labelledby')).toBeTruthy()
    expect(screen.getByRole('heading', { name: '第 1 循环 · 次峰代表' })).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: '队伍1 先锋代表' })).toBeNull()
  })
  it('未生成赛程的草稿仍能编辑和请求校验，不要求先有合法位置人次', async () => {
    vi.mocked(fetchTeam).mockResolvedValue({
      ...teamTournament,
      team_settings: { ...teamTournament.team_settings, schedule_mode: 'positions' },
    })
    vi.mocked(fetchTeamWorkspace).mockResolvedValue({
      ...teamWorkspace,
      status: 'draft',
      match_count: 0,
      stages: [],
      current_stage_id: null,
    })
    vi.mocked(fetchTeamPlans).mockResolvedValue({ results: [], count: 0, page: 1, has_next: false })
    show()
    await screen.findByRole('button', { name: '预览团队赛程' })
    expect(screen.getByRole('button', { name: '编辑团队草稿' }).hasAttribute('disabled')).toBe(
      false,
    )
    expect(screen.queryByRole('button', { name: '正式完赛团队赛' })).toBeNull()
  })
  it('完赛后重新进入仍展示团队冠军、冻结贡献与只读桌关联', async () => {
    vi.mocked(fetchTeam).mockResolvedValue({ ...teamTournament, status: 'completed' })
    vi.mocked(fetchTeamWorkspace).mockResolvedValue({
      ...teamWorkspace,
      status: 'completed',
      champion_team_id: 1,
      completed_matches: 4,
      mapping: [],
      stages: [],
      current_stage_id: null,
    })
    show()
    await screen.findByText('TEAM CHAMPION / 团队冠军')
    expect(screen.getByRole('heading', { name: '队伍1', level: 2 })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '预览下一开赛时段' })).toBeNull()
    expect(screen.queryByRole('button', { name: '确认本场出场' })).toBeNull()
    expect(screen.queryByRole('button', { name: '正式完赛团队赛' })).toBeNull()
  })
  it('单场确认409后禁用旧确认，显式回读原场次后重新核对并提交新版本', async () => {
    show()
    const user = userEvent.setup()
    vi.mocked(confirmTeamPlans).mockRejectedValueOnce(
      new ApiError(409, 'stale_team_plan', '其他管理员更新了名单'),
    )
    const newer = {
      ...teamPlan,
      version: 4,
      lineup: { ...teamPlan.lineup, '1': 2 },
      lineup_rows: teamPlan.lineup_rows.map((r) =>
        r.team_id === 1 ? { ...r, member_id: 2, display_name: '成员2' } : r,
      ),
    }
    vi.mocked(fetchTeamPlan).mockResolvedValue(newer)
    await user.click(await screen.findByRole('button', { name: '确认本场出场' }))
    let panel = within(screen.getByRole('dialog'))
    await user.click(panel.getByRole('button', { name: '二次确认本场名单' }))
    await panel.findByText('本场确认来源已过期，请载入最新名单并重新核对。')
    expect(panel.getByRole('button', { name: '二次确认本场名单' }).hasAttribute('disabled')).toBe(
      true,
    )
    await user.click(panel.getByRole('button', { name: '载入最新本场确认名单' }))
    panel = within(screen.getByRole('dialog'))
    await panel.findByText('队伍1：成员2')
    await waitFor(() =>
      expect(panel.getByRole('button', { name: '二次确认本场名单' }).hasAttribute('disabled')).toBe(
        false,
      ),
    )
    await user.click(panel.getByRole('button', { name: '二次确认本场名单' }))
    expect(confirmTeamPlans).toHaveBeenLastCalledWith(6, [{ match_id: 21, version: 4 }])
    expect(fetchTeamPlan).toHaveBeenCalledWith(6, 21)
  })
  it('位置确认409后保留旧预览且禁止提交，回读同一位置计划使用最新版本', async () => {
    show()
    const user = userEvent.setup()
    await screen.findByText(/第 1 循环 · 先锋，已确认/)
    vi.mocked(confirmTeamPlans).mockRejectedValueOnce(
      new ApiError(409, 'stale_team_plan', '位置名单已更新'),
    )
    await user.click(screen.getByRole('button', { name: '预览确认本位置计划' }))
    let panel = within(screen.getByRole('dialog'))
    await waitFor(() =>
      expect(
        panel.getByRole('button', { name: '二次确认本位置全部名单' }).hasAttribute('disabled'),
      ).toBe(false),
    )
    await user.click(panel.getByRole('button', { name: '二次确认本位置全部名单' }))
    await panel.findByText('本位置确认来源已过期，请载入最新计划并重新核对。')
    expect(
      panel.getByRole('button', { name: '二次确认本位置全部名单' }).hasAttribute('disabled'),
    ).toBe(true)
    vi.mocked(fetchTeamPlans).mockResolvedValue({
      results: [
        {
          ...teamPlan,
          version: 8,
          lineup_rows: teamPlan.lineup_rows.map((r) =>
            r.team_id === 1 ? { ...r, member_id: 2, display_name: '成员2' } : r,
          ),
        },
      ],
      count: 1,
      page: 1,
      has_next: false,
    })
    await user.click(panel.getByRole('button', { name: '载入最新本位置确认名单' }))
    panel = within(screen.getByRole('dialog'))
    await panel.findByText(/第 1 场：队伍1 成员2/)
    await waitFor(() =>
      expect(
        panel.getByRole('button', { name: '二次确认本位置全部名单' }).hasAttribute('disabled'),
      ).toBe(false),
    )
    await user.click(panel.getByRole('button', { name: '二次确认本位置全部名单' }))
    expect(confirmTeamPlans).toHaveBeenLastCalledWith(6, [{ match_id: 21, version: 8 }])
    expect(fetchTeamPlans).toHaveBeenCalledWith(6, 1, 1)
  })
  it('手动固定位置提供四队分组入口，并保留代表编辑入口', async () => {
    vi.mocked(fetchTeam).mockResolvedValue({
      ...teamTournament,
      status: 'started',
      pairing_strategy: 'team_manual_v1',
      team_settings: { ...teamTournament.team_settings, schedule_mode: 'positions' },
    })
    vi.mocked(fetchTeamPlans).mockResolvedValue({
      results: [{ ...teamPlan, stage_id: 1, position_label: '先锋', cycle: 1 }],
      count: 1,
      page: 1,
      has_next: false,
    })
    show()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '编辑第 1 场四队' }))
    expect(screen.getByRole('heading', { name: '第 1 场四队分组' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存四队分组' })).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: '队伍1 出场成员' })).toBeNull()
  })
})
