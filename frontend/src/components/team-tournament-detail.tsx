import { Link } from 'react-router-dom'
import { X, Users } from 'lucide-react'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import type { TeamTournament } from '@/services/teams'

export function TeamTournamentDetail({
  row,
  close,
  edit,
}: {
  row: TeamTournament
  close: () => void
  edit: () => void
}) {
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <SheetContent
        className="machine-sheet tournament-sheet competition-sheet"
        showCloseButton={false}
      >
        <SheetHeader>
          <span className="eyebrow">TEAM TOURNAMENT DOSSIER</span>
          <SheetTitle>团队赛详情</SheetTitle>
          <SheetDescription>队伍、成员和出场赛程。</SheetDescription>
        </SheetHeader>
        <Button
          variant="ghost"
          size="icon"
          className="machine-sheet-close"
          aria-label="关闭团队详情"
          onClick={close}
        >
          <X />
        </Button>
        <div className="tournament-detail">
          <Badge variant="outline">
            {row.status === 'draft' ? '团队草稿' : row.status === 'completed' ? '已完赛' : '进行中'}
          </Badge>
          <h2>{row.name}</h2>
          <p>{row.description || '未填写赛事说明'}</p>
          <p>
            {row.teams.length} 支队伍 · {row.participant_count} 名成员
          </p>
          <p>
            {row.team_settings.schedule_mode === 'free'
              ? `自由赛程 ${row.team_settings.total_matches} 总桌场次`
              : `${row.team_settings.positions.join(' → ')}，每位置每队${row.team_settings.games_per_position}场，${row.team_settings.cycles}循环`}
          </p>
          <p>
            开局 {row.starting_points} 点 · 返还 {row.return_points} 点 · Oka {row.oka} · Uma{' '}
            {row.uma.join(' / ')}
          </p>
          <div className="team-roster-grid">
            {row.teams.map((team) => (
              <article key={team.id}>
                <h3>{team.name}</h3>
                <p>
                  {team.members
                    .map((m) => `${m.display_name}${m.is_captain ? '（队长）' : ''}`)
                    .join('、') || '尚未登记成员'}
                </p>
              </article>
            ))}
          </div>
          <p>队长指定出场人员，管理员在团队工作台录入和确认；团队积分按已确认队员积分精确求和。</p>
          <div className="machine-form-footer">
            <Button variant="outline" onClick={close}>
              关闭
            </Button>
            {row.status === 'draft' && (
              <Button variant="outline" onClick={edit}>
                编辑团队草稿
              </Button>
            )}
            <Button asChild>
              <Link to={`/tournaments/${row.id}/team`}>
                <Users size={16} />
                进入团队赛工作台
              </Link>
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
