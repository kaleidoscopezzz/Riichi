// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  TeamPlanEditor,
  TeamRepresentativesEditor,
  TeamLotteryEditor,
  type TeamRun,
} from './team-actions'
import { teamTournament, teamPlan, teamWorkspace } from '@/test/team-fixtures'
import { selectOption } from '@/test/select-option'
import {
  saveTeamPlan,
  fetchTeamPlan,
  setTeamRepresentatives,
  fetchTeamWorkspace,
  recordTeamLottery,
  type TeamStage,
  type TeamLottery,
} from '@/services/teams'
import { confirmLottery, voidLottery } from '@/services/competition'
import { ApiError } from '@/services/api'
vi.mock('@/services/teams', async (original) => ({
  ...(await original<typeof import('@/services/teams')>()),
  saveTeamPlan: vi.fn(),
  fetchTeamPlan: vi.fn(),
  setTeamRepresentatives: vi.fn(),
  fetchTeamWorkspace: vi.fn(),
  recordTeamLottery: vi.fn(),
}))
vi.mock('@/services/competition', async (original) => ({
  ...(await original<typeof import('@/services/competition')>()),
  confirmLottery: vi.fn(),
  voidLottery: vi.fn(),
}))
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(saveTeamPlan).mockResolvedValue(teamPlan)
  vi.mocked(fetchTeamPlan).mockResolvedValue({
    ...teamPlan,
    version: 4,
    lineup: { '1': 2, '2': 3, '3': 5, '4': 7 },
  })
  vi.mocked(setTeamRepresentatives).mockResolvedValue({ revision: 5 })
})
const run: TeamRun = async (operation) => {
  await operation()
}
describe('团队出场计划与位置代表', () => {
  it('出场下拉只给本队成员，保存当前版本与队长名单标记', async () => {
    render(
      <TeamPlanEditor plan={teamPlan} t={teamTournament} busy={false} error={null} run={run} />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox', { name: '队伍1 出场成员' }))
    expect(screen.queryByRole('option', { name: '成员3' })).toBeNull()
    await user.click(screen.getByRole('option', { name: '成员2' }))
    await user.click(screen.getByRole('button', { name: '保存出场计划' }))
    await waitFor(() =>
      expect(saveTeamPlan).toHaveBeenCalledWith(6, 21, {
        version: 1,
        lineup: [
          { team_id: 1, member_id: 2 },
          { team_id: 2, member_id: 3 },
          { team_id: 3, member_id: 5 },
          { team_id: 4, member_id: 7 },
        ],
        captain_supplied: true,
      }),
    )
  })
  it('未开场计划过期可以载入最新本场数据，已开场计划保持只读', async () => {
    const props = { plan: teamPlan, t: teamTournament, busy: false, run }
    const page = render(
      <TeamPlanEditor {...props} error={new ApiError(409, 'stale_team_plan', '名单已更新')} />,
    )
    const user = userEvent.setup()
    expect(screen.getByRole('button', { name: '保存出场计划' }).hasAttribute('disabled')).toBe(true)
    await user.click(screen.getByRole('button', { name: '载入最新本场计划' }))
    await screen.findByText('已载入最新本场名单，请重新核对。')
    expect(screen.getByRole('combobox', { name: '队伍1 出场成员' }).textContent).toContain('成员2')
    page.rerender(<TeamPlanEditor {...props} error={null} />)
    await user.click(screen.getByRole('button', { name: '保存出场计划' }))
    await waitFor(() =>
      expect(saveTeamPlan).toHaveBeenCalledWith(6, 21, expect.objectContaining({ version: 4 })),
    )
    page.unmount()
    render(
      <TeamPlanEditor
        {...props}
        plan={{ ...teamPlan, status: 'started', table_id: 2 }}
        error={null}
      />,
    )
    expect(screen.getByRole('button', { name: '保存出场计划' }).hasAttribute('disabled')).toBe(true)
  })
  it('位置代表整批保存，不强制不同位置使用不同人；已开场队伍的代表不可改', async () => {
    const stage: TeamStage = {
      id: 9,
      stage_number: 1,
      cycle: 1,
      position_label: '先锋',
      games_per_team: 2,
      match_count: 2,
      confirmed_matches: 1,
      representatives: [
        { team_id: 1, member_id: 1, locked: true },
        { team_id: 2, member_id: 3, locked: false },
        { team_id: 3, member_id: 5, locked: false },
        { team_id: 4, member_id: 7, locked: false },
      ],
    }
    render(
      <TeamRepresentativesEditor
        t={{ ...teamTournament, status: 'started' }}
        ws={teamWorkspace}
        stage={stage}
        busy={false}
        error={null}
        run={run}
      />,
    )
    const user = userEvent.setup()
    expect(screen.getByRole('combobox', { name: '队伍1 先锋代表' }).hasAttribute('disabled')).toBe(
      true,
    )
    await selectOption(user, '队伍2 先锋代表', '成员4')
    await user.click(screen.getByRole('button', { name: '保存位置代表名单' }))
    await waitFor(() =>
      expect(setTeamRepresentatives).toHaveBeenCalledWith(
        6,
        9,
        expect.objectContaining({
          revision: 3,
          representatives: [
            { team_id: 1, member_id: 1 },
            { team_id: 2, member_id: 4 },
            { team_id: 3, member_id: 5 },
            { team_id: 4, member_id: 7 },
          ],
        }),
      ),
    )
  })
  it('清空未开场位置代表时显式提交null，不跳过该队或沿用旧人员', async () => {
    const stage: TeamStage = {
      id: 9,
      stage_number: 1,
      cycle: 1,
      position_label: '先锋',
      games_per_team: 2,
      match_count: 2,
      confirmed_matches: 0,
      representatives: teamTournament.teams.map((team) => ({
        team_id: team.id,
        member_id: team.members[0].id,
        locked: false,
      })),
    }
    render(
      <TeamRepresentativesEditor
        t={teamTournament}
        ws={teamWorkspace}
        stage={stage}
        busy={false}
        error={null}
        run={run}
      />,
    )
    const user = userEvent.setup()
    await selectOption(user, '队伍1 先锋代表', '等待队长指定')
    await user.click(screen.getByRole('button', { name: '保存位置代表名单' }))
    await waitFor(() =>
      expect(setTeamRepresentatives).toHaveBeenCalledWith(
        6,
        9,
        expect.objectContaining({
          representatives: [
            { team_id: 1, member_id: null },
            { team_id: 2, member_id: 3 },
            { team_id: 3, member_id: 5 },
            { team_id: 4, member_id: 7 },
          ],
        }),
      ),
    )
  })
  it('固定位置手动分组只提交四队，不提交或编辑本位置代表名单', async () => {
    const t = {
      ...teamTournament,
      pairing_strategy: 'team_manual_v1' as const,
      teams: [
        ...teamTournament.teams,
        {
          id: 5,
          name: '队伍5',
          members: [
            {
              ...teamTournament.teams[0].members[0],
              id: 9,
              participant_id: 9,
              player_id: 9,
              display_name: '成员9',
            },
          ],
        },
      ],
    }
    render(
      <TeamPlanEditor
        t={t}
        plan={{ ...teamPlan, stage_id: 9, position_label: '先锋', cycle: 1 }}
        busy={false}
        error={null}
        run={run}
      />,
    )
    const user = userEvent.setup()
    expect(screen.queryByRole('combobox', { name: '队伍1 出场成员' })).toBeNull()
    await selectOption(user, '参赛队伍 1', '队伍5')
    await user.click(screen.getByRole('button', { name: '保存四队分组' }))
    await waitFor(() =>
      expect(saveTeamPlan).toHaveBeenCalledWith(6, 21, {
        version: 1,
        team_ids: [5, 2, 3, 4],
        captain_supplied: true,
      }),
    )
  })
})
describe('团队抽签作用域和审计', () => {
  const draw: TeamLottery = {
    id: 12,
    entity_type: 'team',
    members: [1, 2],
    order: [2, 1],
    method: '现场团队纸签',
    description: '公开监督',
    drawn_at: '2026-11-10T08:00:00Z',
    created_by_id: 1,
    created_at: '2026-11-10T08:00:00Z',
    confirmed_by_id: null,
    confirmed_at: null,
    voided_by_id: null,
    voided_at: null,
    void_reason: '',
    source_versions: teamWorkspace.source_versions,
    roster_snapshot: teamWorkspace.roster_snapshot,
    plan_sources: teamWorkspace.plan_sources,
  }
  it('公开团队顺序保存后仍需显式二次确认，完整来源由团队API携带', async () => {
    vi.mocked(recordTeamLottery).mockResolvedValue(draw)
    render(
      <TeamLotteryEditor
        t={{ ...teamTournament, status: 'started' }}
        ws={{ ...teamWorkspace, unresolved_groups: [[1, 2]] }}
        members={[1, 2]}
        busy={false}
        error={null}
        run={run}
        refresh={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    await selectOption(user, '团队抽签顺位 1', '队伍2')
    await selectOption(user, '团队抽签顺位 2', '队伍1')
    await user.type(screen.getByLabelText('团队抽签方式'), '现场纸签')
    await user.type(screen.getByLabelText('实际团队抽签时间'), '2026-11-10T16:00')
    await user.type(screen.getByLabelText('团队公开过程说明'), '全员监督')
    await user.click(screen.getByRole('button', { name: '保存公开团队抽签' }))
    await waitFor(() =>
      expect(recordTeamLottery).toHaveBeenCalledWith(
        6,
        expect.objectContaining({ roster_snapshot: teamWorkspace.roster_snapshot }),
        expect.objectContaining({ members: [1, 2], order: [2, 1] }),
      ),
    )
    expect(confirmLottery).not.toHaveBeenCalled()
    expect(await screen.findByRole('button', { name: '二次确认团队抽签' })).toBeTruthy()
  })
  it('已有团队抽签先二次确认，不能把来源不同的同整数ID记录当成当前待确认', async () => {
    const current = { ...teamWorkspace, unresolved_groups: [[1, 2]], lotteries: [draw] }
    render(
      <TeamLotteryEditor
        t={{ ...teamTournament, status: 'started' }}
        ws={current}
        members={[1, 2]}
        busy={false}
        error={null}
        run={run}
        refresh={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    expect(screen.queryByRole('button', { name: '保存公开团队抽签' })).toBeNull()
    await user.click(screen.getByRole('button', { name: '二次确认团队抽签' }))
    await waitFor(() => expect(confirmLottery).toHaveBeenCalledWith(6, 12))
  })
  it('团队抽签作废有原因和二次确认，已结束记录保留历史', async () => {
    vi.mocked(voidLottery).mockResolvedValue({
      ...draw,
      voided_at: '2026-11-10T09:00:00Z',
      voided_by_id: 1,
      void_reason: '队伍顺序写错',
    })
    render(
      <TeamLotteryEditor
        t={{ ...teamTournament, status: 'started' }}
        ws={{ ...teamWorkspace, unresolved_groups: [[1, 2]], lotteries: [draw] }}
        members={[1, 2]}
        busy={false}
        error={null}
        run={run}
        refresh={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('作废原因'), '队伍顺序写错')
    await user.click(screen.getByRole('button', { name: '预览作废团队记录' }))
    expect(voidLottery).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '确认作废团队记录' }))
    await waitFor(() => expect(voidLottery).toHaveBeenCalledWith(6, 12, '队伍顺序写错'))
    expect((await screen.findByRole('status')).textContent).toContain('记录已作废')
    expect(screen.getByRole('button', { name: '保存公开团队抽签' })).toBeTruthy()
  })
})

describe('位置代表回读来源', () => {
  it('过期面板显式回读后使用最新revision与代表名单', async () => {
    const stage: TeamStage = {
      id: 9,
      stage_number: 1,
      cycle: 1,
      position_label: '先锋',
      games_per_team: 2,
      match_count: 2,
      confirmed_matches: 0,
      representatives: teamTournament.teams.map((team) => ({
        team_id: team.id,
        member_id: team.members[0].id,
        locked: false,
      })),
    }
    vi.mocked(fetchTeamWorkspace).mockResolvedValue({
      ...teamWorkspace,
      revision: 9,
      stages: [
        {
          ...stage,
          representatives: stage.representatives.map((r) =>
            r.team_id === 1 ? { ...r, member_id: 2 } : r,
          ),
        },
      ],
    })
    render(
      <TeamRepresentativesEditor
        t={teamTournament}
        ws={teamWorkspace}
        stage={stage}
        busy={false}
        error={new ApiError(409, 'stale_tournament', '代表名单已变化')}
        run={run}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '载入最新位置名单' }))
    await screen.findByText('已载入最新位置代表名单。')
    expect(screen.getByRole('combobox', { name: '队伍1 先锋代表' }).textContent).toContain('成员2')
    await user.click(screen.getByRole('button', { name: '保存位置代表名单' }))
    await waitFor(() =>
      expect(setTeamRepresentatives).toHaveBeenCalledWith(
        6,
        9,
        expect.objectContaining({ revision: 9 }),
      ),
    )
  })
})
