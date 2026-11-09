import { useEffect, useState } from 'react'
import { Button } from './ui/button'
import { FormFeedback } from './form-feedback'
import {
  displayScore,
  exactScore,
  fetchResultCorrections,
  type ResultCorrection,
} from '@/services/competition'
import type { RoundTable } from '@/services/rounds'

export function ResultCorrectionHistory({ table }: { table: RoundTable }) {
  const [rows, setRows] = useState<ResultCorrection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let current = true
    setLoading(true)
    setError(null)
    void fetchResultCorrections(table.id, controller.signal)
      .then((data) => {
        if (current) setRows(data.corrections)
      })
      .catch((error) => {
        if (current && !controller.signal.aborted) setError(error as Error)
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
      controller.abort()
    }
  }, [table.id, retry])
  if (loading) return <p role="status">正在读取更正记录…</p>
  if (error)
    return (
      <>
        <FormFeedback error={error} />
        <Button variant="outline" onClick={() => setRetry((value) => value + 1)}>
          重试读取更正记录
        </Button>
      </>
    )
  return (
    <section className="result-correction-history" aria-label="成绩更正记录">
      <p>
        第 {table.round_number} 轮 · 逻辑桌 {'ABCD'[table.table_number - 1]}
      </p>
      {!rows.length && <p>尚无成绩更正记录。</p>}
      {rows.map((row) => (
        <article key={row.id}>
          <header>
            <time>{new Date(row.corrected_at).toLocaleString('zh-CN')}</time>
            <span>更正人：{row.corrected_by_username || '管理员'}</span>
          </header>
          {row.reason && <p>{row.reason}</p>}
          {table.seats.map((seat) => {
            const before = row.before.scores.find(
              (score) => score.participant_id === seat.participant_id,
            )
            const after = row.after.scores.find(
              (score) => score.participant_id === seat.participant_id,
            )
            return (
              <div className="correction-player" key={seat.id}>
                <strong>{seat.display_name}</strong>
                <span>
                  点数 {row.before.points[seat.participant_id]} →{' '}
                  {row.after.points[seat.participant_id]}
                </span>
                <span
                  title={
                    before && after
                      ? `${exactScore(before.score)} → ${exactScore(after.score)}`
                      : undefined
                  }
                >
                  积分 {before ? displayScore(before.score) : '—'} →{' '}
                  {after ? displayScore(after.score) : '—'}
                </span>
              </div>
            )
          })}
        </article>
      ))}
    </section>
  )
}
