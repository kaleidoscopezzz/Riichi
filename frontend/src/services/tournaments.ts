import { api, type Player } from './api'

export type Participant = {
  id: number
  player_id: number
  display_name: string
  is_active: boolean
  display_name_snapshot: string
  eliminated_after_round?: number | null
}
export type PairingStrategy =
  | 'legacy_v1'
  | 'random_v1'
  | 'ranked_v1'
  | 'manual_v1'
  | 'swiss_repeats_first_v1'
  | 'swiss_scores_first_v1'
export const pairingOptions = [
  { value: 'ranked_v1', label: '高高碰' },
  { value: 'random_v1', label: '完全随机' },
  { value: 'manual_v1', label: '手动拖拽分桌' },
] as const
export const pairingLabel = (strategy?: PairingStrategy) =>
  pairingOptions.find((option) => option.value === strategy)?.label ??
  (strategy === 'swiss_repeats_first_v1'
    ? '瑞士轮 · 避重优先（既有赛事）'
    : strategy === 'swiss_scores_first_v1'
      ? '瑞士轮 · 积分接近优先（既有赛事）'
      : '历史自动分桌')
export type Tournament = {
  id: number
  name: string
  description: string
  round_count: number
  starting_points: number
  return_points: number
  uma: string[]
  oka: string
  /** null derives Oka from points; "0" explicitly disables the top prize. */
  oka_override: string | null
  pairing_strategy?: PairingStrategy
  ranked_table_bonuses?: string[]
  status: 'draft' | 'started' | 'completed'
  created_by: number
  created_at: string
  updated_at: string
  started_at: string | null
  participant_count: number
  expected_table_count: number | null
  participants: Participant[]
  /** Read-only optimistic lock; a draft PATCH echoes it back (409 stale_tournament). */
  revision: number
}
export type TournamentInput = Pick<
  Tournament,
  | 'name'
  | 'description'
  | 'round_count'
  | 'starting_points'
  | 'return_points'
  | 'uma'
  | 'oka_override'
> & {
  participant_ids: number[]
  revision?: number
  pairing_strategy?: PairingStrategy
  ranked_table_bonuses?: string[]
}
export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }
export const legalSize = (count: number) => [4, 8, 12, 16].includes(count)
export const fetchTournaments = (
  page: number,
  search: string,
  status: string,
  signal?: AbortSignal,
) =>
  api<Page<Tournament>>(
    `/tournaments/?${new URLSearchParams({ page: String(page), search, status })}`,
    { signal },
  )
export const fetchTournament = (id: number) => api<Tournament>(`/tournaments/${id}/`)
export const saveTournament = (body: TournamentInput, id?: number) =>
  api<Tournament>(id ? `/tournaments/${id}/` : '/tournaments/', {
    method: id ? 'PATCH' : 'POST',
    body,
  })
export const startTournament = (id: number) =>
  api<Tournament>(`/tournaments/${id}/start/`, { method: 'POST', body: {} })
export const findPlayers = async (page: number, search: string, signal?: AbortSignal) => {
  const result = await api<Page<Player>>(
    `/players/?${new URLSearchParams({ page: String(page), search, eligible: 'true' })}`,
    { signal },
  )
  return {
    ...result,
    results: result.results.map((player) => ({ ...player, is_active: player.is_active !== false })),
  }
}

// An exact preview in thousandths. No floating-point scoring calculation.
export function previewOka(start: string, end: string) {
  if (!/^[0-9]+$/.test(start) || !/^[0-9]+$/.test(end)) return '—'
  const value = (BigInt(end) - BigInt(start)) * 4n
  const absolute = value < 0n ? -value : value
  const fraction = String(absolute % 1000n)
    .padStart(3, '0')
    .replace(/0+$/, '')
  return `${value < 0n ? '-' : '+'}${absolute / 1000n}${fraction ? `.${fraction}` : ''}`
}

export const validCustomOka = (value: string) =>
  value.length <= 64 && /^[+]?[0-9]+(?:\.[0-9]+)?$/.test(value)

export const describeOka = (value: string) =>
  /^[+-]?0+(?:\.0+)?$/.test(value) ? '0（无头名赏）' : value
