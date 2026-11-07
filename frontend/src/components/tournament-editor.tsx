import { useState, type FormEvent } from 'react'
import { LockKeyhole, X } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { Badge } from './ui/badge'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import { ApiError } from '@/services/api'
import {
  fetchTournament,
  describeOka,
  legalSize,
  previewOka,
  saveTournament,
  startTournament,
  validCustomOka,
  type Tournament,
} from '@/services/tournaments'
import { PlayerPicker } from './player-picker'
import { TournamentRoundSummary } from './tournament-round-summary'

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
  const [okaMode, setOkaMode] = useState(tournament?.oka_override != null ? 'custom' : 'derived')
  const [customOka, setCustomOka] = useState(tournament?.oka_override ?? '0')
  const [selected, setSelected] = useState(tournament?.participants || [])
  // The server copy this form edits; replaced when the latest draft is reloaded.
  const [base, setBase] = useState(tournament)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [stale, setStale] = useState(false)
  const [reloading, setReloading] = useState(false)
  const [notice, setNotice] = useState('')
  const locked = !!base && base.status !== 'draft'
  const okaPreview =
    okaMode === 'derived'
      ? previewOka(starting, returning)
      : validCustomOka(customOka)
        ? customOka
        : '—'
  function load(row: Tournament) {
    setBase(row)
    setName(row.name)
    setDescription(row.description)
    setRounds(String(row.round_count))
    setStarting(String(row.starting_points))
    setReturning(String(row.return_points))
    setUma(row.uma)
    setOkaMode(row.oka_override != null ? 'custom' : 'derived')
    setCustomOka(row.oka_override ?? '0')
    setSelected(row.participants)
  }
  async function reload() {
    if (!base) return
    setReloading(true)
    setError(null)
    setNotice('')
    try {
      const latest = await fetchTournament(base.id)
      load(latest)
      setStale(false)
      if (latest.status === 'draft') setNotice('已载入最新草稿，请重新核对并修改后再保存。')
      else setError(new Error('该赛事已不是草稿，无法继续编辑。请关闭表单后查看赛事详情。'))
    } catch (e) {
      setError(e as Error)
    } finally {
      setReloading(false)
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNotice('')
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
    if (okaMode === 'custom' && !validCustomOka(customOka)) {
      setError(
        new Error('头名赏 Oka 请填写最多64字符的非负十进制数，0 表示无头名赏，不使用科学计数法。'),
      )
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
            oka_override: okaMode === 'derived' ? null : customOka,
            participant_ids: selected.map((p) => p.player_id),
            // Optimistic lock: a draft changed elsewhere is rejected with 409 stale_tournament.
            ...(base && typeof base.revision === 'number' ? { revision: base.revision } : {}),
          },
          base?.id,
        ),
      )
    } catch (e) {
      setError(e as Error)
      setStale(e instanceof ApiError && e.status === 409 && e.code === 'stale_tournament')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy && !reloading) close()
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
          disabled={busy || reloading}
          onClick={close}
        >
          <X />
        </Button>
        <form className="account-form tournament-form" onSubmit={(e) => void submit(e)} noValidate>
          <fieldset disabled={busy || reloading || locked}>
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
                <Select
                  aria-label="总轮数"
                  value={rounds}
                  disabled={busy || reloading || locked}
                  onValueChange={setRounds}
                  options={[1, 2, 3, 4, 5, 6].map((v) => ({ value: v, label: `${v} 轮` }))}
                />
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
              <label>
                头名赏设置
                <Select
                  aria-label="头名赏设置"
                  aria-describedby="oka-help"
                  value={okaMode}
                  disabled={busy || reloading || locked}
                  onValueChange={setOkaMode}
                  options={[
                    { value: 'derived', label: '自动推导' },
                    { value: 'custom', label: '自定义（可为 0）' },
                  ]}
                />
              </label>
              {okaMode === 'custom' && (
                <label>
                  头名赏 Oka
                  <input
                    inputMode="decimal"
                    maxLength={64}
                    value={customOka}
                    aria-describedby="oka-help"
                    onChange={(e) => setCustomOka(e.target.value)}
                  />
                </label>
              )}
              <p className="rule-hint" id="oka-help">
                {okaMode === 'derived'
                  ? '由开局点数和返还原点计算；也可选择自定义，填 0 表示无头名赏。'
                  : '以积分为单位，填 0 表示无头名赏。自定义值独立于开局和返还原点，四人积分合计可能不为 0。'}
              </p>
              <div className="oka-preview" aria-live="polite">
                <span>本场头名赏</span>
                <strong>{describeOka(okaPreview)}</strong>
                <small>
                  {okaMode === 'derived'
                    ? '4 ×（返还原点 − 开局点数）÷ 1000'
                    : '并列第一时，按覆盖名次均分顺位奖励'}
                </small>
              </div>
            </section>
            <section>
              <span className="eyebrow">03 / 参赛选手</span>
              <PlayerPicker
                selected={selected}
                change={setSelected}
                disabled={busy || reloading || locked}
              />
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
          <FormFeedback error={error} success={notice} />
          {stale && (
            <div className="stale-notice">
              <p>
                此草稿已在其他页面或由其他管理员更新，当前表单基于旧版本，不能直接覆盖。请重新加载最新草稿，核对后再保存；本次未保存的修改需要重新填写。
              </p>
              <Button
                type="button"
                variant="outline"
                disabled={reloading}
                onClick={() => void reload()}
              >
                {reloading ? '正在加载最新草稿…' : '重新加载最新草稿'}
              </Button>
            </div>
          )}
          <div className="machine-form-footer">
            <Button type="button" variant="outline" disabled={busy || reloading} onClick={close}>
              取消
            </Button>
            <Button type="submit" disabled={busy || reloading || locked}>
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
        <dt>头名赏 Oka · {row.oka_override == null ? '自动推导' : '自定义'}</dt>
        <dd>{describeOka(row.oka)}</dd>
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
              ? row.status === 'completed'
                ? '已完赛 · 成绩与冠军已归档。'
                : '已启动 · 规则与参赛名单已冻结。'
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
          <Badge variant="outline">
            {row.status === 'draft' ? '草稿' : row.status === 'completed' ? '已完赛' : '已启动'}
          </Badge>
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
                    选手 #{p.player_id}
                    {!p.is_active && ' · 已归档'}
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
