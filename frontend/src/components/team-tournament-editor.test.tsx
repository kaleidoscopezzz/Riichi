// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TeamTournamentEditor } from './team-tournament-editor'
import { teamTournament } from '@/test/team-fixtures'
import { selectOption } from '@/test/select-option'
import { saveTeam, fetchTeam } from '@/services/teams'
import { findPlayers } from '@/services/tournaments'
import { ApiError } from '@/services/api'
vi.mock('@/services/teams', async (original) => ({
  ...(await original<typeof import('@/services/teams')>()),
  saveTeam: vi.fn(),
  fetchTeam: vi.fn(),
}))
vi.mock('@/services/tournaments', async (original) => ({
  ...(await original<typeof import('@/services/tournaments')>()),
  findPlayers: vi.fn(),
}))
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(saveTeam).mockResolvedValue(teamTournament)
  vi.mocked(fetchTeam).mockResolvedValue(teamTournament)
  vi.mocked(findPlayers).mockResolvedValue({
    count: 8,
    next: null,
    previous: null,
    results: teamTournament.teams
      .flatMap((t) => t.members)
      .map((m) => ({
        id: m.player_id,
        nickname: m.display_name,
        is_active: true,
        created_at: teamTournament.created_at,
        updated_at: teamTournament.created_at,
        date_joined: teamTournament.created_at,
      })),
  })
})
describe('团队赛创建与名单', () => {
  it('按固定位置循环保存独立场数与循环，不发送个人赛round_count', async () => {
    render(<TeamTournamentEditor tournament={teamTournament} close={vi.fn()} saved={vi.fn()} />)
    const user = userEvent.setup()
    await selectOption(user, '团队赛程模式', '固定位置依次循环')
    await user.clear(screen.getByLabelText('每位置每队场数'))
    await user.type(screen.getByLabelText('每位置每队场数'), '4')
    await user.clear(screen.getByLabelText('循环次数'))
    await user.type(screen.getByLabelText('循环次数'), '2')
    await user.click(screen.getByRole('button', { name: '保存团队草稿' }))
    await waitFor(() => expect(saveTeam).toHaveBeenCalled())
    const body = vi.mocked(saveTeam).mock.calls[0][0]
    expect(body).toMatchObject({
      competition_type: 'team',
      schedule_mode: 'positions',
      total_matches: null,
      games_per_position: 4,
      cycles: 2,
      revision: 1,
    })
    expect(body.positions).toEqual(['先锋', '次峰', '中间', '副将', '大将'])
    expect(body).not.toHaveProperty('round_count')
  })
  it('队伍可增减，各队人数不必相同，名单超过16仍保留全部成员', async () => {
    const t = {
      ...teamTournament,
      participant_count: 24,
      teams: teamTournament.teams.map((team) => ({
        ...team,
        members: Array.from({ length: 6 }, (_, j) => ({
          ...team.members[0],
          id: team.id * 10 + j,
          participant_id: team.id * 10 + j,
          player_id: team.id * 10 + j,
          display_name: `成员${team.id}-${j}`,
        })),
      })),
    }
    render(<TeamTournamentEditor tournament={t} close={vi.fn()} saved={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '保存团队草稿' }))
    await waitFor(() => expect(saveTeam).toHaveBeenCalled())
    expect(
      vi.mocked(saveTeam).mock.calls[0][0].teams.reduce((n, row) => n + row.player_ids.length, 0),
    ).toBe(24)
    expect(screen.getByText('4 支队伍 · 24 名成员')).toBeTruthy()
  })
  it('其他队已选的同一选手不能重复加入本队，仍使用统一Picker', async () => {
    render(<TeamTournamentEditor tournament={teamTournament} close={vi.fn()} saved={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox', { name: '搜索队伍 2 成员' }))
    const option = await screen.findByRole('option', { name: /成员1/ })
    expect(option.getAttribute('aria-disabled')).toBe('true')
    await user.click(option)
    expect(screen.getAllByText('已选 2 / 4096 人')).toHaveLength(4)
    expect(document.querySelectorAll('select:not([aria-hidden="true"])')).toHaveLength(0)
  })
  it('非法整数不发送，409保留输入并允许显式载入最新团队草稿', async () => {
    render(<TeamTournamentEditor tournament={teamTournament} close={vi.fn()} saved={vi.fn()} />)
    const user = userEvent.setup()
    await user.clear(screen.getByLabelText('总桌场次'))
    await user.type(screen.getByLabelText('总桌场次'), '1e3')
    await user.click(screen.getByRole('button', { name: '保存团队草稿' }))
    expect(saveTeam).not.toHaveBeenCalled()
    await user.clear(screen.getByLabelText('总桌场次'))
    await user.type(screen.getByLabelText('总桌场次'), '8')
    vi.mocked(saveTeam).mockRejectedValueOnce(
      new ApiError(409, 'stale_tournament', '团队草稿已变化'),
    )
    await user.click(screen.getByRole('button', { name: '保存团队草稿' }))
    expect((screen.getByLabelText('总桌场次') as HTMLInputElement).value).toBe('8')
    vi.mocked(fetchTeam).mockResolvedValueOnce({
      ...teamTournament,
      revision: 4,
      name: '服务器最新团队名',
    })
    await user.click(await screen.findByRole('button', { name: '重新加载最新团队草稿' }))
    await waitFor(() =>
      expect((screen.getByLabelText('赛事名称') as HTMLInputElement).value).toBe(
        '服务器最新团队名',
      ),
    )
    expect(saveTeam).toHaveBeenCalledTimes(1)
  })
})
