import { useId, useState } from 'react'
import { Trophy, X } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import { ApiError } from '@/services/api'
import type { Tournament } from '@/services/tournaments'
import { generateRound, type MachineResource, type RoundTable } from '@/services/rounds'
import {
  completeTournament,
  recordLottery,
  confirmLottery,
  voidLottery,
  replaceTable,
  reviewLegacy,
  conflictRefreshCodes,
  isPendingLottery,
  mergeLotteries,
  sameMembers,
  sameVersions,
  type Workspace,
  type FixedTable,
  type Lottery,
} from '@/services/competition'
import { TableResultEditor } from './table-result-editor'
import { ResultCorrectionHistory } from './result-correction-history'

export type CompetitionActionType =
  | { mode: 'generate' | 'finish' | 'review' }
  | { mode: 'result' | 'correct' | 'result-history'; table: RoundTable }
  | { mode: 'replace'; fixed: FixedTable }
  | { mode: 'history'; fixed: FixedTable }
  | { mode: 'lottery'; members: number[] }

const voidReasonLimit = 500
const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('zh-CN') : '未记录'

// History entries are read-only: only the earliest current pending record is actionable.
function lotteryState(lottery: Lottery, current: boolean, waiting: boolean) {
  if (lottery.voided_at) return '已作废'
  if (lottery.confirmed_at) return current ? '已确认' : '已确认（来源成绩已变化，不再适用）'
  return waiting ? '待确认（较晚录入，须先处理更早的记录）' : '待确认（来源成绩已变化，记录失效）'
}

export function CompetitionAction({
  action,
  t,
  ws,
  resources,
  next,
  close,
  saved,
  refresh,
}: {
  action: CompetitionActionType
  t: Tournament
  ws: Workspace
  resources: MachineResource[]
  next: number
  close: () => void
  saved: (message: string) => void
  /** Re-read the page data (workspace and preview) while the panel stays open. */
  refresh: () => void
}) {
  const fieldId = useId()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  // local: input validation; server: failed write; refreshed: failed write whose
  // conflict code already triggered a re-read of the workspace.
  const [errorSource, setErrorSource] = useState<'local' | 'server' | 'refreshed'>('server')
  const [notice, setNotice] = useState('')
  const [stage, setStage] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const [method, setMethod] = useState('')
  const [drawnAt, setDrawnAt] = useState('')
  const [order, setOrder] = useState<number[]>([])
  const [historical, setHistorical] = useState(false)
  // Lottery write responses, overlaid on the workspace until the re-read lands.
  const [writtenLotteries, setWrittenLotteries] = useState<Lottery[]>([])
  const [voidTarget, setVoidTarget] = useState<number | null>(null)
  const [voidReason, setVoidReason] = useState('')
  const [voidStage, setVoidStage] = useState(false)
  const table = action.mode === 'result' || action.mode === 'correct' ? action.table : null
  const needed = t.expected_table_count || 0
  const free = resources.filter(
    (m) =>
      m.assignable ||
      (action.mode === 'review' && ws.mapping.some((f) => f.machine_id === m.machine_id)),
  )
  const machineLabel = (pk: number) => {
    const machine = resources.find((m) => m.machine_id === pk)
    return machine ? `${machine.machine_no} · ${machine.name}` : `设备 #${pk}`
  }
  const playerName = (pk: number) =>
    ws.standings.find((s) => s.participant_id === pk)?.display_name || `选手 #${pk}`
  const members = action.mode === 'lottery' ? action.members : null
  const groupLotteries = members
    ? mergeLotteries(ws.lotteries, writtenLotteries).filter((l) => sameMembers(l.members, members))
    : []
  // Earliest first: a later record can never be confirmed in place of an earlier one.
  const pendingLotteries = members
    ? groupLotteries
        .filter((l) => isPendingLottery(l, members, ws.source_versions))
        .sort((a, b) => a.id - b.id)
    : []
  const pending = pendingLotteries[0] || null
  const lotteryHistory = groupLotteries.filter((l) => l !== pending).sort((a, b) => b.id - a.id)
  const groupOpen =
    !!members && (ws.unresolved_groups ?? []).some((group) => sameMembers(group, members))
  const title = {
    generate: next === 1 ? '确认选桌与首轮' : `确认生成第 ${next} 轮`,
    result: '半庄成绩',
    correct: '更正半庄成绩',
    'result-history': '成绩更正记录',
    finish: '确认正式完赛',
    replace: '故障替换物理桌',
    history: '物理桌占用历史',
    review: '旧赛事兼容复核',
    lottery: '公开抽签与确认',
  }[action.mode]
  async function run(operation: () => Promise<unknown>, message: string, stay = false) {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      await operation()
      if (!stay) saved(message)
    } catch (e) {
      setError(e as Error)
      // The server state moved on (pending/voided/confirmed/completed elsewhere):
      // show its message and re-read everything before any further decision.
      if (e instanceof ApiError && e.status === 409 && conflictRefreshCodes.has(e.code)) {
        setErrorSource('refreshed')
        refresh()
      } else setErrorSource('server')
    } finally {
      setBusy(false)
    }
  }
  function record() {
    if (!members) return
    const versions = ws.source_versions
    void run(
      async () => {
        const row = await recordLottery(t.id, {
          members,
          order,
          method,
          description: reason,
          drawn_at: new Date(drawnAt).toISOString(),
          source_versions: versions,
        })
        setWrittenLotteries((rows) => [
          ...rows,
          { ...row, source_versions: row.source_versions ?? versions },
        ])
        setNotice('公开抽签记录已保存，请核对后二次确认；如记录有误，可填写原因作废。')
        // Whatever happens next (confirm, close or cancel) the page must not keep
        // showing a workspace without this record.
        refresh()
      },
      '',
      true,
    )
  }
  function revoke(lottery: Lottery) {
    const text = voidReason.trim()
    if (!text || text.length > voidReasonLimit) return
    void run(
      async () => {
        const row = await voidLottery(t.id, lottery.id, text)
        setWrittenLotteries((rows) => [...rows.filter((r) => r.id !== row.id), row])
        setVoidTarget(null)
        setVoidReason('')
        setVoidStage(false)
        // A voided draw must never be reused: start the next record from scratch.
        setOrder([])
        setMethod('')
        setDrawnAt('')
        setReason('')
        setNotice(`抽签记录 #${lottery.id} 已作废。请重新组织公开抽签后录入新结果。`)
        refresh()
      },
      '',
      true,
    )
  }
  const pickers = (
    <div className="table-pickers">
      {Array.from({ length: needed }, (_, i) => (
        <label className="round-field" key={i}>
          逻辑桌 {'ABCD'[i]}
          <Select
            aria-label={`逻辑桌 ${'ABCD'[i]} 物理桌`}
            value={selected[i] || ''}
            disabled={busy}
            onValueChange={(value) => {
              // Any change after a preview invalidates it: preview again before submit.
              setStage(false)
              setSelected((v) =>
                Array.from({ length: needed }, (_, j) => (j === i ? Number(value) : v[j] || 0)),
              )
            }}
            options={[
              { value: '', label: '选择真实物理桌' },
              ...free.map((m) => ({
                value: m.machine_id,
                label: `${m.machine_no} · ${m.name}`,
                disabled: selected.includes(m.machine_id) && selected[i] !== m.machine_id,
              })),
            ]}
          />
        </label>
      ))}
    </div>
  )
  const selectionValid =
    selected.length === needed && selected.every(Boolean) && new Set(selected).size === needed
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <SheetContent
        className="machine-sheet tournament-sheet competition-sheet"
        showCloseButton={false}
      >
        <SheetHeader>
          <span className="eyebrow">{table ? 'TABLE RESULT' : 'CONFIRM OPERATION'}</span>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{t.name} · 操作不会自动重试</SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          size="icon"
          variant="ghost"
          aria-label="关闭比赛操作"
          disabled={busy}
          onClick={close}
        >
          <X />
        </Button>
        <div className="competition-action-body">
          {action.mode === 'generate' && (
            <>
              <p>
                {next === 1
                  ? `为 ${t.participant_count} 位选手选择 ${needed} 张物理桌，顺序对应 A～D。`
                  : '根据已确认累计表现排序、每四人一组；新轮次四风重新随机，物理桌保持不变。'}
              </p>
              {next === 1 && pickers}
              {stage && (
                <div className="confirmation-preview">
                  <h3>最终确认</h3>
                  {next === 1 ? (
                    selected.map((pk, i) => (
                      <p key={pk}>
                        逻辑桌 {'ABCD'[i]} →{' '}
                        {resources.find((m) => m.machine_id === pk)?.machine_no}
                      </p>
                    ))
                  ) : (
                    <p>将生成第 {next} 轮，不会覆盖已有座次。</p>
                  )}
                </div>
              )}
              <Button
                disabled={busy || (next === 1 && !selectionValid)}
                onClick={() =>
                  stage
                    ? void run(
                        () => generateRound(t.id, next, next === 1 ? selected : undefined),
                        '轮次已生成并持久化。',
                      )
                    : setStage(true)
                }
              >
                {busy ? '正在提交…' : stage ? '确认生成轮次' : '预览并确认'}
              </Button>
            </>
          )}
          {table && (
            <>
              {action.mode === 'correct' && ws.lotteries.length > 0 && (
                <p>
                  成绩变更后，原有抽签不再用于本次排名；仍然并列时需依据新成绩重新记录公开抽签，原记录保留。
                </p>
              )}
              <TableResultEditor
                table={table}
                tournament={t}
                correction={action.mode === 'correct'}
                busy={busy}
                error={error}
                run={run}
              />
            </>
          )}
          {action.mode === 'result-history' && <ResultCorrectionHistory table={action.table} />}
          {action.mode === 'history' && (
            <div className="allocation-history">
              {action.fixed.history.length ? (
                action.fixed.history.map((h) => (
                  <article key={h.id}>
                    <strong>物理桌 {h.machine_no_snapshot}</strong>
                    <p>
                      {h.status === 'active' ? '占用中' : '已释放'} · {h.source} · 稳定 machineId #
                      {h.machine_id}
                    </p>
                    <dl className="history-reasons">
                      <div>
                        <dt>建立原因</dt>
                        <dd>{h.reason || '初始选桌或旧占用继承'}</dd>
                      </div>
                      {h.status !== 'active' && (
                        <div>
                          <dt>释放原因</dt>
                          <dd>{h.release_reason || '未填写释放原因'}</dd>
                        </div>
                      )}
                    </dl>
                  </article>
                ))
              ) : (
                <p>无赛事预留记录。原始轮次分配历史由 API 保留。</p>
              )}
            </div>
          )}
          {action.mode === 'replace' && (
            <>
              <p>仅故障时替换逻辑桌 {action.fixed.label}。已生成轮次的历史映射与座次不变。</p>
              <label className="round-field">
                目标空闲物理桌
                <Select
                  aria-label="目标空闲物理桌"
                  value={target}
                  disabled={busy}
                  onValueChange={(value) => {
                    setStage(false)
                    setTarget(value)
                  }}
                  options={[
                    { value: '', label: '请选择' },
                    ...resources
                      .filter((m) => m.assignable)
                      .map((m) => ({ value: m.machine_id, label: `${m.machine_no} · ${m.name}` })),
                  ]}
                />
              </label>
              <label className="round-field">
                故障及替换原因
                <textarea
                  value={reason}
                  maxLength={500}
                  onChange={(e) => {
                    setStage(false)
                    setReason(e.target.value)
                  }}
                />
              </label>
              <Button
                disabled={busy || !target || !reason.trim()}
                onClick={() =>
                  stage
                    ? void run(
                        () => replaceTable(t.id, action.fixed.ordinal, Number(target), reason),
                        '物理桌已替换，历史已保留。',
                      )
                    : setStage(true)
                }
              >
                {stage ? '确认故障替换' : '预览替换'}
              </Button>
            </>
          )}
          {action.mode === 'review' && (
            <>
              <p>有效原占用会保留，已释放物理桌不会自动收回。复核不重排任何历史座次。</p>
              <label>
                <input
                  type="checkbox"
                  checked={historical}
                  disabled={busy}
                  onChange={(e) => {
                    setStage(false)
                    setHistorical(e.target.checked)
                  }}
                />{' '}
                全部配置轮次已存在，无需后续实体对局，仅补历史成绩
              </label>
              {!historical && pickers}
              <label className="round-field">
                复核说明
                <textarea
                  maxLength={500}
                  value={reason}
                  onChange={(e) => {
                    setStage(false)
                    setReason(e.target.value)
                  }}
                />
              </label>
              {stage && (
                <div className="confirmation-preview" aria-label="兼容复核摘要">
                  <h3>复核摘要</h3>
                  <p>
                    historical_only：
                    {historical
                      ? '是 · 仅补录历史成绩并正常完赛，不占用物理桌'
                      : '否 · 继续后续实体对局，按下列映射固定物理桌'}
                  </p>
                  {!historical &&
                    selected.map((pk, i) => (
                      <p key={pk}>
                        逻辑桌 {'ABCD'[i]} → 物理桌 {machineLabel(pk)}
                      </p>
                    ))}
                  <p>复核原因：{reason.trim()}</p>
                </div>
              )}
              <Button
                disabled={busy || !reason.trim() || (!historical && !selectionValid)}
                onClick={() =>
                  stage
                    ? void run(
                        () => reviewLegacy(t.id, historical, historical ? [] : selected, reason),
                        '兼容复核已保存。',
                      )
                    : setStage(true)
                }
              >
                {stage ? '确认兼容复核' : '预览复核'}
              </Button>
            </>
          )}
          {members && (
            <>
              <p>
                本组所有绩效指标完全相同。请在公开抽签完成后，依次选择所得完整顺序；系统不会随机生成结果。
              </p>
              <p>并列选手：{members.map(playerName).join('、')}</p>
              {!groupOpen ? (
                <div className="confirmation-preview">
                  <h3>该并列组已无需抽签</h3>
                  <p>赛事可能已完赛，或该组抽签已由其他操作确认。请关闭面板，核对最新排名。</p>
                </div>
              ) : pending ? (
                <>
                  <section
                    className="confirmation-preview lottery-record"
                    aria-labelledby={`${fieldId}-pending`}
                  >
                    <h3 id={`${fieldId}-pending`}>待二次确认的抽签记录 #{pending.id}</h3>
                    <ol className="lottery-order" aria-label="抽签顺序">
                      {pending.order.map((pk, i) => (
                        <li key={pk}>
                          第 {i + 1} 位：{playerName(pk)}
                        </li>
                      ))}
                    </ol>
                    <dl className="lottery-meta">
                      <div>
                        <dt>抽签方式</dt>
                        <dd>{pending.method}</dd>
                      </div>
                      <div>
                        <dt>公开过程说明</dt>
                        <dd>{pending.description}</dd>
                      </div>
                      <div>
                        <dt>实际抽签时间</dt>
                        <dd>{formatTime(pending.drawn_at)}</dd>
                      </div>
                      <div>
                        <dt>记录人</dt>
                        <dd>
                          管理员 #{pending.created_by_id} · {formatTime(pending.created_at)}
                        </dd>
                      </div>
                    </dl>
                    {pendingLotteries.length > 1 && (
                      <p>
                        该组另有 {pendingLotteries.length - 1}{' '}
                        条较晚录入的待确认记录，须先确认或作废本条。
                      </p>
                    )}
                    <p>同一并列组只允许一条待确认记录，处理前不能再录入新结果。</p>
                  </section>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void run(() => confirmLottery(t.id, pending.id), '公开抽签已确认。')
                    }
                  >
                    二次确认抽签顺序
                  </Button>
                  {voidTarget !== pending.id ? (
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => {
                        setVoidTarget(pending.id)
                        setVoidReason('')
                        setVoidStage(false)
                      }}
                    >
                      作废此记录
                    </Button>
                  ) : (
                    <>
                      <label className="round-field">
                        作废原因
                        <textarea
                          value={voidReason}
                          maxLength={voidReasonLimit}
                          required
                          disabled={busy}
                          aria-describedby={`${fieldId}-void-hint`}
                          onChange={(e) => {
                            setVoidStage(false)
                            setVoidReason(e.target.value)
                          }}
                        />
                      </label>
                      <p id={`${fieldId}-void-hint`} className="field-note">
                        必填，最多 {voidReasonLimit} 字（已填写 {voidReason.trim().length}{' '}
                        字）。作废记录保留审计，不能恢复，也不能再确认。
                      </p>
                      {voidStage && (
                        <div className="confirmation-preview" aria-label="作废确认">
                          <h3>确认作废抽签记录 #{pending.id}</h3>
                          <p>顺序：{pending.order.map(playerName).join(' → ')}</p>
                          <p>作废原因：{voidReason.trim()}</p>
                        </div>
                      )}
                      <Button
                        variant={voidStage ? 'destructive' : 'outline'}
                        disabled={busy || !voidReason.trim()}
                        onClick={() => (voidStage ? revoke(pending) : setVoidStage(true))}
                      >
                        {voidStage ? '确认作废' : '预览作废'}
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => {
                          setVoidTarget(null)
                          setVoidStage(false)
                        }}
                      >
                        放弃作废
                      </Button>
                    </>
                  )}
                </>
              ) : (
                <>
                  {members.map((_, i) => (
                    <label className="round-field" key={i}>
                      抽签顺位 {i + 1}
                      <Select
                        aria-label={`抽签顺位 ${i + 1}`}
                        disabled={busy}
                        value={order[i] || ''}
                        onValueChange={(value) =>
                          setOrder((v) =>
                            Array.from({ length: members.length }, (_, j) =>
                              j === i ? Number(value) : v[j] || 0,
                            ),
                          )
                        }
                        options={[
                          { value: '', label: '选择选手' },
                          ...members.map((pk) => ({
                            value: pk,
                            label: playerName(pk),
                            disabled: order.includes(pk) && order[i] !== pk,
                          })),
                        ]}
                      />
                    </label>
                  ))}
                  <label className="round-field">
                    抽签方式
                    <input
                      disabled={busy}
                      maxLength={200}
                      value={method}
                      onChange={(e) => setMethod(e.target.value)}
                    />
                  </label>
                  <label className="round-field">
                    实际抽签时间
                    <input
                      type="datetime-local"
                      disabled={busy}
                      value={drawnAt}
                      onChange={(e) => setDrawnAt(e.target.value)}
                    />
                  </label>
                  <label className="round-field">
                    公开过程说明
                    <textarea
                      disabled={busy}
                      maxLength={2000}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  <Button
                    disabled={
                      busy ||
                      order.length !== members.length ||
                      order.some((x) => !x) ||
                      new Set(order).size !== members.length ||
                      !method.trim() ||
                      !reason.trim() ||
                      !drawnAt
                    }
                    onClick={record}
                  >
                    保存公开抽签记录
                  </Button>
                </>
              )}
              {lotteryHistory.length > 0 && (
                <section className="lottery-history" aria-labelledby={`${fieldId}-history`}>
                  <h3 id={`${fieldId}-history`}>本组抽签记录历史</h3>
                  {lotteryHistory.map((l) => (
                    <article key={l.id}>
                      <strong>
                        记录 #{l.id} ·{' '}
                        {lotteryState(
                          l,
                          sameVersions(l.source_versions ?? [], ws.source_versions),
                          pendingLotteries.includes(l),
                        )}
                      </strong>
                      <p>顺序：{l.order.map(playerName).join(' → ')}</p>
                      <p>
                        {l.method} · 抽签时间 {formatTime(l.drawn_at)} · 记录人 管理员 #
                        {l.created_by_id}
                      </p>
                      {l.voided_at && (
                        <p>
                          作废原因：{l.void_reason || '未填写'} · {formatTime(l.voided_at)} · 管理员
                          #{l.voided_by_id}
                        </p>
                      )}
                    </article>
                  ))}
                </section>
              )}
            </>
          )}
          {action.mode === 'finish' && (
            <>
              <Trophy size={32} />
              <h3>唯一冠军：{ws.standings[0]?.display_name}</h3>
              <p>
                全部 {t.round_count}{' '}
                轮成绩已确认，最终排名将锁定。本赛事的有效物理桌占用将自动释放；不影响其他赛事。
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  void run(
                    () => completeTournament(t.id, ws.source_versions),
                    '赛事已正式完赛，物理桌已自动释放。',
                  )
                }
              >
                {busy ? '正在提交…' : '确认完赛并释放本场物理桌'}
              </Button>
            </>
          )}
          <FormFeedback error={error} success={notice} />
          {error && errorSource !== 'local' && (
            <p>
              {errorSource === 'refreshed'
                ? '已自动重新读取工作台数据，请核对最新状态后再决定是否操作。'
                : '请关闭面板并刷新工作台核对服务器状态，再决定是否重新操作。'}
            </p>
          )}
          <Button variant="ghost" disabled={busy} onClick={close}>
            {action.mode === 'history' ? '关闭' : '取消'}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
