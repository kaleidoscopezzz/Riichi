// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResultScorePreview } from './result-score-preview'
import { previewResult, type ResultPreview, type TablePoints } from '@/services/competition'
import type { RoundTable } from '@/services/rounds'

vi.mock('@/services/competition', async (original) => ({
  ...(await original<typeof import('@/services/competition')>()),
  previewResult: vi.fn(),
}))
const table: RoundTable = {
  id: 20,
  round_id: 1,
  round_number: 1,
  tournament_id: 1,
  table_number: 1,
  created_at: '',
  active_allocation: null,
  allocation_history: [],
  seats: ['east', 'south', 'west', 'north'].map((wind, index) => ({
    id: index + 1,
    participant_id: index + 1,
    player_id: index + 1,
    display_name: `选手${index + 1}`,
    seat_wind: wind as 'east' | 'south' | 'west' | 'north',
  })),
}
const points: TablePoints = [30000, 30000, 30000, 10000].map((raw_points, index) => ({
  participant_id: index + 1,
  raw_points,
}))
const rational = (numerator: string, denominator = '1') => ({ numerator, denominator })
const response: ResultPreview = {
  table_id: 20,
  version: 2,
  complete: true,
  valid_total: true,
  total: '100000',
  expected_total: '100000',
  difference: '0',
  scores: [
    {
      participant_id: 1,
      raw_points: 30000,
      rank: 1,
      tied: true,
      base: rational('0'),
      bonus: rational('50', '3'),
      score: rational('50', '3'),
    },
  ],
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(previewResult).mockResolvedValue(response)
})
afterEach(cleanup)
const props = { table, version: 2, points, invalid: false, disabled: false }

describe('服务端实时积分试算', () => {
  it('发送本桌输入与版本，显示零基础分及循环小数的精确值', async () => {
    render(<ResultScorePreview {...props} />)
    await waitFor(() =>
      expect(previewResult).toHaveBeenCalledWith(20, 2, points, expect.any(AbortSignal)),
    )
    const card = within(screen.getByRole('article', { name: '选手1 积分试算' }))
    await waitFor(() => expect(card.getAllByTitle('50/3')).toHaveLength(2))
    expect(card.getByTitle('0/1').textContent).toBe('0.00')
    expect(card.getAllByTitle('50/3').map((value) => value.textContent)).toEqual(['16.67', '16.67'])
    expect(card.getByText('并列第 1 名')).toBeTruthy()
  })
  it('修改数字后立即移除旧分数，并取消旧请求', async () => {
    let resolveNext!: (value: ResultPreview) => void
    vi.mocked(previewResult)
      .mockResolvedValueOnce(response)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveNext = resolve
        }),
      )
    const { rerender } = render(<ResultScorePreview {...props} />)
    await screen.findAllByText('16.67')
    const signal = vi.mocked(previewResult).mock.calls[0][3]!
    const next = points.map((point) => ({ ...point, raw_points: 25000 }))
    rerender(<ResultScorePreview {...props} points={next} />)
    expect(screen.queryByText('16.67')).toBeNull()
    expect(signal.aborted).toBe(true)
    await waitFor(() => expect(previewResult).toHaveBeenCalledTimes(2))
    await act(async () =>
      resolveNext({
        ...response,
        scores: [
          {
            ...response.scores[0],
            raw_points: 25000,
            rank: 1,
            tied: true,
            base: rational('-5'),
            bonus: rational('5'),
            score: rational('0'),
          },
        ],
      }),
    )
    const card = within(screen.getByRole('article', { name: '选手1 积分试算' }))
    expect(card.getByTitle('0/1').textContent).toBe('0.00')
  })
  it('传输层忽略取消时，迟到的旧响应也不能覆盖新数字的分数', async () => {
    let resolveOld!: (value: ResultPreview) => void
    vi.mocked(previewResult)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveOld = resolve
        }),
      )
      .mockResolvedValueOnce({
        ...response,
        scores: [
          {
            ...response.scores[0],
            raw_points: 40000,
            rank: 1,
            tied: false,
            base: rational('10'),
            bonus: rational('50'),
            score: rational('60'),
          },
        ],
      })
    const { rerender } = render(<ResultScorePreview {...props} />)
    await waitFor(() => expect(previewResult).toHaveBeenCalledTimes(1))
    rerender(
      <ResultScorePreview
        {...props}
        points={points.map((point, index) => ({ ...point, raw_points: index ? 20000 : 40000 }))}
      />,
    )
    await screen.findByText('60.00')
    await act(async () => resolveOld(response))
    expect(screen.getByText('60.00')).toBeTruthy()
    expect(screen.queryByText('16.67')).toBeNull()
  })
  it('非法格式或禁用时不试算；网络失败可明确重试', async () => {
    const { rerender } = render(<ResultScorePreview {...props} invalid />)
    expect(screen.getByText('请先修正点数格式。')).toBeTruthy()
    expect(previewResult).not.toHaveBeenCalled()
    rerender(<ResultScorePreview {...props} disabled />)
    expect(previewResult).not.toHaveBeenCalled()
    vi.mocked(previewResult)
      .mockRejectedValueOnce(new Error('连接中断'))
      .mockResolvedValueOnce(response)
    rerender(<ResultScorePreview {...props} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '重试试算' }))
    await screen.findAllByText('16.67')
    expect(previewResult).toHaveBeenCalledTimes(2)
  })
})
