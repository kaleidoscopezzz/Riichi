import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateRound } from './rounds'
import { saveResult, displayScore, completeTournament } from './competition'

afterEach(() => vi.unstubAllGlobals())
describe('赛事 API 契约和无损展示', () => {
  it('首轮发送明确机器顺序，后续轮次不重新选桌', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async (url: string) =>
          new Response(
            JSON.stringify({
              data: url.endsWith('/auth/csrf/') ? { csrf_token: 'test-only' } : { id: 1 },
            }),
          ),
      )
    vi.stubGlobal('fetch', fetcher)
    await generateRound(7, 1, [5, 2, 3, 6])
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      round_number: 1,
      machine_ids: [5, 2, 3, 6],
    })
    await generateRound(7, 2)
    expect(JSON.parse(fetcher.mock.calls[3][1].body)).toEqual({ round_number: 2 })
  })
  it('提交草稿版本和终局点数，不发送权威分值；409不自动重试', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { csrf_token: 'test-only' } })))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: 'stale_result', message: '版本冲突' } }), {
          status: 409,
        }),
      )
    vi.stubGlobal('fetch', fetcher)
    await expect(
      saveResult(3, 2, [
        { participant_id: 1, raw_points: -1000 },
        { participant_id: 2, raw_points: 0 },
      ]),
    ).rejects.toMatchObject({ code: 'stale_result' })
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      version: 2,
      points: [
        { participant_id: 1, raw_points: -1000 },
        { participant_id: 2, raw_points: 0 },
      ],
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
  it('完赛携带来源版本与明确确认，不提交冠军', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async (url: string) =>
          new Response(
            JSON.stringify({
              data: url.endsWith('/auth/csrf/') ? { csrf_token: 'test-only' } : {},
            }),
          ),
      )
    vi.stubGlobal('fetch', fetcher)
    await completeTournament(4, [{ table_id: 3, version: 2 }])
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      source_versions: [{ table_id: 3, version: 2 }],
      confirmed: true,
    })
  })
  it('分数仅近似展示，巨大分子也不经过浮点数', () => {
    expect(displayScore({ numerator: '50', denominator: '3' })).toBe('16.67')
    expect(displayScore({ numerator: '-1', denominator: '3' })).toBe('−0.33')
    expect(displayScore({ numerator: '900719925474099300', denominator: '1' })).toBe(
      '900719925474099300.00',
    )
  })
})
