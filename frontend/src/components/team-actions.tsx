import { useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import { ApiError } from '@/services/api'
import { confirmLottery, voidLottery, sameMembers, sameVersions } from '@/services/competition'
import {
  fetchTeamPlan,
  fetchTeamWorkspace,
  saveTeamPlan,
  setTeamRepresentatives,
  recordTeamLottery,
  type TeamPlan,
  type TeamTournament,
  type TeamWorkspace,
  type TeamStage,
  type TeamLottery,
} from '@/services/teams'

export type TeamRun = (
  operation: () => Promise<unknown>,
  message: string,
  stay?: boolean,
) => Promise<void>
export function TeamSheet({
  title,
  description,
  busy,
  close,
  children,
}: {
  title: string
  description: string
  busy: boolean
  close: () => void
  children: ReactNode
}) {
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
          <span className="eyebrow">TEAM COMPETITION</span>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          variant="ghost"
          size="icon"
          disabled={busy}
          aria-label="关闭团队操作"
          onClick={close}
        >
          <X />
        </Button>
        <div className="competition-action-body">
          {children}
          <Button variant="ghost" disabled={busy} onClick={close}>
            取消
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export function TeamPlanEditor({
  plan,
  t,
  busy,
  error,
  run,
}: {
  plan: TeamPlan
  t: TeamTournament
  busy: boolean
  error: Error | null
  run: TeamRun
}) {
  const [base, setBase] = useState(plan)
  const [teamIds, setTeamIds] = useState(plan.team_ids)
  const [lineup, setLineup] = useState(plan.lineup)
  const [supplied, setSupplied] = useState(plan.captain_supplied)
  const [notice, setNotice] = useState('')
  const stale = error instanceof ApiError && error.code === 'stale_team_plan'
  const manual = t.pairing_strategy === 'team_manual_v1'
  const position = base.stage_id !== null
  async function reload() {
    await run(
      async () => {
        const latest = await fetchTeamPlan(t.id, plan.id)
        setBase(latest)
        setTeamIds(latest.team_ids)
        setLineup(latest.lineup)
        setSupplied(latest.captain_supplied)
        setNotice('已载入最新本场名单，请重新核对。')
      },
      '',
      true,
    )
  }
  const locked = base.status !== 'draft' || t.status === 'completed'
  return (
    <>
      <p>
        第 {base.match_number} 场 ·{' '}
        {base.position_label ? `第 ${base.cycle} 循环 · ${base.position_label}` : '自由场次'}
        。每桌四支不同队伍各一人。
      </p>
      <fieldset disabled={busy || locked} className="team-lineup-fields">
        {teamIds.map((teamId, i) => {
          const team = t.teams.find((row) => row.id === teamId)
          return (
            <div key={i}>
              {manual ? (
                <label>
                  参赛队伍 {i + 1}
                  <Select
                    aria-label={`参赛队伍 ${i + 1}`}
                    value={teamId}
                    onValueChange={(value) => {
                      const id = Number(value)
                      setTeamIds((rows) => rows.map((old, j) => (i === j ? id : old)))
                      setLineup((rows) => ({ ...rows, [id]: null }))
                    }}
                    options={t.teams.map((row) => ({
                      value: row.id,
                      label: row.name,
                      disabled: teamIds.includes(row.id) && row.id !== teamId,
                    }))}
                  />
                </label>
              ) : (
                <strong>{team?.name}</strong>
              )}
              {!position && (
                <label>
                  {team?.name} 出场成员
                  <Select
                    aria-label={`${team?.name} 出场成员`}
                    value={lineup[teamId] ?? ''}
                    onValueChange={(value) =>
                      setLineup((rows) => ({ ...rows, [teamId]: value ? Number(value) : null }))
                    }
                    options={[
                      { value: '', label: '等待队长指定' },
                      ...(team?.members ?? []).map((m) => ({
                        value: m.id,
                        label: `${m.display_name}${m.is_active ? '' : '（档案已归档，赛事成员保留）'}`,
                      })),
                    ]}
                  />
                </label>
              )}
            </div>
          )
        })}
        {!position && (
          <label className="team-checkbox">
            <input
              type="checkbox"
              checked={supplied}
              onChange={(e) => setSupplied(e.target.checked)}
            />
            已收到队长指定名单
          </label>
        )}
      </fieldset>
      {position && (
        <p className="field-note">
          本场只调整四队分组，出场人员沿用本位置的队伍代表。保存后仍需核对各队本位置场数并确认计划。
        </p>
      )}
      <p className="field-note">缺出场人可以保存草稿；名单齐全后另行确认，确认后才可开场。</p>
      <FormFeedback success={notice} />
      {stale && (
        <Button variant="outline" disabled={busy} onClick={() => void reload()}>
          载入最新本场计划
        </Button>
      )}
      <Button
        disabled={busy || locked || stale || new Set(teamIds).size !== 4}
        onClick={() =>
          void run(
            () =>
              saveTeamPlan(t.id, base.id, {
                version: base.version,
                ...(manual ? { team_ids: teamIds } : {}),
                ...(!position
                  ? {
                      lineup: teamIds.map((team_id) => ({
                        team_id,
                        member_id: lineup[team_id] ?? null,
                      })),
                    }
                  : {}),
                captain_supplied: supplied,
              }),
            '本场出场名单已保存为草稿。',
          )
        }
      >
        {position ? '保存四队分组' : '保存出场计划'}
      </Button>
    </>
  )
}

export function TeamRepresentativesEditor({
  t,
  ws,
  stage,
  busy,
  error,
  run,
}: {
  t: TeamTournament
  ws: TeamWorkspace
  stage: TeamStage
  busy: boolean
  error: Error | null
  run: TeamRun
}) {
  const [base, setBase] = useState(stage)
  const [revision, setRevision] = useState(ws.revision)
  const [selected, setSelected] = useState<Record<string, number | null>>(
    Object.fromEntries(stage.representatives.map((r) => [r.team_id, r.member_id])),
  )
  const [supplied, setSupplied] = useState(true)
  const [withdraw, setWithdraw] = useState(false)
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState('')
  const stale =
    error instanceof ApiError &&
    ['stale_tournament', 'stage_representative_locked', 'team_plan_confirmed'].includes(error.code)
  async function reload() {
    await run(
      async () => {
        const current = await fetchTeamWorkspace(t.id)
        const found = current.stages?.find((row) => row.id === stage.id)
        if (!found) throw new Error('该位置已不属于当前赛程，请关闭后重新选择。')
        setBase(found)
        setRevision(current.revision)
        setSelected(Object.fromEntries(found.representatives.map((r) => [r.team_id, r.member_id])))
        setNotice('已载入最新位置代表名单。')
      },
      '',
      true,
    )
  }
  return (
    <>
      <p>
        第 {stage.cycle} 循环 · {stage.position_label} · 每队 {stage.games_per_team}{' '}
        场。同周期同位置由同一人打满场数，下周期可换人，也可兼任其他位置。
      </p>
      <fieldset className="team-lineup-fields" disabled={busy || t.status === 'completed'}>
        {t.teams.map((team) => {
          const locked = base.representatives.find((r) => r.team_id === team.id)?.locked
          return (
            <label key={team.id}>
              {team.name} {locked && '· 本位置已开场'}
              <Select
                aria-label={`${team.name} ${stage.position_label}代表`}
                value={selected[team.id] ?? ''}
                disabled={locked}
                onValueChange={(value) =>
                  setSelected((rows) => ({ ...rows, [team.id]: value ? Number(value) : null }))
                }
                options={[
                  { value: '', label: '等待队长指定' },
                  ...team.members.map((m) => ({ value: m.id, label: m.display_name })),
                ]}
              />
            </label>
          )
        })}
        <label className="team-checkbox">
          <input
            type="checkbox"
            checked={supplied}
            onChange={(e) => setSupplied(e.target.checked)}
          />
          已收到本次队长指定名单
        </label>
        <label className="team-checkbox">
          <input
            type="checkbox"
            checked={withdraw}
            onChange={(e) => setWithdraw(e.target.checked)}
          />
          更换未开场代表时，撤回本位置相关已确认计划
        </label>
        {withdraw && (
          <label>
            撤回原因
            <textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        )}
      </fieldset>
      <FormFeedback success={notice} />
      {stale && (
        <Button variant="outline" disabled={busy} onClick={() => void reload()}>
          载入最新位置名单
        </Button>
      )}
      <Button
        disabled={busy || t.status === 'completed' || (withdraw && !reason.trim())}
        onClick={() =>
          void run(
            () =>
              setTeamRepresentatives(t.id, stage.id, {
                revision,
                representatives: Object.entries(selected).map(([team, member]) => ({
                  team_id: Number(team),
                  member_id: member,
                })),
                captain_supplied: supplied,
                withdraw_confirmed: withdraw,
                reason,
              }),
            '位置代表名单已保存，相关未开场计划已更新。',
          )
        }
      >
        保存位置代表名单
      </Button>
    </>
  )
}

export function TeamLotteryEditor({
  t,
  ws,
  members,
  busy,
  error,
  run,
  refresh,
}: {
  t: TeamTournament
  ws: TeamWorkspace
  members: number[]
  busy: boolean
  error: Error | null
  run: TeamRun
  refresh: () => void
}) {
  const [written, setWritten] = useState<TeamLottery[]>([])
  const [order, setOrder] = useState<number[]>([])
  const [method, setMethod] = useState('')
  const [description, setDescription] = useState('')
  const [time, setTime] = useState('')
  const [notice, setNotice] = useState('')
  const [voidReason, setVoidReason] = useState('')
  const [voidStage, setVoidStage] = useState(false)
  const name = (id: number) => ws.teams.find((team) => team.id === id)?.name ?? `团队 #${id}`
  const merged = new Map((ws.lotteries ?? []).map((row) => [row.id, row]))
  for (const row of written) {
    const server = merged.get(row.id)
    if (
      !server ||
      ((row.confirmed_at || row.voided_at) && !(server.confirmed_at || server.voided_at))
    )
      merged.set(row.id, row)
  }
  const rows = [...merged.values()].filter(
    (row) => row.entity_type === 'team' && sameMembers(row.members, members),
  )
  const current = (row: TeamLottery) =>
    sameVersions(row.source_versions, ws.source_versions) &&
    JSON.stringify(row.roster_snapshot) === JSON.stringify(ws.roster_snapshot) &&
    JSON.stringify(row.plan_sources) === JSON.stringify(ws.plan_sources)
  const pending = rows
    .filter((row) => !row.confirmed_at && !row.voided_at && current(row))
    .sort((a, b) => a.id - b.id)[0]
  const open =
    t.status === 'started' &&
    (ws.unresolved_groups ?? []).some((group) => sameMembers(group, members))
  return (
    <>
      <p>团队总积分、当桌第一和第二合计均相同。请先现场公开抽签，再录入完整团队顺序。</p>
      <p>团队：{members.map(name).join('、')}</p>
      {!open ? (
        <p>当前团队并列组已变化，请关闭面板核对最新团队榜。原抽签历史仍保留。</p>
      ) : pending ? (
        <>
          <div className="confirmation-preview">
            <h3>待二次确认的团队抽签 #{pending.id}</h3>
            <ol>
              {pending.order.map((id) => (
                <li key={id}>{name(id)}</li>
              ))}
            </ol>
            <p>
              {pending.method} · {pending.description}
            </p>
            <p>{new Date(pending.drawn_at).toLocaleString('zh-CN')}</p>
          </div>
          <Button
            disabled={busy}
            onClick={() =>
              void run(() => confirmLottery(t.id, pending.id), '团队抽签顺序已二次确认。')
            }
          >
            二次确认团队抽签
          </Button>
          <label>
            作废原因
            <textarea
              maxLength={500}
              value={voidReason}
              disabled={busy}
              onChange={(e) => {
                setVoidReason(e.target.value)
                setVoidStage(false)
              }}
            />
          </label>
          {voidStage && (
            <p>
              将作废记录 #{pending.id}，原因：{voidReason.trim()}。原记录保留。
            </p>
          )}
          <Button
            variant="outline"
            disabled={busy || !voidReason.trim()}
            onClick={() =>
              voidStage
                ? void run(
                    async () => {
                      const row = (await voidLottery(
                        t.id,
                        pending.id,
                        voidReason.trim(),
                      )) as TeamLottery
                      setWritten((old) => [...old.filter((r) => r.id !== row.id), row])
                      setOrder([])
                      setMethod('')
                      setDescription('')
                      setTime('')
                      setVoidReason('')
                      setVoidStage(false)
                      setNotice('记录已作废，请重新组织公开抽签。')
                      refresh()
                    },
                    '',
                    true,
                  )
                : setVoidStage(true)
            }
          >
            {voidStage ? '确认作废团队记录' : '预览作废团队记录'}
          </Button>
        </>
      ) : (
        <>
          {members.map((_, i) => (
            <label key={i}>
              团队抽签顺位 {i + 1}
              <Select
                aria-label={`团队抽签顺位 ${i + 1}`}
                disabled={busy}
                value={order[i] || ''}
                onValueChange={(value) =>
                  setOrder((rows) =>
                    Array.from({ length: members.length }, (_, j) =>
                      j === i ? Number(value) : rows[j] || 0,
                    ),
                  )
                }
                options={[
                  { value: '', label: '选择团队' },
                  ...members.map((id) => ({
                    value: id,
                    label: name(id),
                    disabled: order.includes(id) && order[i] !== id,
                  })),
                ]}
              />
            </label>
          ))}
          <label>
            团队抽签方式
            <input
              maxLength={200}
              disabled={busy}
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            />
          </label>
          <label>
            实际团队抽签时间
            <input
              type="datetime-local"
              disabled={busy}
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </label>
          <label>
            团队公开过程说明
            <textarea
              maxLength={2000}
              disabled={busy}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <Button
            disabled={
              busy ||
              order.length !== members.length ||
              order.some((id) => !id) ||
              new Set(order).size !== members.length ||
              !method.trim() ||
              !description.trim() ||
              !time
            }
            onClick={() =>
              void run(
                async () => {
                  const row = await recordTeamLottery(t.id, ws, {
                    members,
                    order,
                    method,
                    description,
                    drawn_at: new Date(time).toISOString(),
                  })
                  setWritten((old) => [...old, row])
                  setNotice('团队抽签已记录，请核对后二次确认。')
                  refresh()
                },
                '',
                true,
              )
            }
          >
            保存公开团队抽签
          </Button>
        </>
      )}
      {rows
        .filter((row) => row.id !== pending?.id)
        .sort((a, b) => b.id - a.id)
        .map((row) => (
          <article className="confirmation-preview" key={row.id}>
            <strong>
              记录 #{row.id} ·{' '}
              {row.voided_at ? '已作废' : row.confirmed_at ? '已确认' : '来源已变化'}
            </strong>
            <p>
              {row.order.map(name).join(' → ')} · {row.method}
            </p>
            {row.voided_at && <p>作废原因：{row.void_reason}</p>}
            {!current(row) && <p>此记录保留原来源，不用于当前团队排名。</p>}
          </article>
        ))}
      <FormFeedback error={error} success={notice} />
    </>
  )
}
