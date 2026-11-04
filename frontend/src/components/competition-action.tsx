import { useState } from 'react'
import { Trophy, X } from 'lucide-react'
import { Button } from './ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import type { Tournament } from '@/services/tournaments'
import { generateRound, windLabels, type MachineResource, type RoundTable } from '@/services/rounds'
import {
  saveResult,
  completeTournament,
  recordLottery,
  confirmLottery,
  replaceTable,
  reviewLegacy,
  type Workspace,
  type FixedTable,
} from '@/services/competition'

export type CompetitionActionType =
  | { mode: 'generate' | 'finish' | 'review' }
  | { mode: 'result'; table: RoundTable }
  | { mode: 'replace'; fixed: FixedTable }
  | { mode: 'history'; fixed: FixedTable }
  | { mode: 'lottery'; members: number[] }

export function CompetitionAction({
  action,
  t,
  ws,
  resources,
  next,
  close,
  saved,
}: {
  action: CompetitionActionType
  t: Tournament
  ws: Workspace
  resources: MachineResource[]
  next: number
  close: () => void
  saved: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [stage, setStage] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const [method, setMethod] = useState('')
  const [drawnAt, setDrawnAt] = useState('')
  const [order, setOrder] = useState<number[]>([])
  const [historical, setHistorical] = useState(false)
  const [lotteryId, setLotteryId] = useState<number | null>(null)
  const table = action.mode === 'result' ? action.table : null
  const [points, setPoints] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      table?.seats.map((s) => [
        String(s.participant_id),
        table.result?.points[s.participant_id]?.toString() ?? '',
      ]) || [],
    ),
  )
  const [version, setVersion] = useState(table?.result?.version || 0)
  const needed = t.expected_table_count || 0
  const allInteger = Object.values(points).every(
    (v) => /^-?\d+$/.test(v) && Number.isSafeInteger(Number(v)),
  )
  const filled = Object.values(points).filter((v) => v !== '').length
  const sum = Object.values(points).reduce((n, v) => n + (/^-?\d+$/.test(v) ? BigInt(v) : 0n), 0n)
  const expected = BigInt(t.starting_points) * 4n
  const valid = allInteger && filled === 4 && sum === expected
  const free = resources.filter(
    (m) =>
      m.assignable ||
      (action.mode === 'review' && ws.mapping.some((f) => f.machine_id === m.machine_id)),
  )
  const title = {
    generate: next === 1 ? '确认选桌与首轮' : `确认生成第 ${next} 轮`,
    result: '半庄成绩',
    finish: '确认正式完赛',
    replace: '故障替换物理桌',
    history: '物理桌占用历史',
    review: '旧赛事兼容复核',
    lottery: '公开抽签与确认',
  }[action.mode]
  async function run(operation: () => Promise<unknown>, message: string, stay = false) {
    setBusy(true)
    setError(null)
    try {
      await operation()
      if (!stay) saved(message)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  async function result(confirm: boolean) {
    const values = table!.seats.map((s) => ({
      participant_id: s.participant_id,
      raw_points: points[s.participant_id] === '' ? null : Number(points[s.participant_id]),
    }))
    if (values.some((v) => v.raw_points !== null && !Number.isSafeInteger(v.raw_points))) {
      setError(new Error('点数必须是安全范围内的整数。'))
      return
    }
    await run(
      async () => {
        const row = await saveResult(table!.id, version, values, confirm)
        setVersion(row.version)
      },
      confirm ? '成绩已正式确认并锁定。' : '草稿已保存，可刷新后继续填写。',
    )
  }
  const pickers = (
    <div className="table-pickers">
      {Array.from({ length: needed }, (_, i) => (
        <label className="round-field" key={i}>
          逻辑桌 {'ABCD'[i]}
          <select
            aria-label={`逻辑桌 ${'ABCD'[i]} 物理桌`}
            value={selected[i] || ''}
            onChange={(e) =>
              setSelected((v) =>
                Array.from({ length: needed }, (_, j) =>
                  j === i ? Number(e.target.value) : v[j] || 0,
                ),
              )
            }
          >
            <option value="">选择真实物理桌</option>
            {free.map((m) => (
              <option
                key={m.machine_id}
                value={m.machine_id}
                disabled={selected.includes(m.machine_id) && selected[i] !== m.machine_id}
              >
                {m.machine_no} · {m.name}
              </option>
            ))}
          </select>
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
          <span className="eyebrow">
            {action.mode === 'result' ? 'TABLE RESULT' : 'CONFIRM OPERATION'}
          </span>
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
              <p>
                第 {table.round_number} 轮 · 逻辑桌 {'ABCD'[table.table_number - 1]}
                。允许负数与零，未确认前可保存部分草稿。
              </p>
              <div className="result-inputs">
                {table.seats.map((s) => (
                  <label key={s.id} className="round-field">
                    <span>
                      {windLabels[s.seat_wind]} · {s.display_name}
                    </span>
                    <input
                      autoComplete="off"
                      inputMode="text"
                      aria-label={`${s.display_name} 终局点数`}
                      value={points[s.participant_id]}
                      onChange={(e) => {
                        setStage(false)
                        setPoints((v) => ({ ...v, [s.participant_id]: e.target.value }))
                      }}
                      placeholder="整数点数"
                    />
                  </label>
                ))}
              </div>
              <div className={`points-total ${valid ? 'valid' : ''}`} aria-live="polite">
                <p>
                  已填写 {filled} / 4 · 实录合计 {sum.toString()}
                </p>
                <p>
                  标准合计 {expected.toString()} · 差额 {(sum - expected).toString()}
                </p>
              </div>
              <p>
                {valid
                  ? '总点数检查通过。确认后结果锁定，不可修改。'
                  : '须四人整数点数且总和等于标准合计，异常只能保存草稿。'}
              </p>
              <Button variant="outline" disabled={busy} onClick={() => void result(false)}>
                保存成绩草稿
              </Button>
              <Button
                disabled={busy || !valid}
                onClick={() => (stage ? void result(true) : setStage(true))}
              >
                {busy ? '正在提交…' : stage ? '再次确认并锁定成绩' : '确认成绩'}
              </Button>
            </>
          )}
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
                    <p>{h.reason || '初始选桌或旧占用继承'}</p>
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
                <select
                  value={target}
                  onChange={(e) => {
                    setStage(false)
                    setTarget(e.target.value)
                  }}
                >
                  <option value="">请选择</option>
                  {resources
                    .filter((m) => m.assignable)
                    .map((m) => (
                      <option key={m.machine_id} value={m.machine_id}>
                        {m.machine_no} · {m.name}
                      </option>
                    ))}
                </select>
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
                  onChange={(e) => setHistorical(e.target.checked)}
                />{' '}
                全部配置轮次已存在，无需后续实体对局，仅补历史成绩
              </label>
              {!historical && pickers}
              <label className="round-field">
                复核说明
                <textarea
                  maxLength={500}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
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
          {action.mode === 'lottery' && (
            <>
              <p>
                本组所有绩效指标完全相同。请在公开抽签完成后，依次选择所得完整顺序；系统不会随机生成结果。
              </p>
              {action.members.map((_, i) => (
                <label className="round-field" key={i}>
                  抽签顺位 {i + 1}
                  <select
                    disabled={!!lotteryId}
                    value={order[i] || ''}
                    onChange={(e) =>
                      setOrder((v) =>
                        Array.from({ length: action.members.length }, (_, j) =>
                          j === i ? Number(e.target.value) : v[j] || 0,
                        ),
                      )
                    }
                  >
                    <option value="">选择选手</option>
                    {action.members.map((pk) => (
                      <option key={pk} value={pk} disabled={order.includes(pk) && order[i] !== pk}>
                        {ws.standings.find((s) => s.participant_id === pk)?.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <label className="round-field">
                抽签方式
                <input
                  disabled={!!lotteryId}
                  maxLength={200}
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                />
              </label>
              <label className="round-field">
                实际抽签时间
                <input
                  type="datetime-local"
                  disabled={!!lotteryId}
                  value={drawnAt}
                  onChange={(e) => setDrawnAt(e.target.value)}
                />
              </label>
              <label className="round-field">
                公开过程说明
                <textarea
                  disabled={!!lotteryId}
                  maxLength={2000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              {!lotteryId ? (
                <Button
                  disabled={
                    busy ||
                    order.length !== action.members.length ||
                    order.some((x) => !x) ||
                    new Set(order).size !== action.members.length ||
                    !method.trim() ||
                    !reason.trim() ||
                    !drawnAt
                  }
                  onClick={() =>
                    void run(
                      async () => {
                        const l = await recordLottery(t.id, {
                          members: action.members,
                          order,
                          method,
                          description: reason,
                          drawn_at: new Date(drawnAt).toISOString(),
                          source_versions: ws.source_versions,
                        })
                        setLotteryId(l.id)
                      },
                      '',
                      true,
                    )
                  }
                >
                  保存公开抽签记录
                </Button>
              ) : (
                <>
                  <p>记录已保存，请核对上述顺序。确认后用于正式排名。</p>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void run(() => confirmLottery(t.id, lotteryId), '公开抽签已确认。')
                    }
                  >
                    二次确认抽签顺序
                  </Button>
                </>
              )}
              {!lotteryId &&
                ws.lotteries
                  .filter(
                    (l) =>
                      !l.confirmed_at &&
                      l.members.length === action.members.length &&
                      l.members.every((pk) => action.members.includes(pk)),
                  )
                  .map((l) => (
                    <div className="confirmation-preview" key={l.id}>
                      <p>
                        已有待确认记录：
                        {l.order
                          .map(
                            (pk) => ws.standings.find((s) => s.participant_id === pk)?.display_name,
                          )
                          .join(' → ')}
                      </p>
                      <p>
                        {l.method} · {l.description}
                      </p>
                      <Button
                        disabled={busy}
                        onClick={() =>
                          void run(() => confirmLottery(t.id, l.id), '已有公开抽签已二次确认。')
                        }
                      >
                        核对并确认已有抽签
                      </Button>
                    </div>
                  ))}
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
          <FormFeedback error={error} />
          {error && <p>请关闭面板并刷新工作台核对服务器状态，再决定是否重新操作。</p>}
          <Button variant="ghost" disabled={busy} onClick={close}>
            {action.mode === 'history' ? '关闭' : '取消'}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
