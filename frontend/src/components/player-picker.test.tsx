// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PlayerPicker } from './player-picker'
import { TournamentEditor } from './tournament-editor'
import { findPlayers, saveTournament, type Participant } from '@/services/tournaments'

vi.mock('@/services/tournaments', async (original) => ({
  ...(await original<typeof import('@/services/tournaments')>()),
  findPlayers: vi.fn(),
  saveTournament: vi.fn(),
}))
const players = Array.from({ length: 24 }, (_, i) => ({
  id: i + 1,
  nickname: i < 2 ? '小明' : `选手${i + 1}`,
  username: `private-${i}`,
  is_active: true,
  created_at: '',
  updated_at: '',
}))
const page = (results = players, next: string | null = null) => ({
  count: 24,
  previous: null,
  next,
  results,
})
function Harness({ initial = [] }: { initial?: Participant[] }) {
  const [selected, change] = useState(initial)
  return <PlayerPicker selected={selected} change={change} disabled={false} />
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(findPlayers).mockResolvedValue(page())
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})
const input = () => screen.getByRole('combobox', { name: '搜索参赛选手' })
const option = (id: number) =>
  screen.getByRole('option', { name: new RegExp(`选手 #${id}(?:$|已选)`) })

describe('参赛选手实时联想', () => {
  it('保留草稿昵称快照与ID；禁用时不查询或变更名单', async () => {
    const change = vi.fn()
    const initial: Participant[] = [
      {
        id: 80,
        player_id: 1,
        display_name: '草稿原昵称',
        is_active: true,
        display_name_snapshot: '历史快照',
      },
    ]
    const view = render(<PlayerPicker selected={initial} change={change} disabled />)
    expect((input() as HTMLInputElement).disabled).toBe(true)
    expect(
      (screen.getByRole('button', { name: '移除 草稿原昵称（选手 #1）' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
    expect(findPlayers).not.toHaveBeenCalled()
    view.rerender(<PlayerPicker selected={initial} change={change} disabled={false} />)
    const user = userEvent.setup()
    await user.click(input())
    await screen.findAllByRole('option')
    expect(option(1).getAttribute('aria-selected')).toBe('true')
    await user.click(option(1))
    expect(change).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '移除 草稿原昵称（选手 #1）' })).toBeTruthy()
  })

  it('键盘向上导航、ARIA活动项和Tab离开后焦点不被抢回', async () => {
    const user = userEvent.setup()
    render(
      <>
        <Harness />
        <button type="button">下一操作</button>
      </>,
    )
    await user.click(input())
    await screen.findAllByRole('option')
    await user.keyboard('{ArrowUp}')
    expect(input().getAttribute('aria-activedescendant')).toBe(option(24).id)
    await user.keyboard('{Tab}')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '下一操作' }))
    expect(input().getAttribute('aria-expanded')).toBe('false')
  })
  it('聚焦查询、250ms防抖、立即取消旧请求；忽略乱序返回及卸载后的返回', async () => {
    vi.useFakeTimers()
    const pending: {
      search: string
      signal?: AbortSignal
      resolve: (v: ReturnType<typeof page>) => void
    }[] = []
    vi.mocked(findPlayers).mockImplementation(
      (_page, search, signal) =>
        new Promise((resolve) => pending.push({ search, signal, resolve })),
    )
    const view = render(<Harness />)
    fireEvent.focus(input())
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(pending[0].search).toBe('')
    fireEvent.change(input(), { target: { value: '小' } })
    expect(pending[0].signal?.aborted).toBe(true)
    await act(() => vi.advanceTimersByTimeAsync(249))
    expect(findPlayers).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    fireEvent.change(input(), { target: { value: '小明' } })
    expect(pending[1].signal?.aborted).toBe(true)
    await act(() => vi.advanceTimersByTimeAsync(250))
    await act(async () => {
      pending[2].resolve(page([players[1]]))
    })
    await act(async () => {
      pending[0].resolve(page([players[4]]))
      pending[1].resolve(page([players[3]]))
    })
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(option(2)).toBeTruthy()
    fireEvent.change(input(), { target: { value: '后' } })
    await act(() => vi.advanceTimersByTimeAsync(250))
    view.unmount()
    expect(pending[3].signal?.aborted).toBe(true)
    await act(async () => {
      pending[3].resolve(page())
    })
  })

  it('中文组合输入不请求或选择；结束后才搜索，方向键/Enter选择并保留焦点', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(input())
    await screen.findAllByRole('option')
    await user.keyboard('{ArrowDown}')
    fireEvent.compositionStart(input())
    expect(input().getAttribute('aria-activedescendant')).toBeNull()
    fireEvent.change(input(), { target: { value: '明' } })
    fireEvent.keyDown(input(), { key: 'Enter', keyCode: 229, isComposing: true })
    expect(screen.getByText('已选 0 / 16 人')).toBeTruthy()
    await new Promise((resolve) => setTimeout(resolve, 280))
    expect(findPlayers).toHaveBeenCalledTimes(1)
    fireEvent.compositionEnd(input(), { data: '明' })
    await waitFor(() =>
      expect(findPlayers).toHaveBeenLastCalledWith(1, '明', expect.any(AbortSignal)),
    )
    await screen.findAllByRole('option')
    await user.keyboard('{ArrowDown}{Enter}')
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
    expect((input() as HTMLInputElement).value).toBe('')
    expect(document.activeElement).toBe(input())
    await user.keyboard('{Escape}')
    expect(input().getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(input())
  })

  it('同名不同ID、重复点击、连续4/8/12/16人、满员和移除；不显示内部用户名', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(input())
    await screen.findAllByRole('option')
    for (let id = 1; id <= 16; id++) {
      await user.click(option(id))
      if ([4, 8, 12, 16].includes(id)) expect(screen.getByText(`已选 ${id} / 16 人`)).toBeTruthy()
    }
    await user.click(option(1))
    await user.click(option(17))
    expect(screen.getByText('已选 16 / 16 人')).toBeTruthy()
    expect(screen.getByText(/已满 16 人/)).toBeTruthy()
    expect(screen.queryByText(/private-/)).toBeNull()
    await user.click(screen.getByRole('button', { name: '移除 小明（选手 #1）' }))
    await user.click(input())
    await screen.findAllByRole('option')
    await user.click(option(17))
    expect(screen.getByText('已选 16 / 16 人')).toBeTruthy()
    expect(screen.getByRole('button', { name: '移除 小明（选手 #2）' })).toBeTruthy()
  })

  it('分页追加去重、归档过滤；后续页失败重试不丢失已加载选手', async () => {
    vi.mocked(findPlayers)
      .mockResolvedValueOnce(page(players.slice(0, 20), '/next'))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(
        page([players[19], ...players.slice(20), { ...players[0], id: 99, is_active: false }]),
      )
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(input())
    await screen.findAllByRole('option')
    await user.click(screen.getByRole('button', { name: '加载更多选手' }))
    expect((await screen.findByRole('alert')).textContent).toContain('查询失败')
    expect(screen.getAllByRole('option')).toHaveLength(20)
    await user.click(screen.getByRole('button', { name: '重试选手查询' }))
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(24))
    expect(findPlayers).toHaveBeenLastCalledWith(2, '', expect.any(AbortSignal))
    expect(screen.queryByText('选手 #99')).toBeNull()
  })

  it('无结果、首屏失败与重试；外部点击收起、重新聚焦打开', async () => {
    vi.mocked(findPlayers).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page([]))
    const user = userEvent.setup()
    render(
      <>
        <Harness />
        <button type="button">外部操作</button>
      </>,
    )
    await user.click(input())
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: '重试选手查询' }))
    await screen.findByText('没有匹配的有效选手。')
    expect(document.activeElement).toBe(input())
    await user.click(screen.getByText('外部操作'))
    expect(input().getAttribute('aria-expanded')).toBe('false')
    await user.click(input())
    expect(input().getAttribute('aria-expanded')).toBe('true')
  })

  it('Sheet内选择/Escape不关闭表单，Enter不保存；提交只带选中ID', async () => {
    const close = vi.fn(),
      saved = vi.fn()
    const user = userEvent.setup()
    render(<TournamentEditor close={close} saved={saved} />)
    await user.type(screen.getByLabelText('赛事名称'), '真实草稿测试')
    await user.click(input())
    await screen.findAllByRole('option')
    await user.click(option(1))
    await user.keyboard('{ArrowDown}{Enter}{Escape}')
    expect(close).not.toHaveBeenCalled()
    expect(saveTournament).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    expect(saveTournament).toHaveBeenCalledWith(
      expect.objectContaining({ participant_ids: [1, 2] }),
      undefined,
    )
  })
})

describe('分页保留与归档标记（F8/F9）', () => {
  it('选中第 2 页选手后保留已加载结果与页码，只更新选中状态', async () => {
    vi.mocked(findPlayers)
      .mockResolvedValueOnce(page(players.slice(0, 20), '/next'))
      .mockResolvedValueOnce(page(players.slice(20)))
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(input())
    await screen.findAllByRole('option')
    await user.click(screen.getByRole('button', { name: '加载更多选手' }))
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(24))
    await user.click(option(22))
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
    expect(screen.getAllByRole('option')).toHaveLength(24)
    expect(option(22).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('已显示 24 / 24 人')).toBeTruthy()
    expect(findPlayers).toHaveBeenCalledTimes(2)
    expect(document.activeElement).toBe(input())
    // Keyboard picking continues in place on the loaded later page as well.
    await user.keyboard('{ArrowDown}{Enter}')
    expect(screen.getByText('已选 2 / 16 人')).toBeTruthy()
    const chosen = screen
      .getAllByRole('option')
      .filter((o) => o.getAttribute('aria-selected') === 'true')
    expect(chosen).toHaveLength(2)
    expect(screen.getAllByRole('option')).toHaveLength(24)
    expect(findPlayers).toHaveBeenCalledTimes(2)
  })
  it('第 1 页带查询词选中后仍清空查询，便于继续搜索', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), '小明')
    await waitFor(() =>
      expect(findPlayers).toHaveBeenLastCalledWith(1, '小明', expect.any(AbortSignal)),
    )
    await screen.findAllByRole('option')
    await user.click(option(2))
    expect((input() as HTMLInputElement).value).toBe('')
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
  })
  it('选中后的名单条目不含内部用户名', async () => {
    const change = vi.fn()
    const user = userEvent.setup()
    render(<PlayerPicker selected={[]} change={change} disabled={false} />)
    await user.click(input())
    await screen.findAllByRole('option')
    await user.click(option(1))
    expect(change).toHaveBeenCalledWith([
      { id: 0, player_id: 1, display_name: '小明', is_active: true, display_name_snapshot: '' },
    ])
    expect(change.mock.calls[0][0][0]).not.toHaveProperty('username')
  })
  it('草稿里的已归档选手显示标记与提示，移除后提示消失', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={[
          {
            id: 81,
            player_id: 30,
            display_name: '老会员',
            is_active: false,
            display_name_snapshot: '',
          },
          {
            id: 82,
            player_id: 2,
            display_name: '小明',
            is_active: true,
            display_name_snapshot: '',
          },
        ]}
      />,
    )
    const archived = screen.getByRole('button', { name: '移除 老会员（选手 #30，已归档）' })
    expect(archived.textContent).toContain('已归档')
    const hint = document.getElementById(archived.getAttribute('aria-describedby')!)
    expect(hint?.textContent).toContain('保存草稿会被拒绝')
    expect(hint?.textContent).toContain('老会员 #30')
    const active = screen.getByRole('button', { name: '移除 小明（选手 #2）' })
    expect(active.textContent).not.toContain('已归档')
    expect(active.getAttribute('aria-describedby')).toBeNull()
    await user.click(archived)
    expect(screen.queryByText(/保存草稿会被拒绝/)).toBeNull()
    expect(screen.getByText('已选 1 / 16 人')).toBeTruthy()
  })
})
