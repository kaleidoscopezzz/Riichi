import { useId, useState } from 'react'
import { Button } from './ui/button'
import { FormFeedback } from './form-feedback'
import { ResultScorePreview } from './result-score-preview'
import { ApiError } from '@/services/api'
import { parsePoints } from '@/lib/points'
import { correctResult, fetchResult, saveResult } from '@/services/competition'
import { windLabels, type RoundTable } from '@/services/rounds'
import type { Tournament } from '@/services/tournaments'

export function TableResultEditor({
  table,
  tournament,
  correction,
  busy,
  error,
  run,
}: {
  table: RoundTable
  tournament: Tournament
  correction: boolean
  busy: boolean
  error: Error | null
  run: (operation: () => Promise<unknown>, message: string, stay?: boolean) => Promise<void>
}) {
  const fieldId = useId()
  const [base, setBase] = useState(table.result)
  const [points, setPoints] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      table.seats.map((seat) => [
        String(seat.participant_id),
        table.result?.points[seat.participant_id]?.toString() ?? '',
      ]),
    ),
  )
  const [reason, setReason] = useState('')
  const [stage, setStage] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [localError, setLocalError] = useState<Error | null>(null)
  const [notice, setNotice] = useState('')
  const version = base?.version ?? 0
  const locked = tournament.status !== 'started'
  const seats = table.seats.map((seat) => ({
    seat,
    parsed: parsePoints(points[seat.participant_id] ?? ''),
  }))
  const invalid = seats.filter(({ parsed }) => !parsed.ok).length
  const values = seats.map(({ seat, parsed }) => ({
    participant_id: seat.participant_id,
    raw_points: parsed.ok ? parsed.value : null,
  }))
  const entered = values.flatMap((value) => (value.raw_points === null ? [] : [value.raw_points]))
  const total = entered.reduce((sum, value) => sum + BigInt(value), 0n)
  const expected = BigInt(tournament.starting_points) * 4n
  const valid = invalid === 0 && entered.length === 4 && total === expected
  const changed = values.some(
    (value) => value.raw_points !== (base?.points[value.participant_id] ?? null),
  )
  const stale = error instanceof ApiError && error.status === 409 && error.code === 'stale_result'

  async function submit(confirm: boolean) {
    setAttempted(true)
    if (busy || locked) return
    if (invalid) {
      setLocalError(new Error('点数必须是安全范围内的整数，请按选手格子下方的提示修改后再保存。'))
      return
    }
    if ((confirm || correction) && !valid) return
    await run(
      async () => {
        const result = correction
          ? await correctResult(table.id, version, values, reason.trim())
          : await saveResult(table.id, version, values, confirm)
        setBase(result)
      },
      correction
        ? '成绩更正已保存，累计积分已更新。'
        : confirm
          ? '成绩已正式确认。'
          : '草稿已保存，可刷新后继续填写。',
    )
  }
  async function reload() {
    await run(
      async () => {
        const latest = await fetchResult(table.id)
        setBase(latest)
        setPoints(
          Object.fromEntries(
            table.seats.map((seat) => [
              String(seat.participant_id),
              latest.points[seat.participant_id]?.toString() ?? '',
            ]),
          ),
        )
        setTouched({})
        setAttempted(false)
        setStage(false)
        setLocalError(null)
        setNotice('已载入最新成绩，请重新核对；本次未保存的数字需要重新填写。')
      },
      '',
      true,
    )
  }
  return (
    <>
      <p>
        第 {table.round_number} {tournament.competition_type === 'team' ? '时段' : '轮'} · 逻辑桌{' '}
        {'ABCD'[table.table_number - 1]}。允许负数与零。
      </p>
      {correction && (
        <p>
          {tournament.competition_type === 'team'
            ? '更正会更新团队累计积分，已经开场的比赛保留出场人员和座次，旧成绩自动留档。'
            : '更正会更新累计积分和后续尚未生成轮次的排序。已经生成的轮次保留现有座次，旧成绩自动留档。'}
        </p>
      )}
      {table.base_bonus && table.base_bonus !== '0' && (
        <p>本桌每位选手附加基础分 {table.base_bonus}，已计入基础分和本场积分。</p>
      )}
      {locked && <p role="status">赛事已完赛，成绩只读。</p>}
      <fieldset className="result-editor-fields" disabled={busy || locked}>
        <div className="result-inputs">
          {seats.map(({ seat, parsed }) => {
            const errorId = `${fieldId}-points-${seat.participant_id}`
            const message =
              !parsed.ok && (attempted || touched[seat.participant_id]) ? parsed.error : ''
            return (
              <label key={seat.id} className="round-field">
                <span>
                  {windLabels[seat.seat_wind]} · {seat.display_name}
                </span>
                <input
                  autoComplete="off"
                  inputMode="text"
                  aria-label={`${seat.display_name} 终局点数`}
                  aria-invalid={message ? true : undefined}
                  aria-describedby={message ? errorId : undefined}
                  value={points[seat.participant_id]}
                  placeholder="整数点数"
                  onBlur={() =>
                    setTouched((previous) => ({ ...previous, [seat.participant_id]: true }))
                  }
                  onChange={(event) => {
                    setStage(false)
                    setLocalError(null)
                    setNotice('')
                    setPoints((previous) => ({
                      ...previous,
                      [seat.participant_id]: event.target.value,
                    }))
                  }}
                />
                {message && (
                  <span id={errorId} className="field-error">
                    {message}
                  </span>
                )}
              </label>
            )
          })}
        </div>
        {correction && (
          <label className="round-field">
            更正说明（可选）
            <input
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        )}
      </fieldset>
      <div className={`points-total ${valid ? 'valid' : ''}`} aria-live="polite">
        <p>
          已填写 {entered.length} / 4 · 实录合计 {total.toString()}
        </p>
        {invalid > 0 && <p>{invalid} 位选手的点数格式有误，未计入合计。</p>}
        <p>
          标准合计 {expected.toString()} · 差额 {(total - expected).toString()}
        </p>
      </div>
      <ResultScorePreview
        table={table}
        version={version}
        points={values}
        invalid={invalid > 0}
        disabled={busy || locked}
      />
      <p>
        {valid
          ? '总点数检查通过。确认后计入排行榜，赛事进行中可以更正。'
          : '须四人整数点数且总和等于标准合计，异常只能保存草稿。'}
      </p>
      <FormFeedback error={localError} success={notice} />
      {stale && (
        <div className="stale-notice">
          <p>成绩已由其他管理员更新，请载入最新成绩后再修改。</p>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void reload()}>
            重新加载最新成绩
          </Button>
        </div>
      )}
      {correction ? (
        <Button
          type="button"
          disabled={busy || locked || !valid || !changed || stale}
          onClick={() => void submit(true)}
        >
          {busy ? '正在保存…' : '保存更正'}
        </Button>
      ) : (
        <>
          <Button
            type="button"
            variant="outline"
            disabled={busy || locked || stale}
            onClick={() => void submit(false)}
          >
            保存成绩草稿
          </Button>
          <Button
            type="button"
            disabled={busy || locked || !valid || stale}
            onClick={() => (stage ? void submit(true) : setStage(true))}
          >
            {busy ? '正在提交…' : stage ? '再次确认成绩' : '确认成绩'}
          </Button>
        </>
      )}
    </>
  )
}
