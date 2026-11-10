import {
  displayScore,
  displayPercent,
  exactScore,
  type Standing,
  type PerformanceStatistics,
} from '@/services/competition'

export function Standings({
  rows,
  completed,
  statistics,
}: {
  rows: Standing[]
  completed: boolean
  statistics?: PerformanceStatistics
}) {
  const names = (ids: number[]) =>
    ids
      .map((id) => rows.find((row) => row.participant_id === id)?.display_name)
      .filter(Boolean)
      .join('、')
  return (
    <section className="settings-panel standings-panel">
      <div className="competition-section-heading">
        <div>
          <span className="eyebrow">STANDINGS</span>
          <h3>{completed ? '最终排名' : '实时累计榜 · 暂列'}</h3>
        </div>
        <span>仅计入已确认成绩</span>
      </div>
      {statistics && (
        <>
          <div className="performance-highlights" aria-label="本场成绩亮点">
            <article>
              <span>四位回避率最高</span>
              <strong>
                {statistics.fourth_avoidance.value
                  ? displayPercent(statistics.fourth_avoidance.value)
                  : '—'}
              </strong>
              <p>{names(statistics.fourth_avoidance.participant_ids) || '等待确认成绩'}</p>
            </article>
            <article>
              <span>单个半庄最高终局点数</span>
              <strong>
                {statistics.highest_raw_points.value === null
                  ? '—'
                  : `${statistics.highest_raw_points.value.toLocaleString('zh-CN')} 点`}
              </strong>
              <p>{names(statistics.highest_raw_points.participant_ids) || '等待确认成绩'}</p>
            </article>
            <article>
              <span>当桌第一次数最多 · 吃1</span>
              <strong>
                {statistics.most_firsts.value === null ? '—' : `${statistics.most_firsts.value} 次`}
              </strong>
              <p>{names(statistics.most_firsts.participant_ids) || '等待出现当桌第一'}</p>
            </article>
          </div>
          <details className="statistics-note">
            <summary>统计口径</summary>
            <p>
              只统计已确认的半庄，包含已淘汰选手的历史成绩。同点沿用共享名次：并列第一均计入吃1，并列第三不计第四；四位回避率为未获第四的半庄数
              ÷ 已确认半庄数。终局点数表示半庄结束时的点棒，不是和牌累计打点。小数保留两位用于展示。
            </p>
          </details>
        </>
      )}
      {!rows.length ? (
        <p>暂无参赛选手。</p>
      ) : (
        <div className="standings-scroll">
          <table>
            <thead>
              <tr>
                <th>名次</th>
                <th>选手</th>
                <th>累计积分</th>
                <th>半庄最高点数</th>
                <th>四位回避率</th>
                <th>每轮成绩明细</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.participant_id}>
                  <td data-label="名次">{r.rank ?? '—'}</td>
                  <th scope="row" data-label="选手">
                    {r.display_name}
                    <small>
                      {r.eliminated_after_round
                        ? `第 ${r.eliminated_after_round} 轮后淘汰`
                        : completed
                          ? '完成赛程'
                          : '仍在赛'}{' '}
                      ·{' '}
                      {r.confirmed_rounds != null
                        ? `已确认 ${r.confirmed_rounds} 轮`
                        : r.rounds?.length
                          ? `已确认 ${r.rounds.length} 轮`
                          : '逐轮明细未收录'}
                    </small>
                  </th>
                  <td data-label="累计积分">
                    <strong title={`精确积分 ${exactScore(r.total)}`}>
                      {displayScore(r.total)} 分
                    </strong>
                  </td>
                  <td data-label="半庄最高点数">
                    {r.highest_raw_points == null
                      ? '—'
                      : `${r.highest_raw_points.toLocaleString('zh-CN')} 点`}
                  </td>
                  <td data-label="四位回避率">
                    {r.fourth_avoidance_rate ? displayPercent(r.fourth_avoidance_rate) : '—'}
                  </td>
                  <td data-label="每轮成绩明细">
                    <details>
                      <summary>
                        {r.rounds ? `展开 ${r.rounds.length} 轮成绩` : '逐轮明细未收录'}
                      </summary>
                      {r.rounds?.map((s, i) => (
                        <article className="round-score-card" key={i}>
                          <header>
                            <strong>
                              第 {s.round_number} 轮
                              {s.table_number ? ` · ${'ABCD'[s.table_number - 1]} 桌` : ''}
                            </strong>
                            <span>
                              {s.rank === 1
                                ? `${s.tied ? '并列' : ''}当桌最高分`
                                : `${s.tied ? '并列' : ''}第 ${s.rank} 名`}
                            </span>
                          </header>
                          <dl>
                            <div>
                              <dt>终局点数</dt>
                              <dd>{s.raw_points.toLocaleString('zh-CN')} 点</dd>
                            </div>
                            <div>
                              <dt>本轮积分</dt>
                              <dd>
                                <strong>{displayScore(s.score)} 分</strong>
                              </dd>
                            </div>
                            <div>
                              <dt>基础积分</dt>
                              <dd>{displayScore(s.base)} 分</dd>
                            </div>
                            <div>
                              <dt>顺位奖励 · Uma / Oka</dt>
                              <dd>{displayScore(s.bonus)} 分</dd>
                            </div>
                          </dl>
                          <details className="exact-score-note">
                            <summary>查看精确值</summary>
                            <p>
                              本轮 {exactScore(s.score)}；基础 {exactScore(s.base)}；顺位奖励{' '}
                              {exactScore(s.bonus)}。基础积分包含本桌适用的附加分。
                            </p>
                          </details>
                        </article>
                      ))}
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
