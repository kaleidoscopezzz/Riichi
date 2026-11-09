import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateRound } from './rounds'
import {
  saveResult,
  correctResult,
  previewResult,
  fetchResultCorrections,
  displayScore,
  completeTournament,
  voidLottery,
  isPendingLottery,
  mergeLotteries,
  type Lottery,
} from './competition'

afterEach(() => vi.unstubAllGlobals())
describe('赛事 API 契约和无损展示', () => {
  it('试算与更正使用独立接口、当前版本和CSRF，历史读取不写入', async () => {
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
    const controller = new AbortController()
    const points = [{ participant_id: 1, raw_points: 0 }]
    await previewResult(20, 2, points, controller.signal)
    expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal)
    expect(fetcher.mock.calls[1][0]).toBe('/api/v1/round-tables/20/result/preview/')
    expect(fetcher.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      signal: controller.signal,
      credentials: 'include',
    })
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ version: 2, points })
    await correctResult(20, 2, points, '抄录修正')
    expect(fetcher.mock.calls[3][0]).toBe('/api/v1/round-tables/20/result/correct/')
    expect(JSON.parse(fetcher.mock.calls[3][1].body)).toEqual({
      version: 2,
      points,
      reason: '抄录修正',
    })
    expect(fetcher.mock.calls[3][1].headers['X-CSRFToken']).toBe('test-only')
    await fetchResultCorrections(20, controller.signal)
    expect(fetcher.mock.calls[4][0]).toBe('/api/v1/round-tables/20/result/corrections/')
    expect(fetcher.mock.calls[4][1].method).toBe('GET')
  })
  it('取消试算也取消获取CSRF，不继续发送试算请求', async () => {
    const fetcher = vi.fn().mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal!.addEventListener('abort', () =>
            reject(new DOMException('cancelled', 'AbortError')),
          )
        }),
    )
    vi.stubGlobal('fetch', fetcher)
    const controller = new AbortController()
    const request = previewResult(20, 2, [], controller.signal)
    controller.abort()
    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('首轮发送明确机器顺序，后续轮次不重新选桌', async () => {
    const fetcher = vi.fn().mockImplementation(
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
    const fetcher = vi.fn().mockImplementation(
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

const lottery: Lottery = {
  id: 7,
  members: [1, 2],
  order: [2, 1],
  method: '签条',
  description: '公开',
  drawn_at: '2026-11-04T12:00:00Z',
  created_by_id: 1,
  created_at: '2026-11-04T12:01:00Z',
  confirmed_by_id: null,
  confirmed_at: null,
  voided_by_id: null,
  voided_at: null,
  void_reason: '',
  source_versions: [{ table_id: 3, version: 2 }],
}
describe('积分展示边界与抽签契约', () => {
  it('舍入为零的负值不显示负号，负分母先移到分子，分母为 0 或非法时返回占位', () => {
    expect(displayScore({ numerator: '-1', denominator: '1000' })).toBe('0.00')
    expect(displayScore({ numerator: '-4', denominator: '1000' })).toBe('0.00')
    expect(displayScore({ numerator: '-5', denominator: '1000' })).toBe('−0.01')
    expect(displayScore({ numerator: '1', denominator: '-3' })).toBe('−0.33')
    expect(displayScore({ numerator: '-50', denominator: '-3' })).toBe('16.67')
    expect(displayScore({ numerator: '0', denominator: '-7' })).toBe('0.00')
    expect(displayScore({ numerator: '5', denominator: '0' })).toBe('—')
    expect(displayScore({ numerator: '1.5', denominator: '2' })).toBe('—')
    expect(displayScore({ numerator: 'x', denominator: '1' })).toBe('—')
  })
  it('作废抽签提交原因到 void 接口，返回该记录', async () => {
    const fetcher = vi.fn().mockImplementation(
      async (url: string) =>
        new Response(
          JSON.stringify({
            data: url.endsWith('/auth/csrf/')
              ? { csrf_token: 'test-only' }
              : { ...lottery, voided_at: '2026-11-04T13:00:00Z', void_reason: '顺序录错' },
          }),
        ),
    )
    vi.stubGlobal('fetch', fetcher)
    const row = await voidLottery(5, 7, '顺序录错')
    expect(fetcher.mock.calls[1][0]).toBe('/api/v1/tournaments/5/lotteries/7/void/')
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: 'POST' })
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ reason: '顺序录错' })
    expect(row.void_reason).toBe('顺序录错')
  })
  it('待确认：未确认、未作废、成员集合与来源版本均相同', () => {
    const versions = [{ table_id: 3, version: 2 }]
    expect(isPendingLottery(lottery, [1, 2], versions)).toBe(true)
    expect(isPendingLottery(lottery, [2, 1], versions)).toBe(true)
    expect(isPendingLottery(lottery, [1, 2, 3], versions)).toBe(false)
    expect(isPendingLottery(lottery, [1, 2], [{ table_id: 3, version: 3 }])).toBe(false)
    expect(isPendingLottery({ ...lottery, voided_at: 'now' }, [1, 2], versions)).toBe(false)
    expect(isPendingLottery({ ...lottery, confirmed_at: 'now' }, [1, 2], versions)).toBe(false)
  })
  it('写入响应覆盖旧读取，但已结束的服务器状态不被本地待确认副本覆盖', () => {
    const voided = { ...lottery, voided_at: 'now', void_reason: '录错' }
    expect(mergeLotteries([lottery], [voided])).toEqual([voided])
    expect(mergeLotteries([voided], [lottery])).toEqual([voided])
    expect(mergeLotteries([], [lottery])).toEqual([lottery])
  })
})
