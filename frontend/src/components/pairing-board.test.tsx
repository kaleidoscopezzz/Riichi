// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { selectOption } from '@/test/select-option'
import { PairingBoard } from './pairing-board'
import { previewPairing, generateRound, type PairingPlan } from '@/services/rounds'
import type { Tournament } from '@/services/tournaments'
import { ApiError } from '@/services/api'

vi.mock('@/services/rounds', async (original) => ({
  ...(await original<typeof import('@/services/rounds')>()),
  previewPairing: vi.fn(),
  generateRound: vi.fn(),
}))
const plan: PairingPlan = {
  round_number: 1,
  strategy: 'manual_v1',
  strategy_label: '手动分桌',
  manual: true,
  token: 'qa-plan',
  participants: Array.from({ length: 8 }, (_, index) => ({
    id: index + 1,
    display_name: `选手${index + 1}`,
    total: { numerator: '0', denominator: '1' },
  })),
  tables: [
    { ordinal: 1, label: 'A', participant_ids: [1, 2, 3, 4], base_bonus: '0' },
    { ordinal: 2, label: 'B', participant_ids: [5, 6, 7, 8], base_bonus: '0' },
  ],
  repeat_pairs: 0,
  repeat_encounters: 0,
}
const tournament = { id: 5, pairing_strategy: 'manual_v1' } as Tournament
const run = async (operation: () => Promise<unknown>) => {
  await operation()
}
const props = {
  tournament,
  next: 1,
  machineIds: [1, 2],
  ready: true,
  busy: false,
  error: null,
  run,
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(previewPairing).mockResolvedValue(plan)
  vi.mocked(generateRound).mockResolvedValue({} as never)
})
afterEach(cleanup)

describe('手动分桌与预览确认', () => {
  it('重新预览的迟到响应不能覆盖切换后的轮次，卸载时也会取消', async () => {
    let late!: (value: PairingPlan) => void
    vi.mocked(previewPairing)
      .mockResolvedValueOnce(plan)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          late = resolve
        }),
      )
      .mockResolvedValueOnce({
        ...plan,
        round_number: 2,
        strategy_label: '当前新轮',
        token: 'new-current',
      })
    const { rerender, unmount } = render(<PairingBoard {...props} />)
    const user = userEvent.setup()
    await screen.findByRole('combobox', { name: '移动 选手1 至' })
    await user.click(screen.getByRole('button', { name: '重新预览分桌' }))
    await waitFor(() => expect(previewPairing).toHaveBeenCalledTimes(2))
    const signal = vi.mocked(previewPairing).mock.calls[1][2]!
    rerender(<PairingBoard {...props} next={2} />)
    await screen.findByText('当前新轮 · 第 2 轮')
    expect(signal.aborted).toBe(true)
    await act(async () => late(plan))
    expect(screen.getByText('当前新轮 · 第 2 轮')).toBeTruthy()
    const currentSignal = vi.mocked(previewPairing).mock.calls[2][2]!
    unmount()
    expect(currentSignal.aborted).toBe(true)
  })
  it('键盘移动到另一桌交换选手，确认提交原token和实际四人分组', async () => {
    render(<PairingBoard {...props} />)
    const user = userEvent.setup()
    await screen.findByRole('combobox', { name: '移动 选手1 至' })
    await selectOption(user, '移动 选手1 至', 'B桌 · 选手5')
    expect(
      within(screen.getByRole('article', { name: '逻辑桌 A 分组' })).getByText('选手5'),
    ).toBeTruthy()
    expect(
      within(screen.getByRole('article', { name: '逻辑桌 B 分组' })).getByText('选手1'),
    ).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '预览并确认' }))
    expect(generateRound).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '确认生成轮次' }))
    await waitFor(() =>
      expect(generateRound).toHaveBeenCalledWith(5, 1, [1, 2], {
        pairing_token: 'qa-plan',
        participant_groups: [
          [5, 2, 3, 4],
          [1, 6, 7, 8],
        ],
      }),
    )
  })
  it('自动瑞士预览只读并显示重复，不发送手动分组覆盖', async () => {
    vi.mocked(previewPairing).mockResolvedValue({
      ...plan,
      manual: false,
      strategy: 'swiss_repeats_first_v1',
      strategy_label: '瑞士轮 · 避重优先',
      repeat_pairs: 4,
      repeat_encounters: 4,
    })
    render(<PairingBoard {...props} next={2} machineIds={undefined} />)
    const user = userEvent.setup()
    await screen.findByText(/预计 4 对重复对手/)
    expect(screen.queryByRole('combobox')).toBeNull()
    await user.click(screen.getByRole('button', { name: '预览并确认' }))
    await user.click(screen.getByRole('button', { name: '确认生成轮次' }))
    await waitFor(() =>
      expect(generateRound).toHaveBeenCalledWith(5, 2, undefined, { pairing_token: 'qa-plan' }),
    )
  })
  it('未选齐物理桌、忙碌或旧预览时不能生成', async () => {
    const { rerender } = render(<PairingBoard {...props} ready={false} />)
    await screen.findByRole('combobox', { name: '移动 选手1 至' })
    expect(screen.getByRole('button', { name: '预览并确认' }).hasAttribute('disabled')).toBe(true)
    rerender(<PairingBoard {...props} error={new ApiError(409, 'stale_pairing', '成绩已变化')} />)
    expect(screen.getByRole('button', { name: '预览并确认' }).hasAttribute('disabled')).toBe(true)
    rerender(<PairingBoard {...props} busy />)
    expect(screen.getByRole('button', { name: '正在提交…' }).hasAttribute('disabled')).toBe(true)
    expect(generateRound).not.toHaveBeenCalled()
  })
  it('切换目标轮次时取消旧请求，乱序旧响应不能覆盖新计划', async () => {
    let resolveOld!: (value: PairingPlan) => void
    vi.mocked(previewPairing)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveOld = resolve
        }),
      )
      .mockResolvedValueOnce({
        ...plan,
        round_number: 2,
        strategy_label: '新轮分组',
        token: 'new-plan',
      })
    const { rerender } = render(<PairingBoard {...props} />)
    await waitFor(() => expect(previewPairing).toHaveBeenCalledTimes(1))
    const signal = vi.mocked(previewPairing).mock.calls[0][2]!
    rerender(<PairingBoard {...props} next={2} />)
    await screen.findByText('新轮分组 · 第 2 轮')
    expect(signal.aborted).toBe(true)
    await act(async () => resolveOld(plan))
    expect(screen.queryByText('手动分桌 · 第 1 轮')).toBeNull()
  })
})
