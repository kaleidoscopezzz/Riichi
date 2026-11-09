import { useEffect, useRef, useState } from 'react'
import { GripVertical } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { FormFeedback } from './form-feedback'
import { ApiError } from '@/services/api'
import { displayScore, exactScore } from '@/services/competition'
import { generateRound, previewPairing, type PairingPlan } from '@/services/rounds'
import type { Tournament } from '@/services/tournaments'

type Slot = { table: number; position: number }
export function PairingBoard({
  tournament,
  next,
  machineIds,
  ready,
  busy,
  error,
  run,
}: {
  tournament: Tournament
  next: number
  machineIds?: number[]
  ready: boolean
  busy: boolean
  error: Error | null
  run: (operation: () => Promise<unknown>, message: string, stay?: boolean) => Promise<void>
}) {
  const [retry, setRetry] = useState(0)
  const requestKey = `${tournament.id}:${next}:${retry}`
  const [storedPlan, setStoredPlan] = useState<{ key: string; data: PairingPlan } | null>(null)
  const plan = storedPlan?.key === requestKey ? storedPlan.data : null
  const [groups, setGroups] = useState<number[][]>([])
  const [storedError, setStoredError] = useState<{ key: string; error: Error } | null>(null)
  const previewError = storedError?.key === requestKey ? storedError.error : null
  const loading = !plan && !previewError
  const [stage, setStage] = useState(false)
  const [dragging, setDragging] = useState<Slot | null>(null)
  const [hover, setHover] = useState<Slot | null>(null)
  const board = useRef<HTMLElement>(null)
  const hoverRef = useRef<Slot | null>(null)
  const frame = useRef<number | null>(null)
  const drag = useRef<{
    source: Slot
    x: number
    y: number
    startX: number
    startY: number
    active: boolean
    scroll: HTMLElement | null
  } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let current = true
    setStoredPlan(null)
    setGroups([])
    setStage(false)
    setStoredError(null)
    void previewPairing(tournament.id, next, controller.signal)
      .then((data) => {
        if (current) {
          setStoredPlan({ key: requestKey, data })
          setGroups(data.tables.map((table) => [...table.participant_ids]))
          setStage(false)
        }
      })
      .catch((error) => {
        if (current && !controller.signal.aborted)
          setStoredError({ key: requestKey, error: error as Error })
      })
    return () => {
      current = false
      controller.abort()
    }
  }, [tournament.id, next, requestKey])
  useEffect(() => () => stopDrag(false), [])
  useEffect(() => {
    if (busy || stage || loading) stopDrag()
  }, [busy, stage, loading])
  const stale = error instanceof ApiError && error.code === 'stale_pairing'
  const people = new Map(plan?.participants.map((person) => [person.id, person]))
  function swap(source: Slot, target: Slot) {
    if (busy || stage || !plan?.manual) return
    const participant = groups[source.table][source.position]
    setGroups((previous) => {
      const updated = previous.map((group) => [...group])
      const value = updated[source.table][source.position]
      updated[source.table][source.position] = updated[target.table][target.position]
      updated[target.table][target.position] = value
      return updated
    })
    requestAnimationFrame(() =>
      document
        .querySelector<HTMLElement>(`[data-pair-participant="${participant}"] [data-pair-handle]`)
        ?.focus(),
    )
  }
  async function reload() {
    await run(
      async () => {
        setStage(false)
        setRetry((value) => value + 1)
      },
      '',
      true,
    )
  }
  function stopDrag(update = true) {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    drag.current = null
    hoverRef.current = null
    if (update) {
      setDragging(null)
      setHover(null)
    }
  }
  function locateTarget(x: number, y: number) {
    const element = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-pairing-slot]')
    const target =
      element && board.current?.contains(element)
        ? { table: Number(element.dataset.tableIndex), position: Number(element.dataset.position) }
        : null
    hoverRef.current = target
    setHover(target)
  }
  function scrollEdge() {
    const current = drag.current
    if (!current?.active) {
      frame.current = null
      return
    }
    const container = current.scroll
    if (container) {
      const rect = container.getBoundingClientRect()
      const top = Math.max(rect.top, 0),
        bottom = Math.min(rect.bottom, window.innerHeight)
      const edge = 48
      let speed = 0
      if (current.y < top + edge)
        speed = -Math.ceil(18 * Math.min(1, (top + edge - current.y) / edge))
      else if (current.y > bottom - edge)
        speed = Math.ceil(18 * Math.min(1, (current.y - bottom + edge) / edge))
      if (speed) container.scrollTop += speed
    }
    locateTarget(current.x, current.y)
    frame.current = requestAnimationFrame(scrollEdge)
  }
  return (
    <section ref={board} className="pairing-board" aria-label="本轮分桌预览">
      <h3>
        {plan?.strategy_label ?? '分桌预览'} · 第 {next} 轮
      </h3>
      <p>
        {plan?.manual
          ? '拖动选手手柄到另一位置即可交换；也可通过“移动至”选择目标。每桌保持4人，四风生成时随机。'
          : '分组按本赛事冻结策略生成，四风生成时随机。'}
      </p>
      {loading && <p role="status">正在预排本轮分桌…</p>}
      <FormFeedback error={previewError} />
      {plan && !loading && (
        <>
          {plan.strategy.startsWith('swiss_') && (
            <p>
              预计 {plan.repeat_pairs} 对重复对手（累计重遇 {plan.repeat_encounters} 次）。
              {plan.repeat_pairs > 0 && '当前优先级下仍有重遇，生成前请核对分组。'}
            </p>
          )}
          <div className="pairing-tables">
            {groups.map((group, tableIndex) => (
              <article key={tableIndex} aria-label={`逻辑桌 ${'ABCD'[tableIndex]} 分组`}>
                <header>
                  <h4>逻辑桌 {'ABCD'[tableIndex]}</h4>
                  <span>每人附加基础分 {plan.tables[tableIndex].base_bonus}</span>
                </header>
                {group.map((participant, position) => {
                  const person = people.get(participant)!
                  const isSource = dragging?.table === tableIndex && dragging.position === position
                  const isTarget = hover?.table === tableIndex && hover.position === position
                  return (
                    <div
                      key={participant}
                      data-pair-participant={participant}
                      data-pairing-slot
                      data-table-index={tableIndex}
                      data-position={position}
                      className={`pairing-card ${isSource ? 'dragging' : ''} ${isTarget ? 'drop-target' : ''}`}
                    >
                      <div className="pairing-person">
                        {plan.manual && (
                          <Button
                            data-pair-handle
                            variant="ghost"
                            size="icon"
                            aria-label={`拖动 ${person.display_name}`}
                            disabled={busy || stage || stale}
                            onPointerDown={(event) => {
                              if (event.button !== 0) return
                              event.currentTarget.setPointerCapture?.(event.pointerId)
                              drag.current = {
                                source: { table: tableIndex, position },
                                x: event.clientX,
                                y: event.clientY,
                                startX: event.clientX,
                                startY: event.clientY,
                                active: false,
                                scroll: event.currentTarget.closest<HTMLElement>(
                                  '.competition-action-body',
                                ),
                              }
                            }}
                            onPointerMove={(event) => {
                              const current = drag.current
                              if (!current) return
                              current.x = event.clientX
                              current.y = event.clientY
                              if (
                                !current.active &&
                                Math.hypot(
                                  event.clientX - current.startX,
                                  event.clientY - current.startY,
                                ) >= 5
                              ) {
                                current.active = true
                                setDragging(current.source)
                                frame.current = requestAnimationFrame(scrollEdge)
                              }
                              if (!current.active) return
                              locateTarget(event.clientX, event.clientY)
                            }}
                            onPointerUp={(event) => {
                              if (drag.current?.active && hoverRef.current)
                                swap(drag.current.source, hoverRef.current)
                              stopDrag()
                              if (event.currentTarget.hasPointerCapture?.(event.pointerId))
                                event.currentTarget.releasePointerCapture(event.pointerId)
                            }}
                            onPointerCancel={() => stopDrag()}
                            onLostPointerCapture={() => stopDrag()}
                          >
                            <GripVertical aria-hidden="true" />
                          </Button>
                        )}
                        <strong>{person.display_name}</strong>
                        <span title={exactScore(person.total)}>
                          {displayScore(person.total)} 分
                        </span>
                      </div>
                      {plan.manual && (
                        <Select
                          aria-label={`移动 ${person.display_name} 至`}
                          value={`${tableIndex}:${position}`}
                          disabled={busy || stage || stale}
                          options={groups.flatMap((members, destination) =>
                            members.map((id, index) => ({
                              value: `${destination}:${index}`,
                              label: `${'ABCD'[destination]}桌 · ${people.get(id)?.display_name}`,
                              disabled: destination === tableIndex && index === position,
                            })),
                          )}
                          onValueChange={(value) => {
                            const [table, position] = value.split(':').map(Number)
                            swap({ table: tableIndex, position }, { table, position })
                          }}
                        />
                      )}
                    </div>
                  )
                })}
              </article>
            ))}
          </div>
          {stage && (
            <div className="confirmation-preview">
              <h3>最终确认分组</h3>
              <p>
                将按以上名单生成第 {next}{' '}
                轮，生成后保留历史座次。各桌人数、名单和成绩版本会再次校验。
              </p>
            </div>
          )}
        </>
      )}
      <div className="pairing-actions">
        <Button
          type="button"
          variant="outline"
          disabled={busy || loading}
          onClick={() => void reload()}
        >
          重新预览分桌
        </Button>
        {stage && (
          <Button type="button" variant="outline" disabled={busy} onClick={() => setStage(false)}>
            返回调整分组
          </Button>
        )}
        <Button
          type="button"
          disabled={busy || loading || !plan || !ready || stale}
          onClick={() =>
            stage && plan
              ? void run(
                  () =>
                    generateRound(tournament.id, next, machineIds, {
                      pairing_token: plan.token,
                      ...(plan.manual ? { participant_groups: groups } : {}),
                    }),
                  '轮次已生成并持久化。',
                )
              : setStage(true)
          }
        >
          {busy ? '正在提交…' : stage ? '确认生成轮次' : '预览并确认'}
        </Button>
      </div>
    </section>
  )
}
