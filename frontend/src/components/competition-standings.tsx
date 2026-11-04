import { displayScore, exactScore, type Standing } from '@/services/competition'

export function Standings({ rows, completed }: { rows: Standing[]; completed: boolean }) {
  return (
    <section className="settings-panel standings-panel">
      <div className="competition-section-heading">
        <div>
          <span className="eyebrow">STANDINGS</span>
          <h3>{completed ? '最终排名' : '实时累计榜 · 暂列'}</h3>
        </div>
        <span>仅计入已确认成绩</span>
      </div>
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
                <th>已确认</th>
                <th>第一 / 第二</th>
                <th>逐轮成绩档案</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.participant_id}>
                  <td>{r.rank}</td>
                  <th scope="row">{r.display_name}</th>
                  <td>
                    <strong>{displayScore(r.total)}</strong>
                    <small>精确 {exactScore(r.total)}</small>
                  </td>
                  <td>{r.confirmed_rounds} 轮</td>
                  <td>
                    {r.first_count} / {r.second_count}
                  </td>
                  <td>
                    <details>
                      <summary>查看 {r.rounds.length} 轮</summary>
                      {r.rounds.map((s, i) => (
                        <p key={i}>
                          第{s.round_number}轮 · {s.raw_points} 点 · {s.tied ? '并列' : ''}第
                          {s.rank}名 · {displayScore(s.score)} 分（精确 {exactScore(s.score)}；基础{' '}
                          {exactScore(s.base)}，奖励 {exactScore(s.bonus)}）
                        </p>
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
