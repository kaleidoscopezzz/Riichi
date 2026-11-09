import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Trophy, Flag, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { FormFeedback } from '@/components/form-feedback'
import {
  CompetitionAction,
  type CompetitionActionType as Action,
} from '@/components/competition-action'
import { Standings } from '@/components/competition-standings'
import { RoundActionSheet } from '@/components/round-action'
import { fetchTournament, type Tournament } from '@/services/tournaments'
import {
  fetchRounds,
  fetchResources,
  windLabels,
  type RoundTable,
  type TournamentRound,
  type MachineResource,
} from '@/services/rounds'
import {
  fetchWorkspace,
  displayScore,
  exactScore,
  isPendingLottery,
  type Workspace,
} from '@/services/competition'

export function RoundsPage() {
  const { id } = useParams()
  const [t, setT] = useState<Tournament | null>(null)
  const [rounds, setRounds] = useState<TournamentRound[]>([])
  const [resources, setResources] = useState<MachineResource[]>([])
  const [ws, setWs] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [revision, setRevision] = useState(0)
  const [success, setSuccess] = useState('')
  const [action, setAction] = useState<Action | null>(null)
  const [legacyHistory, setLegacyHistory] = useState<RoundTable | null>(null)
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const heading = useRef<HTMLElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  function open(a: Action) {
    returnFocus.current = document.activeElement as HTMLElement
    setAction(a)
  }
  function close() {
    setAction(null)
    requestAnimationFrame(() =>
      (returnFocus.current?.isConnected ? returnFocus.current : heading.current)?.focus(),
    )
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void Promise.all([
      fetchTournament(Number(id)),
      fetchRounds(Number(id), controller.signal),
      fetchResources(controller.signal),
      fetchWorkspace(Number(id), controller.signal),
    ])
      .then(([tournament, r, m, workspace]) => {
        if (!controller.signal.aborted) {
          setT(tournament)
          setRounds(r.results)
          setResources(m.results)
          setWs(workspace)
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [id, revision])
  const latest = rounds.at(-1)
  const visible = rounds.find((r) => r.round_number === selectedRound) || latest
  const confirmed = latest?.tables.every((table) => table.result?.status === 'confirmed')
  const completed = t?.status === 'completed'
  // A completed tournament's final snapshot carries no unresolved groups at all.
  const unresolved = ws?.unresolved_groups ?? []
  // Background re-reads (e.g. right after a lottery write) keep the loaded page
  // mounted, so an open panel and its focus-return target survive the refresh.
  const loaded = !!t && !!ws && t.id === Number(id)
  return (
    <div className="competition-workspace">
      <Link className="back-link" to="/tournaments">
        <ArrowLeft size={16} /> 返回赛事管理
      </Link>
      <section className="competition-hero" ref={heading} tabIndex={-1}>
        <div>
          <span className="eyebrow">TOURNAMENT / 比赛工作台</span>
          <h2>{t?.name || '赛事运行'}</h2>
          <p>记录每一场对局，让每一分都有依据。</p>
        </div>
        <Button variant="outline" disabled={loading} onClick={() => setRevision((v) => v + 1)}>
          <RefreshCw size={16} /> 刷新工作台
        </Button>
      </section>
      <FormFeedback error={error} success={success} />
      {loading && loaded && <p role="status">正在刷新比赛数据…</p>}
      {loading && !loaded ? (
        <p role="status">正在读取比赛、成绩与物理桌…</p>
      ) : error ? (
        <Button onClick={() => setRevision((v) => v + 1)}>重新加载工作台</Button>
      ) : (
        t &&
        ws && (
          <>
            <div className="competition-progress">
              <span>{t.participant_count} 位选手</span>
              <span>
                {rounds.length} / {t.round_count} 轮
              </span>
              <Badge variant="outline">
                {completed
                  ? '已完赛 · 结果只读'
                  : latest
                    ? `第 ${latest.round_number} 轮进行中`
                    : t.status === 'draft'
                      ? '草稿'
                      : '待选桌'}
              </Badge>
            </div>
            {completed && (
              <section className="champion-panel">
                <Trophy size={34} />
                <span className="eyebrow">CHAMPION / 个人冠军</span>
                <h2>
                  {ws.standings.find((x) => x.participant_id === ws.champion_id)?.display_name}
                </h2>
                <p>全部成绩已归档，本赛事物理桌已自动释放。</p>
              </section>
            )}
            {t.status === 'draft' ? (
              <section className="settings-panel">
                <h3>赛事尚未启动</h3>
                <p>请返回赛事详情，确认规则与选手名单后启动。</p>
              </section>
            ) : (
              <>
                {ws.resource_state === 'review_required' && (
                  <section className="settings-panel">
                    <h3>旧赛事需要资源复核</h3>
                    <p>首轮座次和历史保留。部分物理桌已释放或状态异常，不会自动抢回设备。</p>
                    <Button onClick={() => open({ mode: 'review' })}>复核旧赛事</Button>
                  </section>
                )}
                {!!ws.mapping.length && (
                  <section className="fixed-strip" aria-label="本场固定物理桌">
                    {ws.mapping.map((f) => (
                      <div key={f.id}>
                        <strong>逻辑桌 {f.label}</strong>
                        <span>
                          {f.machine_no
                            ? `${f.machine_no} · ${f.name}`
                            : completed
                              ? '已释放'
                              : '无有效预留'}
                        </span>
                        <div>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => open({ mode: 'history', fixed: f })}
                          >
                            占用历史
                          </Button>
                          {!completed && f.machine_id && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => open({ mode: 'replace', fixed: f })}
                            >
                              故障换桌
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </section>
                )}
                {!rounds.length && (
                  <section className="settings-panel competition-empty">
                    <Flag size={28} />
                    <h3>为第一轮做好准备</h3>
                    <p>
                      选择 {t.expected_table_count} 张真实物理桌，预览 A～D
                      映射后确认。后续轮次自动沿用。
                    </p>
                    <Button onClick={() => open({ mode: 'generate' })}>选择物理桌并生成首轮</Button>
                  </section>
                )}
                {latest && (
                  <section className="competition-rounds">
                    <div className="competition-section-heading">
                      <h3>对局与成绩</h3>
                      <label>
                        查看轮次{' '}
                        <Select
                          aria-label="查看轮次"
                          value={visible?.round_number}
                          onValueChange={(value) => setSelectedRound(Number(value))}
                          options={rounds.map((r) => ({
                            value: r.round_number,
                            label: `第 ${r.round_number} 轮`,
                          }))}
                        />
                      </label>
                    </div>
                    <div className="competition-tables">
                      {visible?.tables.map((table) => (
                        <article className="competition-table" key={table.id}>
                          <header>
                            <div>
                              <span className="eyebrow">ROUND {table.round_number}</span>
                              <h3>逻辑桌 {'ABCD'[table.table_number - 1]}</h3>
                            </div>
                            <Badge variant="outline">
                              {table.result?.status === 'confirmed'
                                ? `已确认${table.result.correction_count ? ` · 更正 ${table.result.correction_count} 次` : ''}`
                                : table.result?.version
                                  ? '成绩草稿'
                                  : '待录入'}
                            </Badge>
                          </header>
                          <p className="table-machine">
                            本轮开始时物理桌{' '}
                            {table.machine_snapshot?.machine_no ||
                              table.active_allocation?.machine_no_snapshot ||
                              '见历史'}
                          </p>
                          <div className="score-seats">
                            {table.seats.map((s) => {
                              const score = table.result?.scores.find(
                                (x) => x.participant_id === s.participant_id,
                              )
                              return (
                                <div key={s.id}>
                                  <span className="wind-mark">{windLabels[s.seat_wind]}</span>
                                  <strong>{s.display_name}</strong>
                                  <span>{table.result?.points[s.participant_id] ?? '—'}</span>
                                  {score && (
                                    <span title={exactScore(score.score)}>
                                      {displayScore(score.score)} 分{score.tied ? ' · 并列' : ''}
                                    </span>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                          {!!table.allocation_history.length && (
                            <Button
                              variant="ghost"
                              onClick={() => {
                                returnFocus.current = document.activeElement as HTMLElement
                                setLegacyHistory(table)
                              }}
                            >
                              旧版轮次分配历史
                            </Button>
                          )}
                          <footer>
                            {!completed && table.result?.status === 'confirmed' ? (
                              <Button
                                aria-label={`更正第${table.round_number}轮第${table.table_number}桌成绩`}
                                onClick={() => open({ mode: 'correct', table })}
                              >
                                更正成绩
                              </Button>
                            ) : !completed ? (
                              <Button
                                disabled={ws.resource_state === 'review_required'}
                                onClick={() => open({ mode: 'result', table })}
                              >
                                录入第{table.table_number}桌成绩
                              </Button>
                            ) : (
                              <span>
                                <CheckCircle2 size={15} />{' '}
                                {table.result?.status === 'confirmed'
                                  ? '完赛成绩只读，可查看精确值'
                                  : '历史轮次只读'}
                              </span>
                            )}
                            {table.result?.status === 'confirmed' && (
                              <Button
                                variant="ghost"
                                aria-label={`查看第${table.round_number}轮第${table.table_number}桌成绩更正记录`}
                                onClick={() => open({ mode: 'result-history', table })}
                              >
                                更正记录
                              </Button>
                            )}
                          </footer>
                        </article>
                      ))}
                    </div>
                    {!completed && latest.round_number < t.round_count && (
                      <div className="next-round">
                        <p>
                          {confirmed
                            ? '本轮全部成绩已确认，下一轮将按累计表现重排并重新随机四风。'
                            : '须本轮全部桌次成绩确认后，才能生成下一轮。'}
                        </p>
                        <Button
                          disabled={!confirmed || ws.resource_state !== 'fixed'}
                          onClick={() => open({ mode: 'generate' })}
                        >
                          生成第 {latest.round_number + 1} 轮
                        </Button>
                      </div>
                    )}
                  </section>
                )}
                <Standings rows={ws.standings} completed={completed} />
                {!completed && latest?.round_number === t.round_count && (
                  <section className="settings-panel final-actions">
                    <h3>最终排名与完赛</h3>
                    <p>
                      {!ws.all_results_confirmed
                        ? '请先完成所有桌次成绩确认。'
                        : unresolved.length
                          ? '以下选手所有比较指标完全相同，须分别公开抽签。首轮顺序不用于冠军决胜。'
                          : '最终排名已确定，正式完赛后锁定结果并自动释放本赛事物理桌。'}
                    </p>
                    {unresolved.map((members, i) => (
                      <div className="lottery-group" key={members.join('-')}>
                        <span>
                          并列组 {i + 1}：
                          {members
                            .map(
                              (pk) =>
                                ws.standings.find((x) => x.participant_id === pk)?.display_name,
                            )
                            .join('、')}
                          {ws.lotteries.some((l) =>
                            isPendingLottery(l, members, ws.source_versions),
                          ) && ' · 已有待二次确认的抽签记录'}
                        </span>
                        <Button
                          variant="outline"
                          onClick={() => open({ mode: 'lottery', members })}
                        >
                          记录公开抽签 {i + 1}
                        </Button>
                      </div>
                    ))}
                    <Button disabled={!ws.ready} onClick={() => open({ mode: 'finish' })}>
                      <Trophy size={17} /> 正式完赛
                    </Button>
                  </section>
                )}
              </>
            )}
          </>
        )
      )}
      {legacyHistory && (
        <RoundActionSheet
          table={legacyHistory}
          close={() => {
            setLegacyHistory(null)
            requestAnimationFrame(() => returnFocus.current?.focus())
          }}
        />
      )}
      {action && t && ws && (
        <CompetitionAction
          key={JSON.stringify(action)}
          action={action}
          t={t}
          ws={ws}
          resources={resources}
          next={(latest?.round_number || 0) + 1}
          close={close}
          refresh={() => setRevision((v) => v + 1)}
          saved={(message) => {
            close()
            setSuccess(message)
            if (action.mode !== 'correct') setSelectedRound(null)
            setRevision((v) => v + 1)
          }}
        />
      )}
    </div>
  )
}
