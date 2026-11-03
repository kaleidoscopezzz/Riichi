import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Grid2X2, RefreshCw, Shuffle, History, LockKeyhole } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FormFeedback } from '@/components/form-feedback'
import { RoundActionSheet, type RoundAction } from '@/components/round-action'
import { fetchTournament, type Tournament } from '@/services/tournaments'
import {
  fetchRounds,
  fetchResources,
  fetchTable,
  fetchAllocationHistory,
  windLabels,
  type MachineResource,
  type TournamentRound,
  type RoundTable,
} from '@/services/rounds'
import { machineLabels } from '@/services/machines'

export function RoundsPage() {
  const { id } = useParams()
  const [tournament, setTournament] = useState<Tournament | null>(null)
  const [rounds, setRounds] = useState<TournamentRound[]>([])
  const [resources, setResources] = useState<MachineResource[]>([])
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [success, setSuccess] = useState('')
  const [revision, setRevision] = useState(0)
  const [action, setAction] = useState<RoundAction | null>(null)
  const focusPending = useRef(false)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const workspace = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void Promise.all([
      fetchTournament(Number(id)),
      fetchRounds(Number(id), controller.signal),
      fetchResources(controller.signal),
    ])
      .then(([t, r, m]) => {
        if (!controller.signal.aborted) {
          setTournament(t)
          setRounds(r.results)
          setResources(m.results)
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
  useEffect(() => {
    if (action || loading || !focusPending.current) return
    const frame = requestAnimationFrame(() => {
      ;(trigger.current?.isConnected && !trigger.current.disabled
        ? trigger.current
        : workspace.current
      )?.focus()
      focusPending.current = false
    })
    return () => cancelAnimationFrame(frame)
  }, [action, loading])
  function close() {
    setAction(null)
    focusPending.current = true
  }
  function saved(message: string) {
    close()
    setSuccess(message)
    setRevision((v) => v + 1)
  }
  async function open(
    mode: 'generate' | 'history' | 'reassign' | 'release',
    button: HTMLButtonElement,
    table?: RoundTable,
  ) {
    trigger.current = button
    setOpening(true)
    setError(null)
    setSuccess('')
    try {
      if (mode === 'generate') {
        const [fresh, current, pool] = await Promise.all([
          fetchTournament(Number(id)),
          fetchRounds(Number(id)),
          fetchResources(),
        ])
        setTournament(fresh)
        setRounds(current.results)
        setResources(pool.results)
        if (current.results.length) throw new Error('第一轮已生成，请查看持久化分桌。')
        if (fresh.status !== 'started') throw new Error('请先启动赛事，再生成第一轮。')
        setAction({ mode })
      } else if (table) {
        const fresh = await fetchTable(table.id)
        if (mode === 'history') {
          const history = await fetchAllocationHistory(table.id)
          setAction({ mode, table: fresh, history: history.results })
        } else {
          const pool = await fetchResources()
          setResources(pool.results)
          if (!fresh.active_allocation) throw new Error('此桌设备已释放，请刷新查看历史。')
          setAction({ mode, table: fresh })
        }
      }
    } catch (e) {
      setError(e as Error)
    } finally {
      setOpening(false)
    }
  }
  const free = resources.filter((m) => m.assignable).length
  const active = rounds.flatMap((r) => r.tables).filter((t) => t.active_allocation).length
  return (
    <div className="round-workspace" ref={workspace} tabIndex={-1}>
      <Link className="round-back" to="/tournaments">
        <ArrowLeft size={15} />
        返回赛事档案
      </Link>
      <section className="round-hero">
        <div>
          <span className="eyebrow">ROUND & RESOURCE CONTROL</span>
          <h2>{tournament?.name || '赛事分桌工作台'}</h2>
          <p>逻辑桌承载选手与座次，物理设备记录实际占用。</p>
        </div>
        <Button
          variant="outline"
          disabled={loading || opening}
          onClick={() => setRevision((v) => v + 1)}
        >
          <RefreshCw size={16} />
          刷新工作台
        </Button>
      </section>
      <FormFeedback error={error} success={success} />
      {loading ? (
        <div className="settings-panel machine-loading" role="status">
          正在读取轮次与真实设备资源…
        </div>
      ) : error ? (
        <div className="settings-panel list-empty">
          <h3>暂时无法更新工作台</h3>
          <p>请刷新最新状态后重试，写操作不会自动重放。</p>
          <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
            重新加载工作台
          </Button>
        </div>
      ) : (
        tournament && (
          <>
            <div className="round-metrics">
              {[
                [tournament.participant_count, '冻结参赛人数'],
                [tournament.round_count, '配置总轮数'],
                [tournament.expected_table_count || '—', '预计每轮桌数'],
                [`${active} / ${tournament.expected_table_count || '—'}`, '本赛事设备占用'],
              ].map(([value, label]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <section className="settings-panel round-resource-panel">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">LIVE PHYSICAL RESOURCES</span>
                  <h3>设备资源池</h3>
                </div>
                <Badge variant="outline">可分配 {free} 台</Badge>
              </div>
              <div className="round-resources">
                {resources.map((m) => (
                  <article key={m.machine_id} className={m.active_allocation ? 'occupied' : ''}>
                    <div>
                      <span className="machine-number">{m.machine_no}</span>
                      <Badge variant="outline">{machineLabels[m.status]}</Badge>
                    </div>
                    <strong>{m.name}</strong>
                    <p>
                      {m.active_allocation
                        ? `占用中 · ${m.active_allocation.tournament_name} / 第${m.active_allocation.table_number}桌`
                        : m.assignable
                          ? '当前空闲 · 可分配'
                          : '当前不可分配'}
                    </p>
                    <small>稳定 machineId #{m.machine_id}</small>
                  </article>
                ))}
                {!resources.length && (
                  <p className="field-hint">资源池尚无现役设备，请先在麻将机管理登记真实设备。</p>
                )}
              </div>
            </section>
            <section className="round-board">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">PERSISTED SEATING</span>
                  <h3>轮次与分桌</h3>
                </div>
                <Badge variant="outline">已生成 {rounds.length} 轮</Badge>
              </div>
              {!rounds.length ? (
                <div className="settings-panel round-empty">
                  <Shuffle size={36} />
                  <h3>{tournament.status === 'draft' ? '赛事尚未启动' : '第一轮，等待落位'}</h3>
                  <p>
                    {tournament.status === 'draft'
                      ? '请返回赛事详情完成启动，冻结规则与参赛名单。'
                      : `将为${tournament.participant_count}名选手生成${tournament.expected_table_count}张逻辑桌，并分配同等数量的空闲设备。`}
                  </p>
                  {tournament.status === 'started' && (
                    <>
                      <Button
                        disabled={opening}
                        onClick={(e) => void open('generate', e.currentTarget)}
                      >
                        <Shuffle size={16} />
                        生成第一轮分桌
                      </Button>
                      {free < (tournament.expected_table_count || 0) && (
                        <p className="round-shortage">
                          设备资源不足：需要{tournament.expected_table_count}台，当前可分配{free}
                          台。可以查看生成前检查。
                        </p>
                      )}
                    </>
                  )}
                </div>
              ) : (
                rounds.map((round) => (
                  <section key={round.id} className="round-section">
                    <div className="round-section-heading">
                      <h3>
                        第 {round.round_number} 轮 <span>已生成 · 座次固定</span>
                      </h3>
                      <time>{new Date(round.generated_at).toLocaleString('zh-CN')}</time>
                    </div>
                    <div className="round-tables">
                      {round.tables.map((table) => (
                        <article className="round-table-card" key={table.id}>
                          <header>
                            <div>
                              <Grid2X2 size={19} />
                              <h4>逻辑桌 {table.table_number}</h4>
                            </div>
                            <Badge
                              variant="outline"
                              className={
                                table.active_allocation
                                  ? 'allocation-active'
                                  : 'allocation-released'
                              }
                            >
                              {table.active_allocation ? '设备占用中' : '设备已释放'}
                            </Badge>
                          </header>
                          <div
                            className="wind-seats"
                            aria-label={`第${table.table_number}桌四个座次`}
                          >
                            {table.seats.map((s) => (
                              <div key={s.id} className={`wind-seat wind-${s.seat_wind}`}>
                                <span>{windLabels[s.seat_wind]}</span>
                                <strong>{s.display_name}</strong>
                              </div>
                            ))}
                          </div>
                          <div className="round-machine-line">
                            <span>物理麻将机</span>
                            <strong>
                              {table.active_allocation
                                ? `#${table.active_allocation.machine_no}`
                                : '已释放占用'}
                            </strong>
                            <small>
                              {table.active_allocation
                                ? `machineId ${table.active_allocation.machine_id}`
                                : '原始座次与分配历史已保留'}
                            </small>
                          </div>
                          <footer>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`查看第${table.table_number}桌设备历史`}
                              disabled={opening}
                              onClick={(e) => void open('history', e.currentTarget, table)}
                            >
                              <History size={14} />
                              历史
                            </Button>
                            {table.active_allocation && (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  aria-label={`调整第${table.table_number}桌设备`}
                                  disabled={opening}
                                  onClick={(e) => void open('reassign', e.currentTarget, table)}
                                >
                                  调整设备
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`释放第${table.table_number}桌设备`}
                                  disabled={opening}
                                  onClick={(e) => void open('release', e.currentTarget, table)}
                                >
                                  释放设备
                                </Button>
                              </>
                            )}
                          </footer>
                        </article>
                      ))}
                    </div>
                  </section>
                ))
              )}
            </section>
            <div className="round-boundary">
              <LockKeyhole size={20} />
              <p>
                设备释放不等于成绩确认，也不等于轮次正式结束。本阶段仅生成第一轮，后续轮次依赖未来已确认的累计积分。
              </p>
            </div>
          </>
        )
      )}
      {action && tournament && (
        <RoundActionSheet
          action={action}
          tournament={tournament}
          resources={resources}
          close={close}
          saved={saved}
        />
      )}
    </div>
  )
}
