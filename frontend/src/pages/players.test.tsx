// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { selectOption } from '@/test/select-option'
import { PlayersPage } from './players'
import { api, ApiError, type Player } from '@/services/api'

vi.mock('@/services/api', async (original) => ({
  ...(await original<typeof import('@/services/api')>()),
  api: vi.fn(),
}))
const player: Player = {
  id: 5,
  nickname: '老板维护的选手',
  username: 'player_internal_never_display',
  is_active: true,
  can_delete: true,
  reference_count: 0,
  created_at: '2026-11-04T03:00:00Z',
  updated_at: '2026-11-04T03:00:00Z',
}
const page = { count: 1, next: null, previous: null, results: [player] }
const mocked = vi.mocked(api)
beforeEach(() => {
  vi.resetAllMocks()
  mocked.mockImplementation(async (path, options) =>
    options?.method ? player : path.startsWith('/players/?') ? page : player,
  )
})
afterEach(cleanup)
describe('老板维护选手', () => {
  it('真实列表不展示内部用户名，支持搜索和分页', async () => {
    mocked.mockImplementation(async (path) =>
      path.includes('page=2') ? { ...page, previous: 'page1' } : { ...page, next: 'page2' },
    )
    render(<PlayersPage />)
    const u = userEvent.setup()
    await screen.findByText(player.nickname)
    expect(screen.queryByText(player.username!)).toBeNull()
    await u.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() =>
      expect(mocked.mock.calls.some(([path]) => path.includes('page=2'))).toBe(true),
    )
    await u.type(screen.getByLabelText('搜索选手昵称'), '小李')
    await u.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() =>
      expect(
        mocked.mock.calls.some(([path]) => decodeURIComponent(path).includes('search=小李')),
      ).toBe(true),
    )
  })
  it('新建只发送昵称，保存成功刷新真实数据', async () => {
    render(<PlayersPage />)
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: '新增选手' }))
    await u.type(screen.getByLabelText('选手昵称'), '新选手')
    await u.click(screen.getByRole('button', { name: '保存选手' }))
    await screen.findByText('新增选手成功。')
    expect(mocked).toHaveBeenCalledWith('/players/', {
      method: 'POST',
      body: { nickname: '新选手' },
    })
  })
  it('编辑前取最新详情，保留稳定ID', async () => {
    render(<PlayersPage />)
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: `编辑选手 ${player.nickname}` }))
    const input = screen.getByLabelText('选手昵称')
    await u.clear(input)
    await u.type(input, '更新昵称')
    await u.click(screen.getByRole('button', { name: '保存选手' }))
    await screen.findByText('编辑选手成功。')
    expect(mocked).toHaveBeenCalledWith('/players/5/', {
      method: 'PATCH',
      body: { nickname: '更新昵称' },
    })
  })
  it('删除需确认，取消不写入，删除有明确body', async () => {
    render(<PlayersPage />)
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: `删除选手 ${player.nickname}` }))
    await u.click(screen.getByRole('button', { name: '取消' }))
    expect(mocked.mock.calls.some(([, o]) => o?.method === 'DELETE')).toBe(false)
    await u.click(screen.getByRole('button', { name: `删除选手 ${player.nickname}` }))
    await u.click(screen.getByRole('button', { name: '确认删除选手' }))
    await screen.findByText('删除选手成功。')
    expect(mocked).toHaveBeenCalledWith('/players/5/', {
      method: 'DELETE',
      body: { confirmed: true },
    })
  })
  it('有引用只提供归档，说明历史保护并可恢复', async () => {
    mocked.mockImplementation(async (path, options) =>
      options?.method
        ? player
        : path.startsWith('/players/?')
          ? { ...page, results: [{ ...player, can_delete: false, reference_count: 2 }] }
          : { ...player, can_delete: false, reference_count: 2 },
    )
    render(<PlayersPage />)
    const u = userEvent.setup()
    await screen.findByText(player.nickname)
    expect(screen.queryByRole('button', { name: `删除选手 ${player.nickname}` })).toBeNull()
    await u.click(screen.getByRole('button', { name: `归档选手 ${player.nickname}` }))
    expect(screen.getByRole('dialog').textContent).toContain('历史参赛关系、昵称快照与成绩保持不变')
    await u.click(screen.getByRole('button', { name: '确认归档选手' }))
    await screen.findByText('归档选手成功。')
    expect(mocked).toHaveBeenCalledWith('/players/5/archive/', {
      method: 'POST',
      body: { confirmed: true },
    })
    mocked.mockImplementation(async (path, options) =>
      options?.method
        ? player
        : path.startsWith('/players/?')
          ? { ...page, results: [{ ...player, is_active: false }] }
          : { ...player, is_active: false },
    )
    await selectOption(u, '选手状态', '已归档')
    await u.click(await screen.findByRole('button', { name: `恢复选手 ${player.nickname}` }))
    await u.click(screen.getByRole('button', { name: '确认恢复选手' }))
    await screen.findByText('恢复选手成功。')
    expect(mocked).toHaveBeenCalledWith('/players/5/restore/', {
      method: 'POST',
      body: { confirmed: true },
    })
  })
  it.each([400, 403, 404, 409])('%i错误保留反馈不自动重放写入', async (status) => {
    mocked.mockImplementation(async (path, options) => {
      if (options?.method) throw new ApiError(status, 'player_conflict', `真实错误${status}`)
      return path.startsWith('/players/?') ? page : player
    })
    render(<PlayersPage />)
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: '新增选手' }))
    await u.type(screen.getByLabelText('选手昵称'), '测试')
    await u.click(screen.getByRole('button', { name: '保存选手' }))
    expect((await screen.findByRole('alert')).textContent).toContain(`真实错误${status}`)
    expect(mocked.mock.calls.filter(([, o]) => o?.method).length).toBe(1)
  })
})
