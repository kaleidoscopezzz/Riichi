import { useState } from 'react'
import { X, Shuffle, Archive, ArrowLeftRight } from 'lucide-react'
import { Button } from './ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import {
  generateRound,
  reassignMachine,
  releaseMachine,
  windLabels,
  type MachineResource,
  type RoundTable,
  type Allocation,
} from '@/services/rounds'
import type { Tournament } from '@/services/tournaments'

export type RoundAction =
  | { mode: 'generate' }
  | { mode: 'reassign' | 'release'; table: RoundTable }
  | { mode: 'history'; table: RoundTable; history: Allocation[] }
export function RoundActionSheet({
  action,
  tournament,
  resources,
  close,
  saved,
}: {
  action: RoundAction
  tournament: Tournament
  resources: MachineResource[]
  close: () => void
  saved: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [machine, setMachine] = useState('')
  const [reason, setReason] = useState('')
  const free = resources.filter((m) => m.assignable)
  const needed = tournament.expected_table_count || 0
  const table = 'table' in action ? action.table : null
  const title = {
    generate: '确认生成第一轮',
    reassign: '确认调整物理设备',
    release: '确认释放物理设备',
    history: '设备分配历史',
  }[action.mode]
  async function submit() {
    setBusy(true)
    setError(null)
    try {
      if (action.mode === 'generate') {
        await generateRound(tournament.id)
        saved('第一轮已生成，随机座次与设备分配已持久化。')
      } else if (action.mode === 'reassign') {
        await reassignMachine(action.table.id, Number(machine))
        saved('物理设备已调整，原分配已释放并保留历史。')
      } else if (action.mode === 'release') {
        await releaseMachine(action.table.id, reason.trim())
        saved('设备已释放。此操作不代表成绩确认或轮次结束。')
      }
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
      <SheetContent
        className="machine-sheet tournament-sheet round-action-sheet"
        showCloseButton={false}
      >
        <SheetHeader>
          <span className="eyebrow">
            {action.mode === 'history' ? 'RESOURCE AUDIT' : 'CONFIRM OPERATION'}
          </span>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {tournament.name}
            {table ? ` · 第${table.round_number}轮 / 第${table.table_number}桌` : ''}
          </SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          variant="ghost"
          size="icon"
          aria-label="关闭轮次操作"
          disabled={busy}
          onClick={close}
        >
          <X />
        </Button>
        <div className="round-action-body">
          {action.mode === 'generate' && (
            <>
              <Shuffle className="round-action-icon" />
              <h3>一次生成，完整落位。</h3>
              <dl className="round-checklist">
                <div>
                  <dt>冻结参赛名单</dt>
                  <dd>{tournament.participant_count} 人</dd>
                </div>
                <div>
                  <dt>预计逻辑桌 / 所需设备</dt>
                  <dd>
                    {needed} 桌 / {needed} 台
                  </dd>
                </div>
                <div>
                  <dt>当前可分配设备</dt>
                  <dd>{free.length} 台</dd>
                </div>
              </dl>
              <p>
                将随机排列全部参赛者，按东、南、西、北持久化座次，并按设备编号升序分配机器。生成后刷新页面不会重新随机。
              </p>
              {free.length < needed && (
                <div className="form-feedback error" role="alert">
                  可分配设备不足：需要{needed}台，当前{free.length}台，不会部分生成。
                </div>
              )}
              <p className="round-warning">
                本阶段只生成第一轮。后续轮次须等待已确认成绩与累计积分。
              </p>
            </>
          )}
          {action.mode === 'reassign' && (
            <>
              <ArrowLeftRight className="round-action-icon" />
              <p>
                当前设备 <strong>{table?.active_allocation?.machine_no}</strong>{' '}
                将被释放，新的分配记录会保留完整历史。选手和座次不会改变。
              </p>
              <label className="round-field">
                目标空闲设备
                <select
                  value={machine}
                  disabled={busy}
                  onChange={(e) => setMachine(e.target.value)}
                >
                  <option value="">请选择设备</option>
                  {free.map((m) => (
                    <option key={m.machine_id} value={m.machine_id}>
                      {m.machine_no} · {m.name}
                    </option>
                  ))}
                </select>
              </label>
              {!free.length && <p role="status">当前没有空闲且可用的替换设备。</p>}
            </>
          )}
          {action.mode === 'release' && (
            <>
              <Archive className="round-action-icon" />
              <h3>确认实体设备已结束使用</h3>
              <p>
                将释放设备 <strong>{table?.active_allocation?.machine_no}</strong>
                ，供其他赛事分配。原始座次与占用历史保留。
              </p>
              <label className="round-field">
                释放说明（可选）
                <textarea
                  rows={3}
                  maxLength={500}
                  value={reason}
                  disabled={busy}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <p className="round-warning">
                设备释放不等于成绩确认，也不等于轮次正式结束。本阶段不支持重新开启已释放的占用。
              </p>
            </>
          )}
          {table && action.mode !== 'history' && (
            <div className="round-confirm-seats">
              {table.seats.map((s) => (
                <span key={s.id}>
                  {windLabels[s.seat_wind]} · {s.display_name}
                </span>
              ))}
            </div>
          )}
          {action.mode === 'history' && (
            <div className="allocation-history">
              {action.history.map((a) => (
                <article key={a.id}>
                  <div>
                    <strong>设备 {a.machine_no_snapshot}</strong>
                    <span>{a.status === 'active' ? '占用中' : '已释放'}</span>
                  </div>
                  <p>
                    稳定 machineId #{a.machine_id}
                    {a.machine_no !== a.machine_no_snapshot ? ` · 当前编号 ${a.machine_no}` : ''}
                  </p>
                  <p>
                    分配：{new Date(a.allocated_at).toLocaleString('zh-CN')} · 管理员 ID{' '}
                    {a.allocated_by}
                  </p>
                  {a.released_at && (
                    <>
                      <p>
                        释放：{new Date(a.released_at).toLocaleString('zh-CN')} · 管理员 ID{' '}
                        {a.released_by}
                      </p>
                      <p>{a.release_reason || '未填写释放说明'}</p>
                    </>
                  )}
                </article>
              ))}
              {!action.history.length && <p>没有分配记录。</p>}
            </div>
          )}
          <FormFeedback error={error} />
          <div className="machine-form-footer">
            <Button variant="outline" disabled={busy} onClick={close}>
              {action.mode === 'history' ? '关闭' : '取消'}
            </Button>
            {action.mode !== 'history' && (
              <Button
                disabled={
                  busy ||
                  (action.mode === 'generate' && (!needed || free.length < needed)) ||
                  (action.mode === 'reassign' && !machine)
                }
                onClick={() => void submit()}
              >
                {busy
                  ? '正在提交…'
                  : action.mode === 'generate'
                    ? '确认生成首轮'
                    : action.mode === 'reassign'
                      ? '确认调整设备'
                      : '确认释放设备'}
              </Button>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
