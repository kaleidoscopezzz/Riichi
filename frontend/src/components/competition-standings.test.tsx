// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Standings } from './competition-standings'
import type { Standing, PerformanceStatistics } from '@/services/competition'

afterEach(cleanup)
const rational = (numerator: string, denominator = '1') => ({ numerator, denominator })
const player: Standing = {
  participant_id: 1,
  display_name: '已确认选手',
  rank: 2,
  total: rational('249', '5'),
  confirmed_rounds: 3,
  first_count: 2,
  second_count: 0,
  highest_raw_points: 49800,
  fourth_avoidance_rate: rational('2', '3'),
  eliminated_after_round: null,
  rounds: [
    {
      participant_id: 1,
      raw_points: 49800,
      rank: 1,
      tied: false,
      base: rational('99', '5'),
      bonus: rational('30'),
      score: rational('249', '5'),
      round_number: 2,
      table_number: 1,
    },
  ],
}
const other: Standing = {
  ...player,
  participant_id: 2,
  display_name: '并列领先选手',
  rank: 1,
  eliminated_after_round: 2,
}
const statistics: PerformanceStatistics = {
  fourth_avoidance: { value: rational('2', '3'), participant_ids: [1, 2] },
  highest_raw_points: { value: 49800, participant_ids: [1, 2] },
  most_firsts: { value: 2, participant_ids: [1, 2] },
}

describe('清楚的成绩展示', () => {
  it('显示后端排名和两位小数，逐轮基础和奖励使用可读积分，精确值可展开', async () => {
    render(<Standings rows={[other, player]} completed={false} statistics={statistics} />)
    expect(screen.getAllByRole('row')[1].textContent).toContain('并列领先选手')
    expect(screen.queryByRole('columnheader', { name: '第一 / 第二' })).toBeNull()
    expect(screen.getByRole('columnheader', { name: '每轮成绩明细' })).toBeTruthy()
    const user = userEvent.setup()
    await user.click(screen.getAllByText('展开 1 轮成绩')[1])
    const card = screen.getAllByText('当桌最高分')[1].closest('article')!
    expect(card.textContent).toContain('49.80 分')
    expect(card.textContent).toContain('19.80 分')
    expect(card.textContent).toContain('30.00 分')
    expect(within(card).getByText('终局点数')).toBeTruthy()
    await user.click(within(card).getByText('查看精确值'))
    expect(within(card).getByText(/本轮 249\/5；基础 99\/5；顺位奖励 30\/1/)).toBeTruthy()
  })
  it('三个统计亮点显示全部并列领先者和样本口径，不按ID挑一人', async () => {
    render(<Standings rows={[other, player]} completed={false} statistics={statistics} />)
    const highlights = screen.getByLabelText('本场成绩亮点')
    expect(within(highlights).getByText('66.67%')).toBeTruthy()
    expect(within(highlights).getByText('49,800 点')).toBeTruthy()
    expect(within(highlights).getByText('2 次')).toBeTruthy()
    for (const card of within(highlights).getAllByRole('article')) {
      expect(card.textContent).toContain('已确认选手、并列领先选手')
    }
    const user = userEvent.setup()
    await user.click(screen.getByText('统计口径'))
    expect(screen.getByText(/并列第三不计第四/)).toBeTruthy()
  })
  it('无确认成绩时显示等待状态，淘汰状态和历史成绩继续可见', () => {
    render(
      <Standings
        rows={[other]}
        completed={false}
        statistics={{
          fourth_avoidance: { value: null, participant_ids: [] },
          highest_raw_points: { value: null, participant_ids: [] },
          most_firsts: { value: null, participant_ids: [] },
        }}
      />,
    )
    expect(screen.getAllByText('等待确认成绩')).toHaveLength(2)
    expect(screen.getByText(/第 2 轮后淘汰/)).toBeTruthy()
  })
})
