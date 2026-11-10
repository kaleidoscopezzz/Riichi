import { api } from './api'
import type { Tournament } from './tournaments'
import type {
  Standing,
  Rational,
  Version,
  FixedTable,
  Lottery,
  PerformanceStatistics,
} from './competition'
import type { TournamentRound } from './rounds'

export type TeamMember = {
  id: number
  participant_id: number
  player_id: number
  display_name: string
  is_active: boolean
  is_captain: boolean
}
export type Team = { id: number; name: string; members: TeamMember[] }
export type TeamSettings = {
  schedule_mode: 'free' | 'positions'
  total_matches: number | null
  positions: string[]
  games_per_position: number
  cycles: number
  schedule_revision: number
}
export type TeamTournament = Tournament & {
  competition_type: 'team'
  teams: Team[]
  team_settings: TeamSettings
}
export type TeamInput = {
  competition_type: 'team'
  name: string
  description: string
  starting_points: number
  return_points: number
  uma: string[]
  oka_override: string | null
  pairing_strategy: 'team_balanced_v1' | 'team_manual_v1'
  schedule_mode: 'free' | 'positions'
  total_matches: number | null
  positions: string[]
  games_per_position: number
  cycles: number
  teams: { id?: number; name: string; player_ids: number[]; captain_player_id?: number | null }[]
  revision?: number
}
export type PlanSource = { match_id: number; version: number }
export type TeamPlan = {
  id: number
  match_number: number
  schedule_revision: number
  version: number
  stage_id: number | null
  team_ids: number[]
  lineup: Record<string, number | null>
  captain_supplied: boolean
  status: 'draft' | 'confirmed' | 'started' | 'completed' | 'voided'
  table_id: number | null
  batch_number: number | null
  cycle: number | null
  position_index: number | null
  position_label: string
  lineup_rows: {
    team_id: number
    team_name: string
    member_id: number | null
    participant_id: number | null
    display_name: string | null
  }[]
}
export type TeamStage = {
  id: number
  stage_number: number
  cycle: number
  position_label: string
  games_per_team: number
  match_count: number
  confirmed_matches: number
  representatives: {
    team_id: number
    member_id: number | null
    locked: boolean
    captain_supplied?: boolean
    confirmed_matches?: number
    planned_matches?: number
  }[]
}
export type Contribution = Standing & { team_id: number; team_name: string }
export type TeamStanding = {
  team_id: number
  name: string
  rank: number
  total: Rational
  first_count: number
  second_count: number
  confirmed_matches: number
  planned_matches: number
  contributions: Contribution[]
  matches: (Standing['rounds'][number] & {
    table_id: number
    display_name: string
    match_number: number
    position_label: string
    cycle: number | null
  })[]
}
export type RosterSource = { id: number; name: string; members: Omit<TeamMember, 'is_active'>[] }[]
export type TeamLottery = Lottery & {
  entity_type: 'team'
  roster_snapshot: RosterSource
  plan_sources: PlanSource[]
}
export type TeamWorkspace = {
  status: 'draft' | 'started' | 'completed'
  competition_type: 'team'
  revision: number
  teams: Team[]
  team_settings: TeamSettings
  team_standings: TeamStanding[]
  standings: Contribution[]
  statistics: PerformanceStatistics
  unresolved_groups?: number[][]
  ready?: boolean
  all_results_confirmed?: boolean
  source_versions: Version[]
  roster_snapshot: RosterSource
  plan_sources: PlanSource[]
  stages?: TeamStage[]
  current_stage_id?: number | null
  match_count: number
  completed_matches: number
  latest_batch_number?: number | null
  mapping: FixedTable[]
  resource_state: string
  lotteries: TeamLottery[]
  champion_team_id?: number
  completed_at?: string | null
}
export type PlanPage = { results: TeamPlan[]; count: number; page: number; has_next: boolean }
export type SchedulePreview = {
  match_count: number
  games_per_team: number
  preview_limit: number
  token: string
  preview_matches: {
    match_number: number
    stage_number: number | null
    cycle: number | null
    position_label: string
    team_ids: number[]
  }[]
}
export type TeamBatchPreview = {
  batch_number: number
  token: string
  tables: {
    ordinal: number
    match: TeamPlan
    mapping: { ordinal: number; machine_id: number; machine_no: string; name: string }
  }[]
}

export const fetchTeam = (id: number, signal?: AbortSignal) =>
  api<TeamTournament>(`/tournaments/${id}/`, { signal })
export const saveTeam = (body: TeamInput, id?: number) =>
  api<TeamTournament>(id ? `/tournaments/${id}/` : '/tournaments/', {
    method: id ? 'PATCH' : 'POST',
    body,
  })
export const fetchTeamWorkspace = (id: number, signal?: AbortSignal) =>
  api<TeamWorkspace>(`/tournaments/${id}/workspace/`, { signal })
export const previewTeamSchedule = (id: number, signal?: AbortSignal) =>
  api<SchedulePreview>(`/tournaments/${id}/team/schedule/preview/`, {
    method: 'POST',
    body: {},
    signal,
  })
export const generateTeamSchedule = (id: number, token: string) =>
  api(`/tournaments/${id}/team/schedule/generate/`, {
    method: 'POST',
    body: { token, confirmed: true },
  })
export const resetTeamSchedule = (id: number, revision: number, reason: string) =>
  api(`/tournaments/${id}/team/schedule/reset/`, {
    method: 'POST',
    body: { revision, reason, confirmed: true },
  })
export const fetchTeamPlans = (
  id: number,
  page = 1,
  stage?: number,
  status?: string,
  signal?: AbortSignal,
) =>
  api<PlanPage>(
    `/tournaments/${id}/team/plans/?${new URLSearchParams({ page: String(page), ...(stage ? { stage: String(stage) } : {}), ...(status ? { status } : {}) })}`,
    { signal },
  )
export const fetchTeamPlan = (id: number, match: number, signal?: AbortSignal) =>
  api<TeamPlan>(`/tournaments/${id}/team/plans/${match}/`, { signal })
export const saveTeamPlan = (
  id: number,
  plan: number,
  body: {
    version: number
    team_ids?: number[]
    lineup?: { team_id: number; member_id: number | null }[]
    captain_supplied: boolean
  },
) => api<TeamPlan>(`/tournaments/${id}/team/plans/${plan}/`, { method: 'PUT', body })
export const confirmTeamPlans = (id: number, plan_sources: PlanSource[]) =>
  api(`/tournaments/${id}/team/plans/confirm/`, {
    method: 'POST',
    body: { plan_sources, confirmed: true },
  })
export const withdrawTeamPlan = (id: number, plan: number, version: number, reason: string) =>
  api(`/tournaments/${id}/team/plans/${plan}/withdraw/`, {
    method: 'POST',
    body: { version, reason, confirmed: true },
  })
export const setTeamRepresentative = (
  id: number,
  stage: number,
  body: {
    revision: number
    team_id: number
    member_id: number | null
    captain_supplied: boolean
    withdraw_confirmed?: boolean
    reason?: string
  },
) =>
  api<{ revision: number }>(`/tournaments/${id}/team/stages/${stage}/representative/`, {
    method: 'PUT',
    body,
  })
export const setTeamRepresentatives = (
  id: number,
  stage: number,
  body: {
    revision: number
    representatives: { team_id: number; member_id: number | null }[]
    captain_supplied: boolean
    withdraw_confirmed?: boolean
    reason?: string
  },
) =>
  api<{ revision: number }>(`/tournaments/${id}/team/stages/${stage}/representatives/`, {
    method: 'PUT',
    body,
  })
export const fetchTeamBatches = (id: number, page = 1, signal?: AbortSignal) =>
  api<{ results: TournamentRound[]; count: number; page: number; has_next: boolean }>(
    `/tournaments/${id}/team/batches/?page=${page}`,
    { signal },
  )
export const previewTeamBatch = (id: number, machine_ids?: number[], signal?: AbortSignal) =>
  api<TeamBatchPreview>(`/tournaments/${id}/team/batches/preview/`, {
    method: 'POST',
    body: machine_ids ? { machine_ids } : {},
    signal,
  })
export const startTeamBatch = (id: number, token: string) =>
  api<TournamentRound>(`/tournaments/${id}/team/batches/start/`, {
    method: 'POST',
    body: { token, confirmed: true },
  })
export const startTeam = (id: number) =>
  api<TeamTournament>(`/tournaments/${id}/start/`, { method: 'POST', body: {} })
export const completeTeam = (id: number, ws: TeamWorkspace) =>
  api<TeamWorkspace>(`/tournaments/${id}/complete/`, {
    method: 'POST',
    body: {
      confirmed: true,
      source_versions: ws.source_versions,
      roster_snapshot: ws.roster_snapshot,
      plan_sources: ws.plan_sources,
    },
  })
export const recordTeamLottery = (
  id: number,
  ws: TeamWorkspace,
  body: {
    members: number[]
    order: number[]
    method: string
    description: string
    drawn_at: string
  },
) =>
  api<TeamLottery>(`/tournaments/${id}/lotteries/`, {
    method: 'POST',
    body: {
      ...body,
      entity_type: 'team',
      source_versions: ws.source_versions,
      roster_snapshot: ws.roster_snapshot,
      plan_sources: ws.plan_sources,
    },
  })
export const fetchTeamAudit = (id: number, page = 1, signal?: AbortSignal) =>
  api<{
    results: {
      id: number
      action: string
      revision: number
      before: unknown
      after: unknown
      reason: string
      created_by: number
      created_at: string
    }[]
    page: number
    has_next: boolean
  }>(`/tournaments/${id}/team/audit/?page=${page}`, { signal })
