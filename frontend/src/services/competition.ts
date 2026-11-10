import { api } from './api'

export type Rational = { numerator: string; denominator: string }
export type Version = { table_id: number; version: number }
export type ParticipantStatus = { participant_id: number; eliminated_after_round: number | null }
export type Score = {
  participant_id: number
  raw_points: number
  rank: number
  tied: boolean
  base: Rational
  bonus: Rational
  score: Rational
  round_number?: number
  table_number?: number
}
export type Result = {
  table_id: number
  version: number
  status: 'draft' | 'confirmed'
  points: Record<string, number | null>
  scores: Score[]
  confirmed_at: string | null
  correction_count?: number
}
export type TablePoints = { participant_id: number; raw_points: number | null }[]
export type ResultPreview = {
  table_id: number
  version: number
  complete: boolean
  valid_total: boolean
  total: string
  expected_total: string
  difference: string
  team_changes?: {
    participant_id: number
    team_id: number
    team_name: string
    confirmed_total: Rational
    previous_score: Rational
    score_change: Rational | null
    projected_total: Rational | null
  }[]
  team_source_versions?: Version[]
  scores: (Omit<Score, 'raw_points' | 'rank' | 'base' | 'bonus' | 'score'> & {
    raw_points: number | null
    rank: number | null
    base: Rational | null
    bonus: Rational | null
    score: Rational | null
  })[]
}
export type ResultCorrection = {
  id: number
  from_version: number
  to_version: number
  before: Pick<Result, 'table_id' | 'version' | 'status' | 'points' | 'scores'>
  after: Pick<Result, 'table_id' | 'version' | 'status' | 'points' | 'scores'>
  corrected_by: number
  corrected_by_username?: string
  corrected_at: string
  reason: string
}
export type Standing = {
  participant_id: number
  display_name: string
  rank: number | null
  total: Rational
  confirmed_rounds: number
  first_count: number
  second_count: number
  eliminated_after_round?: number | null
  highest_raw_points?: number | null
  fourth_count?: number
  fourth_avoidance_rate?: Rational | null
  rounds: Score[]
}
export type PerformanceStatistics = {
  fourth_avoidance: { value: Rational | null; participant_ids: number[] }
  highest_raw_points: { value: number | null; participant_ids: number[] }
  most_firsts: { value: number | null; participant_ids: number[] }
}
export type EliminationPlan = {
  round_number: number
  active_count: number
  remaining_count: number
  remaining_rounds: number
  ready: boolean
  candidates: Standing[]
  standings: Standing[]
  unresolved_groups: number[][]
  source_versions: Version[]
  participant_statuses: ParticipantStatus[]
}
export type EliminationRecord = {
  id: number
  round_number: number
  participant_ids: number[]
  confirmed_by: number
  confirmed_at: string
}
export type ReservationHistory = {
  id: number
  machine_id: number
  machine_no_snapshot: string
  status: string
  source: string
  /** Why the reservation was established. Releasing no longer overwrites it. */
  reason: string
  /** Why the reservation was released; empty while it is still active. */
  release_reason: string
}
export type FixedTable = {
  id: number
  ordinal: number
  label: string
  machine_id: number | null
  machine_no: string | null
  name: string | null
  history: ReservationHistory[]
}
export type Lottery = {
  id: number
  members: number[]
  order: number[]
  method: string
  description: string
  drawn_at: string
  created_by_id: number
  created_at: string
  confirmed_by_id: number | null
  confirmed_at: string | null
  voided_by_id: number | null
  voided_at: string | null
  void_reason: string
  source_versions: Version[]
  purpose?: 'final' | 'elimination'
  round_number?: number | null
  participant_statuses?: ParticipantStatus[]
}
export type Workspace = {
  status: string
  resource_state: string
  mapping: FixedTable[]
  standings: Standing[]
  /** Absent from a completed tournament's final snapshot. */
  unresolved_groups?: number[][]
  ready?: boolean
  all_results_confirmed?: boolean
  champion_id?: number
  source_versions: Version[]
  lotteries: Lottery[]
  completed_at?: string
  participant_statuses?: ParticipantStatus[]
  statistics?: PerformanceStatistics
  elimination?: EliminationPlan | null
  eliminations?: EliminationRecord[]
}
export const fetchWorkspace = (id: number, signal?: AbortSignal) =>
  api<Workspace>(`/tournaments/${id}/workspace/`, { signal })
export const fetchResult = (id: number, signal?: AbortSignal) =>
  api<Result>(`/round-tables/${id}/result/`, { signal })
export const previewResult = (
  id: number,
  version: number,
  points: TablePoints,
  signal?: AbortSignal,
) =>
  api<ResultPreview>(`/round-tables/${id}/result/preview/`, {
    method: 'POST',
    body: { version, points },
    signal,
  })
export const correctResult = (id: number, version: number, points: TablePoints, reason = '') =>
  api<Result>(`/round-tables/${id}/result/correct/`, {
    method: 'POST',
    body: { version, points, reason },
  })
export const fetchResultCorrections = (id: number, signal?: AbortSignal) =>
  api<{ table_id: number; corrections: ResultCorrection[] }>(
    `/round-tables/${id}/result/corrections/`,
    { signal },
  )
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
export const completeTournament = (
  id: number,
  source_versions: Version[],
  participant_statuses?: ParticipantStatus[],
) =>
  api<Workspace>(`/tournaments/${id}/complete/`, {
    method: 'POST',
    body: {
      source_versions,
      ...(participant_statuses ? { participant_statuses } : {}),
      confirmed: true,
    },
  })
export const eliminatePlayers = (id: number, plan: EliminationPlan) =>
  api<EliminationRecord>(`/tournaments/${id}/eliminations/`, {
    method: 'POST',
    body: {
      round_number: plan.round_number,
      participant_ids: plan.candidates.map((row) => row.participant_id),
      source_versions: plan.source_versions,
      participant_statuses: plan.participant_statuses,
      confirmed: true,
    },
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
    purpose?: 'final' | 'elimination'
    round_number?: number
    participant_statuses?: ParticipantStatus[]
  },
) => api<Lottery>(`/tournaments/${id}/lotteries/`, { method: 'POST', body })
export const confirmLottery = (id: number, lottery: number) =>
  api<Lottery>(`/tournaments/${id}/lotteries/${lottery}/confirm/`, {
    method: 'POST',
    body: { confirmed: true },
  })
export const voidLottery = (id: number, lottery: number, reason: string) =>
  api<Lottery>(`/tournaments/${id}/lotteries/${lottery}/void/`, {
    method: 'POST',
    body: { reason },
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

/** 409 codes after which the panel must re-read the workspace before anything else. */
export const conflictRefreshCodes: ReadonlySet<string> = new Set([
  'lottery_pending',
  'lottery_voided',
  'lottery_conflict',
  'tournament_completed',
  'stale_standings',
  'stale_result',
  'tournament_not_started',
  'stale_pairing',
  'stale_elimination',
  'elimination_not_available',
  'elimination_already_confirmed',
  'elimination_minimum',
  'elimination_lottery_required',
])

export function sameMembers(a: readonly number[], b: readonly number[]) {
  const left = new Set(a)
  const right = new Set(b)
  return left.size === right.size && [...left].every((pk) => right.has(pk))
}

// Same comparison as the server: the full ordered list of confirmed table versions.
export function sameVersions(a: readonly Version[], b: readonly Version[]) {
  return (
    a.length === b.length &&
    a.every((v, i) => v.table_id === b[i].table_id && v.version === b[i].version)
  )
}

/** Awaiting a second confirmation for exactly this tie group and these source results. */
export function isPendingLottery(
  lottery: Lottery,
  members: readonly number[],
  versions: readonly Version[],
  context?: {
    purpose: 'final' | 'elimination'
    round_number?: number
    participant_statuses?: ParticipantStatus[]
  },
) {
  return (
    !lottery.confirmed_at &&
    !lottery.voided_at &&
    (lottery.purpose ?? 'final') === (context?.purpose ?? 'final') &&
    (lottery.round_number ?? null) === (context?.round_number ?? null) &&
    sameParticipantStatuses(lottery.participant_statuses, context?.participant_statuses) &&
    sameMembers(lottery.members, members) &&
    sameVersions(lottery.source_versions ?? [], versions)
  )
}

export function sameParticipantStatuses(
  a: readonly ParticipantStatus[] | undefined,
  b: readonly ParticipantStatus[] | undefined,
) {
  if (!a?.length || !b?.length)
    return !(a?.length ? a : (b ?? [])).some((row) => row.eliminated_after_round !== null)
  return (
    a.length === b.length &&
    a.every(
      (row, i) =>
        row.participant_id === b[i].participant_id &&
        row.eliminated_after_round === b[i].eliminated_after_round,
    )
  )
}

const settled = (lottery: Lottery) => Boolean(lottery.confirmed_at || lottery.voided_at)

/**
 * Overlay write responses on a workspace read which may predate them. A record only
 * moves from pending to confirmed or voided, so a settled copy always wins.
 */
export function mergeLotteries(server: readonly Lottery[], local: readonly Lottery[]) {
  const rows = new Map(server.map((lottery) => [lottery.id, lottery]))
  for (const lottery of local) {
    const known = rows.get(lottery.id)
    if (!known || (settled(lottery) && !settled(known))) rows.set(lottery.id, lottery)
  }
  return [...rows.values()]
}

// Approximation for display ONLY. All ranking and accumulation comes from API.
export function displayScore(value: Rational) {
  let numerator: bigint
  let denominator: bigint
  try {
    numerator = BigInt(value.numerator)
    denominator = BigInt(value.denominator)
  } catch {
    return '—'
  }
  if (denominator === 0n) return '—'
  if (denominator < 0n) {
    numerator = -numerator
    denominator = -denominator
  }
  const negative = numerator < 0n
  const abs = negative ? -numerator : numerator
  const scaled = (abs * 100n + denominator / 2n) / denominator
  // A value which rounds to zero is shown unsigned, never as −0.00.
  const sign = negative && scaled !== 0n ? '−' : ''
  return `${sign}${scaled / 100n}.${String(scaled % 100n).padStart(2, '0')}`
}
export const exactScore = (v: Rational) => `${v.numerator}/${v.denominator}`
export function displayPercent(value: Rational) {
  try {
    return `${displayScore({ numerator: String(BigInt(value.numerator) * 100n), denominator: value.denominator })}%`
  } catch {
    return '—'
  }
}
