import { afterEach, describe, expect, it, vi } from 'vitest'
import { teamWorkspace } from '@/test/team-fixtures'
import {
  saveTeamPlan,
  completeTeam,
  setTeamRepresentatives,
  generateTeamSchedule,
  fetchTeamPlans,
  startTeamBatch,
  recordTeamLottery,
} from './teams'

afterEach(() => vi.unstubAllGlobals())
function mockFetch() {
  const fetcher = vi
    .fn()
    .mockImplementation(
      async (url: string) =>
        new Response(
          JSON.stringify({ data: url.endsWith('/auth/csrf/') ? { csrf_token: 'test-only' } : {} }),
        ),
    )
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}
describe('团队赛API契约', () => {
  it('出场计划提交版本和成员归属，写前获取CSRF并携带会话', async () => {
    const fetcher = mockFetch()
    const body = { version: 2, lineup: [{ team_id: 1, member_id: 7 }], captain_supplied: true }
    await saveTeamPlan(6, 21, body)
    expect(fetcher.mock.calls[1][0]).toBe('/api/v1/tournaments/6/team/plans/21/')
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: 'PUT', credentials: 'include' })
    expect(fetcher.mock.calls[1][1].headers['X-CSRFToken']).toBe('test-only')
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(body)
  })
  it('整批位置代表名单带最新revision，不要求五个不同人', async () => {
    const fetcher = mockFetch()
    const body = {
      revision: 12,
      representatives: [
        { team_id: 1, member_id: 2 },
        { team_id: 2, member_id: 3 },
      ],
      captain_supplied: true,
    }
    await setTeamRepresentatives(6, 15, body)
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(body)
    expect(fetcher.mock.calls[1][0]).toContain('/stages/15/representatives/')
  })
  it('团队完赛提交完整来源，冠军由服务器决定', async () => {
    const fetcher = mockFetch()
    await completeTeam(6, teamWorkspace)
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      confirmed: true,
      source_versions: teamWorkspace.source_versions,
      roster_snapshot: teamWorkspace.roster_snapshot,
      plan_sources: teamWorkspace.plan_sources,
    })
  })
  it('赛程/开场提交签名且明确确认，场次读取带分页与阶段', async () => {
    const fetcher = mockFetch()
    await generateTeamSchedule(6, 'schedule-token')
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      token: 'schedule-token',
      confirmed: true,
    })
    await startTeamBatch(6, 'batch-token')
    expect(JSON.parse(fetcher.mock.calls[3][1].body)).toEqual({
      token: 'batch-token',
      confirmed: true,
    })
    await fetchTeamPlans(6, 3, 15, 'draft')
    expect(fetcher.mock.calls[4][0]).toContain('page=3&stage=15&status=draft')
  })
  it('团队抽签明确实体类型、成员组和来源，避免与个人整数ID混用', async () => {
    const fetcher = mockFetch()
    const body = {
      members: [1, 2],
      order: [2, 1],
      method: '现场纸签',
      description: '公开',
      drawn_at: '2026-11-10T08:00:00Z',
    }
    await recordTeamLottery(6, teamWorkspace, body)
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      ...body,
      entity_type: 'team',
      source_versions: teamWorkspace.source_versions,
      roster_snapshot: teamWorkspace.roster_snapshot,
      plan_sources: teamWorkspace.plan_sources,
    })
  })
})
