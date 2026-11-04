import { useEffect, useState } from 'react'
import { fetchRounds } from '@/services/rounds'
import { fetchWorkspace } from '@/services/competition'
import { Button } from './ui/button'
import { FormFeedback } from './form-feedback'

export function TournamentRoundSummary({ id }: { id: number }) {
  const [summary, setSummary] = useState<{ rounds: number; active: number } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setSummary(null)
    setError(null)
    void Promise.all([fetchRounds(id, controller.signal), fetchWorkspace(id, controller.signal)])
      .then(([{ results }, workspace]) => {
        if (!controller.signal.aborted)
          setSummary({
            rounds: results.length,
            active: workspace.mapping.filter((f) => f.machine_id).length,
          })
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e)
      })
    return () => controller.abort()
  }, [id, retry])
  return (
    <section className="tournament-round-summary" aria-label="赛事轮次与设备摘要">
      <h3>轮次与设备</h3>
      {error ? (
        <>
          <FormFeedback error={error} />
          <Button variant="outline" onClick={() => setRetry((v) => v + 1)}>
            重试轮次摘要
          </Button>
        </>
      ) : summary ? (
        <>
          <dl>
            <div>
              <dt>已生成轮次</dt>
              <dd>{summary.rounds} 轮</dd>
            </div>
            <div>
              <dt>当前占用设备</dt>
              <dd>{summary.active} 台</dd>
            </div>
          </dl>
          <p>
            {summary.rounds
              ? '进入比赛工作台录入成绩、查看累计榜与后续轮次。'
              : '尚未生成第一轮，请进入分桌工作台检查资源并确认生成。'}
          </p>
        </>
      ) : (
        <p role="status">正在读取轮次与设备占用…</p>
      )}
    </section>
  )
}
