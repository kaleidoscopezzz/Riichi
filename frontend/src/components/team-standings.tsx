import { displayScore, exactScore, displayPercent } from '@/services/competition'
import type { TeamStanding } from '@/services/teams'

export function TeamStandings({ rows, completed }: { rows: TeamStanding[]; completed: boolean }) {
  return (
    <section className="settings-panel team-standings-panel">
      <div className="competition-section-heading">
        <h3>{completed ? '最终团队排名' : '团队累计榜 · 暂列'}</h3>
        <span>仅采用已确认有效积分</span>
      </div>
      {!rows.length ? (
        <p>尚未登记队伍。</p>
      ) : (
        <div className="team-standings-scroll">
          <table>
            <thead>
              <tr>
                <th>名次</th>
                <th>团队</th>
                <th>累计有效积分</th>
                <th>已确认 / 已计划</th>
                <th>当桌第一 / 第二合计</th>
                <th>队员贡献与场次</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((team) => (
                <tr key={team.team_id}>
                  <td data-label="名次">{team.rank}</td>
                  <th scope="row" data-label="团队">
                    {team.name}
                  </th>
                  <td data-label="累计有效积分">
                    <strong title={exactScore(team.total)}>{displayScore(team.total)} 分</strong>
                  </td>
                  <td data-label="已确认 / 已计划">
                    {team.confirmed_matches} / {team.planned_matches} 场
                  </td>
                  <td data-label="当桌第一 / 第二合计">
                    {team.first_count} / {team.second_count} 次
                  </td>
                  <td data-label="队员贡献与场次">
                    <details>
                      <summary>展开本队贡献</summary>
                      {team.contributions.map((member) => (
                        <article className="team-contribution" key={member.participant_id}>
                          <strong>{member.display_name}</strong>
                          <p>
                            {member.confirmed_rounds
                              ? `${displayScore(member.total)} 分 · 实际确认 ${member.confirmed_rounds} 场`
                              : '尚无确认出场 · 贡献 0.00 分'}
                          </p>
                          <small>
                            四位回避率{' '}
                            {member.fourth_avoidance_rate
                              ? displayPercent(member.fourth_avoidance_rate)
                              : '—'}{' '}
                            · 当桌第一 {member.first_count} 次
                          </small>
                        </article>
                      ))}
                    </details>
                    <details>
                      <summary>查看 {team.matches.length} 场记录</summary>
                      {team.matches.map((m) => (
                        <article className="team-contribution" key={m.table_id}>
                          <strong>
                            第 {m.match_number} 场 · {m.display_name}
                          </strong>
                          {m.position_label && (
                            <p>
                              第 {m.cycle} 循环 · {m.position_label}
                            </p>
                          )}
                          <p>
                            终局 {m.raw_points.toLocaleString('zh-CN')} 点 · {displayScore(m.score)}{' '}
                            分
                          </p>
                          <details>
                            <summary>查看精确值</summary>
                            <p>
                              基础 {exactScore(m.base)}，顺位奖励 {exactScore(m.bonus)}，本场{' '}
                              {exactScore(m.score)}
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
