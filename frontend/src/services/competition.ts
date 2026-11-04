import { api } from './api'

export type Rational = { numerator: string; denominator: string }
export type Version = { table_id: number; version: number }
export type Score = {
  participant_id: number
  raw_points: number
  rank: number
  tied: boolean
  base: Rational
  bonus: Rational
  score: Rational
  round_number?: number
}
export type Result = {
  table_id: number
  version: number
  status: 'draft' | 'confirmed'
  points: Record<string, number | null>
  scores: Score[]
  confirmed_at: string | null
}
export type Standing = {
  participant_id: number
  display_name: string
  rank: number
  total: Rational
  confirmed_rounds: number
  first_count: number
  second_count: number
  rounds: Score[]
}
export type FixedTable = {
  id: number
  ordinal: number
  label: string
  machine_id: number | null
  machine_no: string | null
  name: string | null
  history: {
    id: number
    machine_id: number
    machine_no_snapshot: string
    status: string
    source: string
    reason: string
  }[]
}
export type Lottery = {
  id: number
  members: number[]
  order: number[]
  method: string
  description: string
  confirmed_at: string | null
}
export type Workspace = {
  status: string
  resource_state: string
  mapping: FixedTable[]
  standings: Standing[]
  unresolved_groups: number[][]
  ready?: boolean
  all_results_confirmed?: boolean
  champion_id?: number
  source_versions: Version[]
  lotteries: Lottery[]
  completed_at?: string
}
export const fetchWorkspace = (id: number, signal?: AbortSignal) =>
  api<Workspace>(`/tournaments/${id}/workspace/`, { signal })
export const saveResult = (
  id: number,
  version: number,
  points: { participant_id: number; raw_points: number | null }[],
  confirm = false,
) =>
  api<Result>(`/round-tables/${id}/result/${confirm ? 'confirm/' : ''}`, {
    method: confirm ? 'POST' : 'PUT',
    body: { version, points },
  })
export const completeTournament = (id: number, source_versions: Version[]) =>
  api<Workspace>(`/tournaments/${id}/complete/`, {
    method: 'POST',
    body: { source_versions, confirmed: true },
  })
export const recordLottery = (
  id: number,
  body: {
    members: number[]
    order: number[]
    method: string
    description: string
    drawn_at: string
    source_versions: Version[]
  },
) => api<Lottery>(`/tournaments/${id}/lotteries/`, { method: 'POST', body })
export const confirmLottery = (id: number, lottery: number) =>
  api<Lottery>(`/tournaments/${id}/lotteries/${lottery}/confirm/`, {
    method: 'POST',
    body: { confirmed: true },
  })
export const replaceTable = (id: number, ordinal: number, machine_id: number, reason: string) =>
  api<FixedTable[]>(`/tournaments/${id}/tables/replace/`, {
    method: 'POST',
    body: { ordinal, machine_id, reason },
  })
export const reviewLegacy = (
  id: number,
  historical_only: boolean,
  machine_ids: number[],
  reason: string,
) =>
  api<FixedTable[]>(`/tournaments/${id}/compatibility-review/`, {
    method: 'POST',
    body: { historical_only, machine_ids, reason },
  })

// Approximation for display ONLY. All ranking and accumulation comes from API.
export function displayScore(value: Rational) {
  const n = BigInt(value.numerator),
    d = BigInt(value.denominator)
  const negative = n < 0n
  const abs = negative ? -n : n
  const scaled = (abs * 100n + d / 2n) / d
  return `${negative ? '−' : ''}${scaled / 100n}.${String(scaled % 100n).padStart(2, '0')}`
}
export const exactScore = (v: Rational) => `${v.numerator}/${v.denominator}`
