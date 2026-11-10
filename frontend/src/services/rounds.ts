import { api } from './api'
import type { Result } from './competition'
import type { PairingStrategy } from './tournaments'

export type Allocation = {
  id: number
  table_id: number
  machine_id: number
  machine_no: string
  machine_no_snapshot: string
  machine_status: string
  status: 'active' | 'released'
  allocated_at: string
  allocated_by: number
  released_at: string | null
  released_by: number | null
  release_reason: string
}
export type RoundSeat = {
  id: number
  participant_id: number
  player_id: number
  display_name: string
  seat_wind: 'east' | 'south' | 'west' | 'north'
}
export type RoundTable = {
  id: number
  round_id: number
  round_number: number
  tournament_id: number
  table_number: number
  result?: Result
  base_bonus?: string
  machine_snapshot?: { machine_id?: number; machine_no?: string }
  seats: RoundSeat[]
  active_allocation: Allocation | null
  allocation_history: Allocation[]
  created_at: string
}
export type TournamentRound = {
  id: number
  tournament_id: number
  round_number: number
  generated_at: string
  generated_by: number
  created_at: string
  tables: RoundTable[]
}
export type MachineResource = {
  machine_id: number
  machine_no: string
  name: string
  status: 'available' | 'maintenance' | 'disabled' | 'retired'
  assignable: boolean
  reservations?: { tournament_id: number; tournament_name: string; ordinal: number }[]
  active_allocation: {
    id: number
    table_id: number
    table_number: number
    round_number: number
    tournament_id: number
    tournament_name: string
  } | null
}
export const fetchRounds = (id: number, signal?: AbortSignal) =>
  api<{ results: TournamentRound[] }>(`/tournaments/${id}/rounds/`, { signal })
export const fetchResources = (signal?: AbortSignal) =>
  api<{ results: MachineResource[] }>('/machine-resources/', { signal })
export type PairingPlan = {
  round_number: number
  strategy: PairingStrategy
  strategy_label: string
  manual: boolean
  token: string
  participants: {
    id: number
    display_name: string
    total: { numerator: string; denominator: string }
  }[]
  tables: { ordinal: number; label: string; participant_ids: number[]; base_bonus: string }[]
  repeat_pairs: number
  repeat_encounters: number
}
export const previewPairing = (id: number, round_number: number, signal?: AbortSignal) =>
  api<PairingPlan>(`/tournaments/${id}/rounds/preview/`, {
    method: 'POST',
    body: { round_number },
    signal,
  })
export const generateRound = (
  id: number,
  round_number = 1,
  machine_ids?: number[],
  plan?: { pairing_token: string; participant_groups?: number[][] },
) =>
  api<TournamentRound>(`/tournaments/${id}/rounds/`, {
    method: 'POST',
    body: { round_number, ...(machine_ids ? { machine_ids } : {}), ...plan },
  })
export const fetchTable = (id: number) => api<RoundTable>(`/round-tables/${id}/`)
export const fetchAllocationHistory = (id: number) =>
  api<{ results: Allocation[] }>(`/round-tables/${id}/machine/history/`)
export const reassignMachine = (id: number, machine_id: number) =>
  api<RoundTable>(`/round-tables/${id}/machine/reassign/`, { method: 'POST', body: { machine_id } })
export const releaseMachine = (id: number, reason: string) =>
  api<RoundTable>(`/round-tables/${id}/machine/release/`, { method: 'POST', body: { reason } })
export const windLabels = { east: '东', south: '南', west: '西', north: '北' } as const
