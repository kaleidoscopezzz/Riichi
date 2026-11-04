import { api, type Player } from './api'

export type Participant = {
  id: number
  player_id: number
  display_name: string
  username: string
  is_active: boolean
  display_name_snapshot: string
}
export type Tournament = {
  id: number
  name: string
  description: string
  round_count: number
  starting_points: number
  return_points: number
  uma: string[]
  oka: string
  status: 'draft' | 'started' | 'completed'
  created_by: number
  created_at: string
  updated_at: string
  started_at: string | null
  participant_count: number
  expected_table_count: number | null
  participants: Participant[]
}
export type TournamentInput = Pick<
  Tournament,
  'name' | 'description' | 'round_count' | 'starting_points' | 'return_points' | 'uma'
> & { participant_ids: number[] }
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
  return { ...result, results: result.results.map((player) => ({ ...player, is_active: true })) }
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
