import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Trophy, Users, Flag } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { FormFeedback } from '@/components/form-feedback'
import { TeamTournamentEditor } from '@/components/team-tournament-editor'
import {
  TeamSheet,
  TeamPlanEditor,
  TeamRepresentativesEditor,
  TeamLotteryEditor,
} from '@/components/team-actions'
import { TeamStandings } from '@/components/team-standings'
import { Standings } from '@/components/competition-standings'
import { TableResultEditor } from '@/components/table-result-editor'
import { ResultCorrectionHistory } from '@/components/result-correction-history'
import { ApiError } from '@/services/api'
import {
  fetchResources,
  windLabels,
  type MachineResource,
  type RoundTable,
  type TournamentRound,
} from '@/services/rounds'
import { displayScore, exactScore, replaceTable } from '@/services/competition'
import {
  fetchTeam,
  fetchTeamWorkspace,
  fetchTeamPlans,
  fetchTeamPlan,
  fetchTeamBatches,
  previewTeamSchedule,
  generateTeamSchedule,
  resetTeamSchedule,
  confirmTeamPlans,
  withdrawTeamPlan,
  previewTeamBatch,
  startTeamBatch,
  startTeam,
  completeTeam,
  fetchTeamAudit,
  type TeamTournament,
  type TeamWorkspace,
  type TeamPlan,
  type TeamStage,
  type SchedulePreview,
  type TeamBatchPreview,
  type PlanSource,
} from '@/services/teams'

type Action =
  | { mode: 'schedule' }
  | { mode: 'start' }
  | { mode: 'batch' }
  | { mode: 'complete' }
  | { mode: 'reset' }
  | { mode: 'audit' }
  | { mode: 'plan' | 'confirm-plan' | 'withdraw'; plan: TeamPlan }
  | { mode: 'representatives' | 'confirm-stage'; stage: TeamStage }
  | { mode: 'result' | 'correct' | 'history'; table: RoundTable }
  | { mode: 'lottery'; members: number[] }
  | { mode: 'replace'; ordinal: number }

export function TeamTournamentPage() {
  const { id } = useParams()
  const tournamentId = Number(id)
  const [t, setT] = useState<TeamTournament | null>(null)
  const [ws, setWs] = useState<TeamWorkspace | null>(null)
  const [plans, setPlans] = useState<TeamPlan[]>([])
  const [planCount, setPlanCount] = useState(0)
  const [planNext, setPlanNext] = useState(false)
  const [planPage, setPlanPage] = useState(1)
  const [planStatus, setPlanStatus] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [batches, setBatches] = useState<TournamentRound[]>([])
  const [batchPage, setBatchPage] = useState(1)
  const [batchNext, setBatchNext] = useState(false)
  const [resources, setResources] = useState<MachineResource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [success, setSuccess] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<Action | null>(null)
  const [editing, setEditing] = useState(false)
  const [operationError, setOperationError] = useState<Error | null>(null)
  const [schedulePreview, setSchedulePreview] = useState<SchedulePreview | null>(null)
  const [batchPreview, setBatchPreview] = useState<TeamBatchPreview | null>(null)
  const [tableCount, setTableCount] = useState('1')
  const [selectedMachines, setSelectedMachines] = useState<number[]>([])
  const [reason, setReason] = useState('')
  const [target, setTarget] = useState('')
  const [stageSources, setStageSources] = useState<PlanSource[]>([])
  const [stagePlans, setStagePlans] = useState<TeamPlan[]>([])
  const [confirmationStale, setConfirmationStale] = useState(false)
  const [audits, setAudits] = useState<Awaited<ReturnType<typeof fetchTeamAudit>>['results']>([])
  const [auditPage, setAuditPage] = useState(1)
  const [auditNext, setAuditNext] = useState(false)
  const focusReturn = useRef<HTMLElement | null>(null)
  const heading = useRef<HTMLElement>(null)
  const actionEpoch = useRef(0)
  const loaded = t?.id === tournamentId && ws !== null
  const refresh = () => setRevision((value) => value + 1)
  function close() {
    actionEpoch.current++
    setAction(null)
    setEditing(false)
    requestAnimationFrame(() =>
      (focusReturn.current?.isConnected ? focusReturn.current : heading.current)?.focus(),
    )
  }
  function open(next: Action) {
    actionEpoch.current++
    focusReturn.current = document.activeElement as HTMLElement
    setAction(next)
    setOperationError(null)
    setReason('')
    setTarget('')
    setSchedulePreview(null)
    setBatchPreview(null)
    setStageSources([])
    setStagePlans([])
    setConfirmationStale(false)
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void Promise.all([
      fetchTeam(tournamentId, controller.signal),
      fetchTeamWorkspace(tournamentId, controller.signal),
      fetchTeamPlans(
        tournamentId,
        planPage,
        stageFilter ? Number(stageFilter) : undefined,
        planStatus || undefined,
        controller.signal,
      ),
      fetchTeamBatches(tournamentId, batchPage, controller.signal),
      fetchResources(controller.signal),
    ])
      .then(([team, workspace, p, b, r]) => {
        if (!controller.signal.aborted) {
          setT(team)
          setWs(workspace)
          setPlans(p.results)
          setPlanCount(p.count)
          setPlanNext(p.has_next)
          setBatches(b.results)
          setBatchNext(b.has_next)
          setResources(r.results)
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e as Error)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [tournamentId, revision, planPage, stageFilter, planStatus, batchPage])
  async function run(operation: () => Promise<unknown>, message: string, stay = false) {
    if (busy) return
    setBusy(true)
    setOperationError(null)
    try {
      await operation()
      if (!stay) {
        close()
        setSuccess(message)
        refresh()
      }
    } catch (e) {
      setOperationError(e as Error)
      if (e instanceof ApiError && e.status === 409) {
        if (action?.mode === 'confirm-plan' || action?.mode === 'confirm-stage') {
          setConfirmationStale(true)
        }
        refresh()
      }
    } finally {
      setBusy(false)
    }
  }
  async function loadStagePlans(stage: TeamStage) {
    const epoch = actionEpoch.current
    await run(
      async () => {
        const rows: TeamPlan[] = []
        let page = 1
        while (true) {
          const data = await fetchTeamPlans(tournamentId, page, stage.id)
          rows.push(...data.results)
          if (!data.has_next) break
          page++
        }
        if (epoch === actionEpoch.current) {
          const draft = rows.filter((p) => p.status === 'draft')
          setStagePlans(draft)
          setStageSources(draft.map((p) => ({ match_id: p.id, version: p.version })))
          setConfirmationStale(false)
        }
      },
      '',
      true,
    )
  }
  async function loadAudit(page: number) {
    await run(
      async () => {
        const data = await fetchTeamAudit(tournamentId, page)
        setAudits(data.results)
        setAuditNext(data.has_next)
        setAuditPage(page)
      },
      '',
      true,
    )
  }
  const completed = t?.status === 'completed'
  const selectedStage = ws?.stages?.find((s) => s.id === Number(stageFilter || ws.current_stage_id))
  const sourceLabel = (plan: TeamPlan) =>
    plan.position_label ? `第 ${plan.cycle} 循环 · ${plan.position_label}` : '自由场次'
  const title = action
    ? action.mode === 'plan'
      ? `第 ${action.plan.match_number} 场${action.plan.stage_id ? '四队分组' : '出场名单'}`
      : action.mode === 'representatives'
        ? `第 ${action.stage.cycle} 循环 · ${action.stage.position_label}代表`
        : {
            schedule: '预览并确认赛程',
            start: '确认启动团队赛',
            batch: '预览下一开赛时段',
            complete: '确认团队赛完赛',
            reset: '撤回未开场赛程',
            audit: '团队赛操作历史',
            'confirm-plan': '确认本场出场名单',
            'confirm-stage': '确认本位置出场计划',
            withdraw: '撤回本场确认',
            result: '团队赛半庄成绩',
            correct: '更正团队赛半庄成绩',
            history: '成绩更正记录',
            lottery: '团队公开抽签',
            replace: '故障替换物理桌',
          }[action.mode]
    : ''
  return (
    <div className="competition-workspace team-workspace">
      <Link className="back-link" to="/tournaments">
        <ArrowLeft size={16} />
        返回赛事管理
      </Link>
      <section className="competition-hero" tabIndex={-1} ref={heading}>
        <div>
          <span className="eyebrow">TEAM TOURNAMENT / 团队赛工作台</span>
          <h2>{t?.name ?? '团队赛'}</h2>
          <p>每桌四队各一人，按队员已确认有效积分汇总团队成绩。</p>
        </div>
        <Button variant="outline" disabled={loading} onClick={refresh}>
          <RefreshCw size={16} />
          刷新团队工作台
        </Button>
      </section>
      <FormFeedback error={error} success={success} />
      {loading && loaded && <p role="status">正在刷新团队赛数据…</p>}
      {loading && !loaded ? (
        <p role="status">正在读取团队、赛程和成绩…</p>
      ) : error ? (
        <Button onClick={refresh}>重新读取团队赛</Button>
      ) : (
        t &&
        ws && (
          <>
            <div className="competition-progress">
              <span>
                {t.teams.length} 支队伍 · {t.participant_count} 名登记成员
              </span>
              <span>
                {ws.completed_matches} / {ws.match_count} 桌场确认
              </span>
              <Badge variant="outline">
                {completed ? '已完赛 · 只读' : t.status === 'draft' ? '团队草稿' : '进行中'}
              </Badge>
            </div>
            {completed && (
              <section className="champion-panel">
                <Trophy size={34} />
                <span className="eyebrow">TEAM CHAMPION / 团队冠军</span>
                <h2>
                  {ws.team_standings.find((row) => row.team_id === ws.champion_team_id)?.name}
                </h2>
                <p>团队冠军、队员贡献和成绩已归档，本赛桌关联已结束。</p>
              </section>
            )}
            <section className="settings-panel">
              <div className="competition-section-heading">
                <h3>赛制与阵容</h3>
                <span>
                  {t.team_settings.schedule_mode === 'free' ? '按整体场次' : '固定位置依次循环'}
                </span>
              </div>
              <p>
                {t.team_settings.schedule_mode === 'free'
                  ? `配置 ${t.team_settings.total_matches} 总桌场次，队长逐场指定成员。`
                  : `${t.team_settings.positions.join(' → ')}；每位置每队 ${t.team_settings.games_per_position} 场，共 ${t.team_settings.cycles} 个循环。`}
              </p>
              <p>
                开局 {t.starting_points} 点 · 返还 {t.return_points} 点 · Oka {t.oka} · Uma{' '}
                {t.uma.join(' / ')}；团队按精确积分总和排名。
              </p>
              <details>
                <summary>查看 {t.teams.length} 支队伍成员</summary>
                <div className="team-roster-grid">
                  {t.teams.map((team) => (
                    <article key={team.id}>
                      <h4>{team.name}</h4>
                      <p>
                        {team.members
                          .map((m) => `${m.display_name}${m.is_captain ? '（队长）' : ''}`)
                          .join('、') || '尚无成员'}
                      </p>
                    </article>
                  ))}
                </div>
              </details>
              {t.status === 'draft' && (
                <div className="team-button-row">
                  <Button
                    variant="outline"
                    disabled={ws.match_count > 0}
                    onClick={() => {
                      focusReturn.current = document.activeElement as HTMLElement
                      setEditing(true)
                    }}
                  >
                    编辑团队草稿
                  </Button>
                  <Button disabled={!ws.match_count} onClick={() => open({ mode: 'start' })}>
                    启动团队赛
                  </Button>
                </div>
              )}
            </section>
            {!ws.match_count && !completed && (
              <section className="settings-panel competition-empty">
                <Flag />
                <h3>先安排四队对局，再收齐队长名单</h3>
                <p>预览会校验队伍数量、各队场数及位置人次，保存后仍是待指定人员的计划草稿。</p>
                <Button onClick={() => open({ mode: 'schedule' })}>预览团队赛程</Button>
              </section>
            )}
            {ws.match_count > 0 && !completed && t.status === 'draft' && (
              <Button variant="outline" onClick={() => open({ mode: 'reset' })}>
                撤回赛程后调整队伍或规则
              </Button>
            )}
            {!!ws.stages?.length && (
              <section className="settings-panel">
                <div className="competition-section-heading">
                  <h3>位置循环进度</h3>
                  <label>
                    查看位置
                    <Select
                      aria-label="查看团队位置阶段"
                      value={stageFilter}
                      onValueChange={(value) => {
                        setStageFilter(value)
                        setPlanPage(1)
                      }}
                      options={[
                        { value: '', label: '全部位置阶段' },
                        ...ws.stages.map((stage) => ({
                          value: stage.id,
                          label: `第 ${stage.cycle} 循环 · ${stage.position_label}（${stage.confirmed_matches}/${stage.match_count} 场）`,
                        })),
                      ]}
                    />
                  </label>
                </div>
                {selectedStage && (
                  <>
                    <p>
                      第 {selectedStage.cycle} 循环 · {selectedStage.position_label}，已确认{' '}
                      {selectedStage.confirmed_matches}/{selectedStage.match_count} 桌场。
                    </p>
                    <div className="team-plan-lineup">
                      {selectedStage.representatives.map((rep) => {
                        const team = t.teams.find((row) => row.id === rep.team_id)
                        const member = team?.members.find((row) => row.id === rep.member_id)
                        return (
                          <div key={rep.team_id}>
                            <strong>{team?.name}</strong>
                            <span>
                              已确认 {rep.confirmed_matches ?? '—'} /{' '}
                              {rep.planned_matches ?? selectedStage.games_per_team} 场 ·{' '}
                              {member?.display_name ?? '等待队长指定'}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                    <div className="team-button-row">
                      <Button
                        disabled={completed || loading}
                        onClick={() => open({ mode: 'representatives', stage: selectedStage })}
                      >
                        编辑本位置代表名单
                      </Button>
                      <Button
                        variant="outline"
                        disabled={completed || busy || loading}
                        onClick={() => {
                          open({ mode: 'confirm-stage', stage: selectedStage })
                          void loadStagePlans(selectedStage)
                        }}
                      >
                        预览确认本位置计划
                      </Button>
                    </div>
                  </>
                )}
              </section>
            )}
            {!!ws.match_count && (
              <section className="settings-panel">
                <div className="competition-section-heading">
                  <h3>赛程与出场名单</h3>
                  <label>
                    计划状态
                    <Select
                      aria-label="团队计划状态"
                      value={planStatus}
                      onValueChange={(value) => {
                        setPlanStatus(value)
                        setPlanPage(1)
                      }}
                      options={[
                        { value: '', label: '全部计划' },
                        { value: 'draft', label: '计划草稿' },
                        { value: 'confirmed', label: '已确认未开场' },
                        { value: 'started', label: '已开场待成绩' },
                        { value: 'completed', label: '成绩已确认' },
                      ]}
                    />
                  </label>
                </div>
                <div className="team-plan-grid">
                  {plans.map((p) => (
                    <article className="team-plan-card" key={p.id}>
                      <header>
                        <h4>第 {p.match_number} 场</h4>
                        <Badge variant="outline">
                          {
                            {
                              draft: '计划草稿',
                              confirmed: '已确认未开场',
                              started: '已开场',
                              completed: '成绩已确认',
                              voided: '已撤回',
                            }[p.status]
                          }
                        </Badge>
                      </header>
                      <p>
                        {sourceLabel(p)}
                        {p.batch_number ? ` · 时段 ${p.batch_number}` : ''}
                      </p>
                      <div className="team-plan-lineup">
                        {p.lineup_rows.map((row) => (
                          <div key={row.team_id}>
                            <strong>{row.team_name}</strong>
                            <span>{row.display_name ?? '等待队长指定'}</span>
                          </div>
                        ))}
                      </div>
                      {!completed && p.status === 'draft' && (
                        <div className="team-button-row">
                          {p.stage_id && t.pairing_strategy === 'team_manual_v1' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={loading}
                              onClick={() => open({ mode: 'plan', plan: p })}
                            >
                              编辑第 {p.match_number} 场四队
                            </Button>
                          )}
                          {p.stage_id ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                const stage = ws.stages?.find((s) => s.id === p.stage_id)
                                if (stage) open({ mode: 'representatives', stage })
                              }}
                            >
                              指定位置代表
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => open({ mode: 'plan', plan: p })}
                            >
                              编辑第 {p.match_number} 场名单
                            </Button>
                          )}
                          <Button
                            size="sm"
                            disabled={
                              !p.captain_supplied || p.lineup_rows.some((r) => !r.member_id)
                            }
                            onClick={() => open({ mode: 'confirm-plan', plan: p })}
                          >
                            确认本场出场
                          </Button>
                        </div>
                      )}
                      {!completed && p.status === 'confirmed' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => open({ mode: 'withdraw', plan: p })}
                        >
                          撤回本场确认
                        </Button>
                      )}
                    </article>
                  ))}
                </div>
                <div className="pagination">
                  <span>
                    {planCount} 场计划 · 第 {planPage} 页
                  </span>
                  <Button
                    variant="outline"
                    disabled={planPage === 1}
                    onClick={() => setPlanPage((p) => p - 1)}
                  >
                    上一页计划
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!planNext}
                    onClick={() => setPlanPage((p) => p + 1)}
                  >
                    下一页计划
                  </Button>
                </div>
              </section>
            )}
            {!!ws.mapping.length && (
              <section className="fixed-strip" aria-label="团队赛固定物理桌">
                {ws.mapping.map((fixed) => (
                  <div key={fixed.id}>
                    <strong>逻辑桌 {fixed.label}</strong>
                    <span>
                      {fixed.machine_no ? `${fixed.machine_no} · ${fixed.name}` : '本赛关联已结束'}
                    </span>
                    {!completed && fixed.machine_id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => open({ mode: 'replace', ordinal: fixed.ordinal })}
                      >
                        故障换桌 {fixed.label}
                      </Button>
                    )}
                    <details>
                      <summary>关联历史</summary>
                      {fixed.history.map((h) => (
                        <p key={h.id}>
                          {h.machine_no_snapshot} · {h.status === 'active' ? '关联有效' : '已结束'}{' '}
                          · {h.reason || '初始选桌'}
                          {h.release_reason ? ` · ${h.release_reason}` : ''}
                        </p>
                      ))}
                    </details>
                  </div>
                ))}
              </section>
            )}
            {t.status === 'started' && (
              <div className="next-round">
                <p>按已确认计划选择下一时段；同一人重叠时分到后续时段，位置按顺序完成。</p>
                <Button disabled={loading} onClick={() => open({ mode: 'batch' })}>
                  预览下一开赛时段
                </Button>
              </div>
            )}
            {!!batches.length && (
              <section className="competition-rounds">
                <h3>已开场对局与成绩</h3>
                {batches.map((batch) => (
                  <div key={batch.id}>
                    <h4 className="team-batch-heading">时段 {batch.round_number}</h4>
                    <div className="competition-tables">
                      {batch.tables.map((table) => (
                        <article className="competition-table" key={table.id}>
                          <header>
                            <h3>逻辑桌 {'ABCD'[table.table_number - 1]}</h3>
                            <Badge variant="outline">
                              {table.result?.status === 'confirmed' ? '成绩已确认' : '待录入/确认'}
                            </Badge>
                          </header>
                          <p className="table-machine">
                            本场开赛时物理桌 {table.machine_snapshot?.machine_no}
                          </p>
                          <div className="score-seats">
                            {table.seats.map((seat) => {
                              const team = t.teams.find((row) =>
                                row.members.some((m) => m.participant_id === seat.participant_id),
                              )
                              const score = table.result?.scores.find(
                                (s) => s.participant_id === seat.participant_id,
                              )
                              return (
                                <div key={seat.id}>
                                  <span className="wind-mark">{windLabels[seat.seat_wind]}</span>
                                  <strong>
                                    {team?.name} · {seat.display_name}
                                  </strong>
                                  <span>{table.result?.points[seat.participant_id] ?? '—'} 点</span>
                                  {score && (
                                    <span title={exactScore(score.score)}>
                                      {displayScore(score.score)} 分
                                    </span>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                          <footer>
                            {!completed && (
                              <Button
                                onClick={() =>
                                  open({
                                    mode:
                                      table.result?.status === 'confirmed' ? 'correct' : 'result',
                                    table,
                                  })
                                }
                              >
                                {table.result?.status === 'confirmed' ? '更正' : '录入'}时段{' '}
                                {batch.round_number} 第{table.table_number}桌成绩
                              </Button>
                            )}
                            {table.result?.status === 'confirmed' && (
                              <Button
                                variant="ghost"
                                onClick={() => open({ mode: 'history', table })}
                              >
                                查看成绩更正历史
                              </Button>
                            )}
                          </footer>
                        </article>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="pagination">
                  <Button
                    variant="outline"
                    disabled={batchPage === 1}
                    onClick={() => setBatchPage((p) => p - 1)}
                  >
                    较新开赛时段
                  </Button>
                  <span>第 {batchPage} 页时段</span>
                  <Button
                    variant="outline"
                    disabled={!batchNext}
                    onClick={() => setBatchPage((p) => p + 1)}
                  >
                    较早开赛时段
                  </Button>
                </div>
              </section>
            )}
            <TeamStandings rows={ws.team_standings} completed={completed} />
            <details className="settings-panel">
              <summary>查看队员个人表现（辅助榜）</summary>
              <p>未出场成员不排名，个人并列不阻断团队完赛。</p>
              <Standings rows={ws.standings} completed={completed} statistics={ws.statistics} />
            </details>
            {t.status === 'started' && (
              <section className="settings-panel final-actions">
                <h3>团队排名与完赛</h3>
                <p>
                  {ws.all_results_confirmed
                    ? ws.unresolved_groups?.length
                      ? '团队比较指标完全相同，请公开抽签后确认。'
                      : '全部计划成绩已确认，可以核对团队冠军并完赛。'
                    : '须全部计划实际开场且成绩确认后，才能正式完赛。'}
                </p>
                {(ws.unresolved_groups ?? []).map((members, i) => (
                  <div className="lottery-group" key={members.join('-')}>
                    <span>
                      {members
                        .map((id) => ws.teams.find((team) => team.id === id)?.name)
                        .join('、')}
                    </span>
                    <Button variant="outline" onClick={() => open({ mode: 'lottery', members })}>
                      记录团队公开抽签 {i + 1}
                    </Button>
                  </div>
                ))}
                <Button disabled={!ws.ready} onClick={() => open({ mode: 'complete' })}>
                  <Trophy size={16} />
                  正式完赛团队赛
                </Button>
              </section>
            )}
            <Button
              variant="outline"
              onClick={() => {
                open({ mode: 'audit' })
                void loadAudit(1)
              }}
            >
              查看团队操作历史
            </Button>
          </>
        )
      )}
      {editing && t && (
        <TeamTournamentEditor
          tournament={t}
          close={close}
          saved={() => {
            close()
            setSuccess('团队草稿已保存。')
            refresh()
          }}
        />
      )}
      {action && t && ws && (
        <TeamSheet title={title} description={t.name} busy={busy} close={close}>
          {action.mode === 'schedule' && (
            <>
              <p>先预览四队编排，管理员随后按队长指定名单安排成员。</p>
              {schedulePreview && (
                <div className="confirmation-preview">
                  <h3>赛程摘要</h3>
                  <p>
                    共 {schedulePreview.match_count} 桌场，各队 {schedulePreview.games_per_team}{' '}
                    场。
                  </p>
                  {schedulePreview.preview_matches.map((p) => (
                    <p key={p.match_number}>
                      第 {p.match_number} 场
                      {p.position_label ? ` · 第${p.cycle}循环 ${p.position_label}` : ''}：
                      {p.team_ids
                        .map((id) => t.teams.find((row) => row.id === id)?.name)
                        .join('、')}
                    </p>
                  ))}
                  {schedulePreview.match_count > schedulePreview.preview_limit && (
                    <p>此处展示前 {schedulePreview.preview_limit} 场；生成后可分页查看完整赛程。</p>
                  )}
                </div>
              )}
              <Button
                disabled={busy}
                onClick={() => {
                  const epoch = actionEpoch.current
                  void run(
                    async () => {
                      const data = await previewTeamSchedule(t.id)
                      if (epoch === actionEpoch.current) setSchedulePreview(data)
                    },
                    '',
                    true,
                  )
                }}
              >
                计算团队赛程预览
              </Button>
              {schedulePreview && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(
                      () => generateTeamSchedule(t.id, schedulePreview.token),
                      '赛程计划已保存，请收齐队长出场名单。',
                    )
                  }
                >
                  确认生成团队赛程
                </Button>
              )}
            </>
          )}
          {action.mode === 'start' && (
            <>
              <Users size={28} />
              <h3>确认启动并冻结阵容</h3>
              <p>
                {t.teams.length} 支队伍、{t.participant_count} 名登记成员、{ws.match_count}{' '}
                桌场计划。规则及成员名单启动后冻结，未来未开场出场人仍可按本队名单指定。
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  void run(() => startTeam(t.id), '团队赛已启动，队伍与成员阵容已冻结。')
                }
              >
                确认启动团队赛
              </Button>
            </>
          )}
          {action.mode === 'plan' && (
            <TeamPlanEditor plan={action.plan} t={t} busy={busy} error={operationError} run={run} />
          )}
          {action.mode === 'representatives' && (
            <TeamRepresentativesEditor
              t={t}
              ws={ws}
              stage={action.stage}
              busy={busy}
              error={operationError}
              run={run}
            />
          )}
          {action.mode === 'confirm-plan' && (
            <>
              <div className="confirmation-preview">
                <h3>第 {action.plan.match_number} 场出场确认</h3>
                <p>{sourceLabel(action.plan)}</p>
                {action.plan.lineup_rows.map((row) => (
                  <p key={row.team_id}>
                    {row.team_name}：{row.display_name ?? '待指定'}
                  </p>
                ))}
              </div>
              {confirmationStale && (
                <>
                  <p role="status">本场确认来源已过期，请载入最新名单并重新核对。</p>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      const epoch = actionEpoch.current
                      void run(
                        async () => {
                          const plan = await fetchTeamPlan(t.id, action.plan.id)
                          if (epoch === actionEpoch.current) {
                            setAction({ mode: 'confirm-plan', plan })
                            setConfirmationStale(false)
                          }
                        },
                        '',
                        true,
                      )
                    }}
                  >
                    载入最新本场确认名单
                  </Button>
                </>
              )}
              <Button
                disabled={
                  busy ||
                  confirmationStale ||
                  action.plan.status !== 'draft' ||
                  !action.plan.captain_supplied ||
                  action.plan.lineup_rows.some((row) => !row.member_id)
                }
                onClick={() =>
                  void run(
                    () =>
                      confirmTeamPlans(t.id, [
                        { match_id: action.plan.id, version: action.plan.version },
                      ]),
                    '本场出场计划已确认。',
                  )
                }
              >
                二次确认本场名单
              </Button>
            </>
          )}
          {action.mode === 'confirm-stage' && (
            <>
              <h3>
                第 {action.stage.cycle} 循环 · {action.stage.position_label}
              </h3>
              {busy && !stagePlans.length && <p role="status">正在读取本位置计划…</p>}
              <p>本次将确认 {stageSources.length} 场待确认计划。</p>
              {stagePlans.slice(0, 40).map((p) => (
                <p key={p.id}>
                  第 {p.match_number} 场：
                  {p.lineup_rows
                    .map((r) => `${r.team_name} ${r.display_name ?? '待指定'}`)
                    .join('、')}
                </p>
              ))}
              {confirmationStale && (
                <>
                  <p role="status">本位置确认来源已过期，请载入最新计划并重新核对。</p>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void loadStagePlans(action.stage)}
                  >
                    载入最新本位置确认名单
                  </Button>
                </>
              )}
              <Button
                disabled={
                  busy ||
                  confirmationStale ||
                  !stageSources.length ||
                  stagePlans.some(
                    (p) => !p.captain_supplied || p.lineup_rows.some((r) => !r.member_id),
                  )
                }
                onClick={() =>
                  void run(() => confirmTeamPlans(t.id, stageSources), '本位置出场计划已确认。')
                }
              >
                二次确认本位置全部名单
              </Button>
            </>
          )}
          {(action.mode === 'reset' || action.mode === 'withdraw') && (
            <>
              <p>
                {action.mode === 'reset'
                  ? '撤回全部未开场赛程，旧计划及人员安排保留历史；开场后无法撤回整份赛程。'
                  : `撤回第 ${action.plan.match_number} 场确认，回到名单草稿，原确认记录留档。`}
              </p>
              <label>
                撤回原因
                <textarea
                  value={reason}
                  maxLength={500}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <Button
                variant="destructive"
                disabled={busy || !reason.trim()}
                onClick={() =>
                  void run(
                    () =>
                      action.mode === 'reset'
                        ? resetTeamSchedule(t.id, t.revision, reason.trim())
                        : withdrawTeamPlan(
                            t.id,
                            action.plan.id,
                            action.plan.version,
                            reason.trim(),
                          ),
                    '计划已撤回，原版本已保留。',
                  )
                }
              >
                确认撤回计划
              </Button>
            </>
          )}
          {action.mode === 'batch' && (
            <>
              {!ws.mapping.length && (
                <>
                  <label>
                    本赛物理桌数量
                    <Select
                      aria-label="团队赛物理桌数量"
                      value={tableCount}
                      disabled={busy}
                      onValueChange={(value) => {
                        setTableCount(value)
                        setSelectedMachines([])
                        setBatchPreview(null)
                      }}
                      options={[1, 2, 3, 4].map((n) => ({ value: n, label: `${n} 张桌` }))}
                    />
                  </label>
                  <div className="table-pickers">
                    {Array.from({ length: Number(tableCount) }, (_, i) => (
                      <label key={i}>
                        逻辑桌 {'ABCD'[i]}
                        <Select
                          aria-label={`团队逻辑桌 ${'ABCD'[i]} 物理桌`}
                          value={selectedMachines[i] || ''}
                          disabled={busy}
                          onValueChange={(value) => {
                            setBatchPreview(null)
                            setSelectedMachines((rows) =>
                              Array.from({ length: Number(tableCount) }, (_, j) =>
                                i === j ? Number(value) : rows[j] || 0,
                              ),
                            )
                          }}
                          options={[
                            { value: '', label: '选择真实可用桌' },
                            ...resources
                              .filter((r) => r.status === 'available')
                              .map((r) => ({
                                value: r.machine_id,
                                label: `${r.machine_no} · ${r.name}`,
                                disabled:
                                  selectedMachines.includes(r.machine_id) &&
                                  selectedMachines[i] !== r.machine_id,
                              })),
                          ]}
                        />
                      </label>
                    ))}
                  </div>
                  <p>跨赛事可以共享设备，本赛逻辑桌使用不同设备；成员重叠的比赛分到后续时段。</p>
                </>
              )}
              <Button
                disabled={
                  busy ||
                  (!ws.mapping.length &&
                    (selectedMachines.length !== Number(tableCount) ||
                      selectedMachines.some((id) => !id)))
                }
                onClick={() => {
                  const epoch = actionEpoch.current
                  void run(
                    async () => {
                      const data = await previewTeamBatch(
                        t.id,
                        ws.mapping.length ? undefined : selectedMachines,
                      )
                      if (epoch === actionEpoch.current) setBatchPreview(data)
                    },
                    '',
                    true,
                  )
                }}
              >
                计算下一时段预览
              </Button>
              {batchPreview && (
                <>
                  <div className="confirmation-preview">
                    <h3>时段 {batchPreview.batch_number} 开场确认</h3>
                    {batchPreview.tables.map((table) => (
                      <article key={table.ordinal}>
                        <strong>
                          逻辑桌 {'ABCD'[table.ordinal - 1]} → {table.mapping.machine_no} · 第{' '}
                          {table.match.match_number} 场
                        </strong>
                        <p>{sourceLabel(table.match)}</p>
                        {table.match.lineup_rows.map((r) => (
                          <p key={r.team_id}>
                            {r.team_name}：{r.display_name}
                          </p>
                        ))}
                      </article>
                    ))}
                  </div>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () => startTeamBatch(t.id, batchPreview.token),
                        '团队赛开赛时段已生成，四风已保存。',
                      )
                    }
                  >
                    确认开场此时段
                  </Button>
                </>
              )}
            </>
          )}
          {(action.mode === 'result' || action.mode === 'correct') && (
            <TableResultEditor
              table={action.table}
              tournament={t}
              correction={action.mode === 'correct'}
              busy={busy}
              error={operationError}
              run={run}
            />
          )}
          {action.mode === 'history' && <ResultCorrectionHistory table={action.table} />}
          {action.mode === 'lottery' && (
            <TeamLotteryEditor
              t={t}
              ws={ws}
              members={action.members}
              busy={busy}
              error={operationError}
              run={run}
              refresh={refresh}
            />
          )}
          {action.mode === 'complete' && (
            <>
              <Trophy size={30} />
              <h3>团队冠军：{ws.team_standings[0]?.name}</h3>
              <p>
                全部 {ws.match_count}{' '}
                桌场成绩已确认，团队冠军、队员贡献、规则和来源将归档，本赛物理桌关联结束。
              </p>
              <Button
                disabled={busy || !ws.ready}
                onClick={() =>
                  void run(() => completeTeam(t.id, ws), '团队赛已正式完赛，成绩及团队冠军已归档。')
                }
              >
                确认团队赛完赛并归档
              </Button>
            </>
          )}
          {action.mode === 'replace' && (
            <>
              <label>
                目标可用物理桌
                <Select
                  aria-label="团队故障替换物理桌"
                  value={target}
                  disabled={busy}
                  onValueChange={setTarget}
                  options={[
                    { value: '', label: '选择替换设备' },
                    ...resources
                      .filter(
                        (r) =>
                          r.status === 'available' &&
                          !ws.mapping.some((m) => m.machine_id === r.machine_id),
                      )
                      .map((r) => ({ value: r.machine_id, label: `${r.machine_no} · ${r.name}` })),
                  ]}
                />
              </label>
              <label>
                故障及替换原因
                <textarea
                  value={reason}
                  maxLength={500}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <p>历史开场设备快照保留，后续时段使用新设备。</p>
              <Button
                disabled={busy || !target || !reason.trim()}
                onClick={() =>
                  void run(
                    () => replaceTable(t.id, action.ordinal, Number(target), reason.trim()),
                    '本赛物理桌已替换，历史已保留。',
                  )
                }
              >
                确认团队故障换桌
              </Button>
            </>
          )}
          {action.mode === 'audit' && (
            <>
              <div className="team-audit-list">
                {audits.map((row) => (
                  <article key={row.id}>
                    <strong>
                      记录 #{row.id} · {row.action}
                    </strong>
                    <p>
                      管理员 #{row.created_by} · {new Date(row.created_at).toLocaleString('zh-CN')}
                    </p>
                    {row.reason && <p>{row.reason}</p>}
                    <details>
                      <summary>查看操作前后记录</summary>
                      <pre>{JSON.stringify({ before: row.before, after: row.after }, null, 2)}</pre>
                    </details>
                  </article>
                ))}
              </div>
              <div className="pagination">
                <Button
                  variant="outline"
                  disabled={busy || auditPage === 1}
                  onClick={() => void loadAudit(auditPage - 1)}
                >
                  上一页历史
                </Button>
                <span>第 {auditPage} 页</span>
                <Button
                  variant="outline"
                  disabled={busy || !auditNext}
                  onClick={() => void loadAudit(auditPage + 1)}
                >
                  下一页历史
                </Button>
              </div>
            </>
          )}
          <FormFeedback error={operationError} />
          {operationError instanceof ApiError && operationError.status === 409 && (
            <p>正在刷新工作台；当前面板的名单和确认来源需要重新载入并核对。</p>
          )}
        </TeamSheet>
      )}
    </div>
  )
}
