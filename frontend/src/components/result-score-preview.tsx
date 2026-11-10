import { useEffect, useState } from 'react'
import { Button } from './ui/button'
import {
  previewResult,
  displayScore,
  exactScore,
  type ResultPreview,
  type TablePoints,
} from '@/services/competition'
import type { RoundTable } from '@/services/rounds'

export function ResultScorePreview({
  table,
  version,
  points,
  invalid,
  disabled,
}: {
  table: RoundTable
  version: number
  points: TablePoints
  invalid: boolean
  disabled: boolean
}) {
  const input = JSON.stringify({ version, points })
  const key = `${table.id}:${input}:${invalid}`
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState<{ key: string; data?: ResultPreview; error?: Error } | null>(
    null,
  )
  useEffect(() => {
    if (invalid || disabled) return
    const controller = new AbortController()
    let current = true
    const timer = setTimeout(() => {
      const values = JSON.parse(input) as { version: number; points: TablePoints }
      void previewResult(table.id, values.version, values.points, controller.signal)
        .then((data) => {
          if (current) setState({ key, data })
        })
        .catch((error) => {
          if (current && !controller.signal.aborted) setState({ key, error: error as Error })
        })
    }, 150)
    return () => {
      current = false
      clearTimeout(timer)
      controller.abort()
    }
  }, [table.id, input, key, invalid, disabled, retry])

  // Never show an earlier response under newly edited numbers, including when
  // a transport ignores abort or replies out of order.
  const current = state?.key === key ? state : null
  const data = current?.data
  const loading = !invalid && !disabled && !data && !current?.error
  return (
    <section className="result-score-preview" aria-label="实时积分试算" aria-busy={loading}>
      <h3>实时积分试算</h3>
      <p className="field-note" aria-live="polite">
        {invalid
          ? '请先修正点数格式。'
          : current?.error
            ? `暂时无法试算：${current.error.message}`
            : loading
              ? '正在计算积分…'
              : data?.complete
                ? data.valid_total
                  ? '按本赛事规则试算，保存后才更新正式成绩。'
                  : '点数合计尚不符合确认条件，以下为当前输入的试算。'
                : '补齐四人点数后显示顺位奖励和本场积分。'}
      </p>
      {current?.error && (
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => {
            setState(null)
            setRetry((v) => v + 1)
          }}
        >
          重试试算
        </Button>
      )}
      <div className="result-preview-grid">
        {table.seats.map((seat) => {
          const row = data?.scores.find((score) => score.participant_id === seat.participant_id)
          const team = data?.team_changes?.find(
            (change) => change.participant_id === seat.participant_id,
          )
          return (
            <article key={seat.id} aria-label={`${seat.display_name} 积分试算`}>
              <header>
                <strong>{seat.display_name}</strong>
                <span>
                  {row?.rank ? `${row.tied ? '并列' : ''}第 ${row.rank} 名` : '顺位待计算'}
                </span>
              </header>
              <p className="preview-raw-points">终局点数 {row?.raw_points ?? '—'}</p>
              <dl>
                {(
                  [
                    ['基础分', row?.base],
                    ['顺位奖励', row?.bonus],
                    ['本场积分', row?.score],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd title={value ? exactScore(value) : undefined}>
                      {value ? displayScore(value) : '—'}
                    </dd>
                  </div>
                ))}
              </dl>
              {team && (
                <div
                  className="team-preview-contribution"
                  aria-label={`${team.team_name} 累计积分试算`}
                >
                  <p>{team.team_name}</p>
                  <dl>
                    {(
                      [
                        ['团队当前积分', team.confirmed_total],
                        ['本次积分变化', team.score_change],
                        ['试算后团队积分', team.projected_total],
                      ] as const
                    ).map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd title={value ? exactScore(value) : undefined}>
                          {value ? displayScore(value) : '—'}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
