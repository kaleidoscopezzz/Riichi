import { useEffect, useState, type FormEvent } from 'react'
import { Check, LockKeyhole, Search, X } from 'lucide-react'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import {
  findPlayers,
  legalSize,
  previewOka,
  saveTournament,
  startTournament,
  type Page,
  type Participant,
  type Tournament,
} from '@/services/tournaments'
import type { Player } from '@/services/api'
import { TournamentRoundSummary } from './tournament-round-summary'

export function PlayerPicker({
  selected,
  change,
  disabled,
}: {
  selected: Participant[]
  change: (value: Participant[]) => void
  disabled: boolean
}) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<Player & { is_active: boolean }> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void findPlayers(page, search, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value)
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [page, search, retry])
  return (
    <section className="participant-picker" aria-label="选择参赛选手">
      <div className="tournament-section-heading">
        <h3>参赛名单</h3>
        <Badge variant="outline">已选 {selected.length} / 16 人</Badge>
      </div>
      <p className="field-hint">草稿可暂留空；启动需要 4、8、12 或 16 人。选手来自已注册账号。</p>
      <div className="selected-players" aria-label="已选人员">
        {selected.length ? (
          selected.map((p) => (
            <button
              type="button"
              key={p.player_id}
              disabled={disabled}
              onClick={() => change(selected.filter((v) => v.player_id !== p.player_id))}
              aria-label={`移除 ${p.display_name}`}
            >
              <span>{p.display_name}</span>
              <X size={13} />
            </button>
          ))
        ) : (
          <span className="field-hint">尚未选择选手</span>
        )}
      </div>
      <div className="machine-toolbar">
        <div className="machine-search">
          <Search size={16} />
          <input
            aria-label="搜索参赛选手"
            placeholder="昵称或用户名"
            value={query}
            maxLength={150}
            disabled={disabled}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                setSearch(query.trim())
                setPage(1)
              }
            }}
          />
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => {
            setSearch(query.trim())
            setPage(1)
          }}
        >
          查找选手
        </Button>
      </div>
      <FormFeedback error={error} />
      {loading ? (
        <p role="status">正在加载已注册选手…</p>
      ) : error ? (
        <Button type="button" variant="outline" onClick={() => setRetry((v) => v + 1)}>
          重试选手查询
        </Button>
      ) : (
        <div className="picker-results">
          {data?.results.length ? (
            data.results.map((p) => {
              const checked = selected.some((v) => v.player_id === p.id)
              return (
                <button
                  type="button"
                  key={p.id}
                  className={checked ? 'selected' : ''}
                  aria-pressed={checked}
                  disabled={disabled || !p.is_active || (!checked && selected.length >= 16)}
                  onClick={() =>
                    change(
                      checked
                        ? selected.filter((v) => v.player_id !== p.id)
                        : [
                            ...selected,
                            {
                              id: 0,
                              player_id: p.id,
                              display_name: p.nickname,
                              username: p.username,
                              is_active: p.is_active,
                              display_name_snapshot: '',
                            },
                          ],
                    )
                  }
                >
                  <span>
                    <strong>{p.nickname}</strong>
                    <small>
                      @{p.username}
                      {!p.is_active && ' · 账号已停用'}
                    </small>
                  </span>
                  {checked ? <Check size={17} /> : <span className="picker-add">+</span>}
                </button>
              )
            })
          ) : (
            <p className="field-hint">没有匹配的已注册选手。</p>
          )}
        </div>
      )}
      {data && !loading && !error && (
        <div className="pagination">
          <span>
            共 {data.count} 人 · 第 {page} 页
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled || !data.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页选手
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled || !data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页选手
          </Button>
        </div>
      )}
    </section>
  )
}

export function TournamentEditor({
  tournament,
  close,
  saved,
}: {
  tournament?: Tournament
  close: () => void
  saved: (row: Tournament) => void
}) {
  const [name, setName] = useState(tournament?.name || '')
  const [description, setDescription] = useState(tournament?.description || '')
  const [rounds, setRounds] = useState(String(tournament?.round_count || 3))
  const [starting, setStarting] = useState(String(tournament?.starting_points || 25000))
  const [returning, setReturning] = useState(String(tournament?.return_points || 30000))
  const [uma, setUma] = useState(tournament?.uma || ['30', '10', '-10', '-30'])
  const [selected, setSelected] = useState(tournament?.participants || [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (
      !name.trim() ||
      !/^[1-6]$/.test(rounds) ||
      [starting, returning].some(
        (v) => !/^[0-9]+$/.test(v) || Number(v) < 1 || Number(v) > 2147483647,
      ) ||
      uma.some((v) => v.length > 64 || !/^[+-]?[0-9]+(?:\.[0-9]+)?$/.test(v))
    ) {
      setError(new Error('请填写赛事名称、1～6轮、正整数点数和四项有效十进制 Uma。'))
      return
    }
    setBusy(true)
    try {
      saved(
        await saveTournament(
          {
            name: name.trim(),
            description: description.trim(),
            round_count: Number(rounds),
            starting_points: Number(starting),
            return_points: Number(returning),
            uma,
            participant_ids: selected.map((p) => p.player_id),
          },
          tournament?.id,
        ),
      )
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <SheetContent className="machine-sheet tournament-sheet" showCloseButton={false}>
        <SheetHeader>
          <span className="eyebrow">TOURNAMENT STUDIO</span>
          <SheetTitle>{tournament ? '编辑赛事草稿' : '创建个人赛事'}</SheetTitle>
          <SheetDescription>
            独立规则，真实选手。保存草稿后可继续完善，启动时冻结。
          </SheetDescription>
        </SheetHeader>
        <Button
          variant="ghost"
          size="icon"
          className="machine-sheet-close"
          aria-label="关闭赛事表单"
          disabled={busy}
          onClick={close}
        >
          <X />
        </Button>
        <form className="account-form tournament-form" onSubmit={(e) => void submit(e)} noValidate>
          <fieldset disabled={busy}>
            <section>
              <span className="eyebrow">01 / 基础信息</span>
              <label>
                赛事名称
                <input
                  autoFocus
                  value={name}
                  maxLength={120}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="为这场赛事命名"
                />
              </label>
              <label>
                赛事说明
                <textarea
                  value={description}
                  maxLength={3000}
                  rows={2}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <label>
                总轮数
                <select value={rounds} onChange={(e) => setRounds(e.target.value)}>
                  {[1, 2, 3, 4, 5, 6].map((v) => (
                    <option value={v} key={v}>
                      {v} 轮
                    </option>
                  ))}
                </select>
              </label>
            </section>
            <section>
              <span className="eyebrow">02 / 计分配置</span>
              <div className="rule-fields">
                <label>
                  开局点数
                  <input
                    inputMode="numeric"
                    value={starting}
                    onChange={(e) => setStarting(e.target.value)}
                  />
                </label>
                <label>
                  返还原点
                  <input
                    inputMode="numeric"
                    value={returning}
                    onChange={(e) => setReturning(e.target.value)}
                  />
                </label>
              </div>
              <div className="uma-fields">
                {uma.map((v, i) => (
                  <label key={i}>
                    第 {i + 1} 名 Uma
                    <input
                      value={v}
                      inputMode="decimal"
                      maxLength={64}
                      onChange={(e) =>
                        setUma(uma.map((old, index) => (index === i ? e.target.value : old)))
                      }
                    />
                  </label>
                ))}
              </div>
              <div className="oka-preview">
                <span>推导 Oka</span>
                <strong>{previewOka(starting, returning)}</strong>
                <small>4 ×（返还原点 − 开局点数）÷ 1000</small>
              </div>
            </section>
            <section>
              <span className="eyebrow">03 / 参赛选手</span>
              <PlayerPicker selected={selected} change={setSelected} disabled={busy} />
            </section>
          </fieldset>
          <section className="tournament-summary">
            <strong>草稿摘要</strong>
            <p>
              {name || '未命名赛事'} · {rounds} 轮 · {selected.length} 人 ·{' '}
              {legalSize(selected.length) ? `预计每轮 ${selected.length / 4} 桌` : '名单待完善'}
            </p>
            <p>保存不会启动赛事，也不会占用麻将机。</p>
          </section>
          <FormFeedback error={error} />
          <div className="machine-form-footer">
            <Button type="button" variant="outline" disabled={busy} onClick={close}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? '正在保存…' : '保存草稿'}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}

export function TournamentRules({ row }: { row: Tournament }) {
  return (
    <dl className="tournament-rules">
      <div>
        <dt>总轮数</dt>
        <dd>{row.round_count} 轮</dd>
      </div>
      <div>
        <dt>开局 / 返还</dt>
        <dd>
          {row.starting_points} / {row.return_points}
        </dd>
      </div>
      <div>
        <dt>Uma · 一至四名</dt>
        <dd>{row.uma.join(' / ')}</dd>
      </div>
      <div>
        <dt>推导 Oka</dt>
        <dd>{row.oka}</dd>
      </div>
      <div>
        <dt>预计每轮桌数</dt>
        <dd>
          {row.expected_table_count === null ? '名单待完善' : `${row.expected_table_count} 桌`}
        </dd>
      </div>
    </dl>
  )
}

export function TournamentDetail({
  row,
  confirm = false,
  close,
  saved,
  edit,
  prepareStart,
}: {
  row: Tournament
  confirm?: boolean
  close: () => void
  saved: (row: Tournament) => void
  edit: () => void
  prepareStart: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const valid = legalSize(row.participant_count) && row.participants.every((p) => p.is_active)
  async function start() {
    setBusy(true)
    setError(null)
    try {
      saved(await startTournament(row.id))
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <SheetContent className="machine-sheet tournament-sheet" showCloseButton={false}>
        <SheetHeader>
          <span className="eyebrow">{confirm ? 'READY TO START' : 'TOURNAMENT DOSSIER'}</span>
          <SheetTitle>{confirm ? '确认启动赛事' : '赛事详情'}</SheetTitle>
          <SheetDescription>
            {row.status !== 'draft'
              ? (row.status === 'completed' ? '已完赛 · 成绩与冠军已归档。' : '已启动 · 规则与参赛名单已冻结。')
              : '草稿 · 启动前可调整配置与参赛名单。'}
          </SheetDescription>
        </SheetHeader>
        <Button
          variant="ghost"
          size="icon"
          className="machine-sheet-close"
          aria-label="关闭赛事详情"
          disabled={busy}
          onClick={close}
        >
          <X />
        </Button>
        <div className="tournament-detail">
          <Badge variant="outline">{row.status === 'draft' ? '草稿' : row.status === 'completed' ? '已完赛' : '已启动'}</Badge>
          <h2>{row.name}</h2>
          <p>{row.description || '未填写赛事说明'}</p>
          <TournamentRules row={row} />
          {row.status !== 'draft' && <TournamentRoundSummary id={row.id} />}
          <section>
            <div className="tournament-section-heading">
              <h3>参赛名单</h3>
              <span>{row.participant_count} 人</span>
            </div>
            <div className="participant-roster">
              {row.participants.map((p) => (
                <div key={p.player_id}>
                  <strong>{p.display_name}</strong>
                  <small>
                    @{p.username}
                    {!p.is_active && ' · 账号已停用'}
                  </small>
                </div>
              ))}
            </div>
            {!row.participant_count && <p>尚未选择参赛选手。</p>}
          </section>
          <div className="machine-dates">
            <p>创建时间：{new Date(row.created_at).toLocaleString('zh-CN')}</p>
            <p>
              启动时间：
              {row.started_at ? new Date(row.started_at).toLocaleString('zh-CN') : '尚未启动'}
            </p>
          </div>
          {row.status === 'draft' && (
            <div className="tournament-start-notice">
              <LockKeyhole size={20} />
              <div>
                <strong>{valid ? '人数检查通过' : '启动条件尚未满足'}</strong>
                <p>
                  需要 4、8、12 或 16 名有效选手。启动后规则和名单无法修改；不会自动分桌或分配设备。
                </p>
              </div>
            </div>
          )}
          <FormFeedback error={error} />
          <div className="machine-form-footer">
            <Button variant="outline" disabled={busy} onClick={close}>
              {confirm ? '暂不启动' : '关闭'}
            </Button>
            {row.status !== 'draft' && (
              <Button asChild>
                <a href={`/tournaments/${row.id}/rounds`}>进入分桌工作台</a>
              </Button>
            )}
            {row.status === 'draft' &&
              (confirm ? (
                <Button disabled={busy || !valid} onClick={() => void start()}>
                  {busy ? '正在启动…' : '确认启动并冻结'}
                </Button>
              ) : (
                <>
                  <Button variant="outline" onClick={edit}>
                    编辑草稿
                  </Button>
                  <Button disabled={!valid} onClick={prepareStart}>
                    启动前检查
                  </Button>
                </>
              ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
