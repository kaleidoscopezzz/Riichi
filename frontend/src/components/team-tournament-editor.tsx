import { useState, type FormEvent } from 'react'
import { Plus, Trash2, ArrowUp, ArrowDown, X } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import { PlayerPicker } from './player-picker'
import { ApiError } from '@/services/api'
import { fetchTeam, saveTeam, type TeamTournament, type TeamInput } from '@/services/teams'
import { validCustomOka, previewOka, type Participant } from '@/services/tournaments'

type DraftTeam = { key: number; id?: number; name: string; members: Participant[]; captain: string }
const initialPositions = ['先锋', '次峰', '中间', '副将', '大将']
export function TeamTournamentEditor({
  tournament,
  close,
  saved,
}: {
  tournament?: TeamTournament
  close: () => void
  saved: (t: TeamTournament) => void
}) {
  const [base, setBase] = useState(tournament)
  const [name, setName] = useState(tournament?.name ?? '')
  const [description, setDescription] = useState(tournament?.description ?? '')
  const [starting, setStarting] = useState(String(tournament?.starting_points ?? 25000))
  const [returning, setReturning] = useState(String(tournament?.return_points ?? 30000))
  const [uma, setUma] = useState(tournament?.uma ?? ['30', '10', '-10', '-30'])
  const [okaMode, setOkaMode] = useState(tournament?.oka_override != null ? 'custom' : 'derived')
  const [oka, setOka] = useState(tournament?.oka_override ?? '0')
  const [mode, setMode] = useState<'free' | 'positions'>(
    tournament?.team_settings.schedule_mode ?? 'free',
  )
  const [total, setTotal] = useState(String(tournament?.team_settings.total_matches ?? 10))
  const [games, setGames] = useState(String(tournament?.team_settings.games_per_position ?? 2))
  const [cycles, setCycles] = useState(String(tournament?.team_settings.cycles ?? 1))
  const [positions, setPositions] = useState(
    tournament?.team_settings.positions ?? initialPositions,
  )
  const [pairing, setPairing] = useState<'team_balanced_v1' | 'team_manual_v1'>(
    tournament?.pairing_strategy === 'team_manual_v1' ? 'team_manual_v1' : 'team_balanced_v1',
  )
  const loadTeams = (t?: TeamTournament): DraftTeam[] =>
    t?.teams.map((team) => ({
      key: team.id,
      id: team.id,
      name: team.name,
      members: team.members.map((m) => ({
        id: m.participant_id,
        player_id: m.player_id,
        display_name: m.display_name,
        display_name_snapshot: '',
        is_active: m.is_active,
      })),
      captain: String(team.members.find((m) => m.is_captain)?.player_id ?? ''),
    })) ??
    Array.from({ length: 4 }, (_, i) => ({ key: -i - 1, name: '', members: [], captain: '' }))
  const [teams, setTeams] = useState<DraftTeam[]>(() => loadTeams(tournament))
  const [newKey, setNewKey] = useState(-5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [stale, setStale] = useState(false)
  const [notice, setNotice] = useState('')
  const locked = base?.status !== undefined && base.status !== 'draft'
  const integer = (value: string, max: number) =>
    /^[0-9]+$/.test(value) && BigInt(value) > 0n && BigInt(value) <= BigInt(max)
  const memberCount = teams.reduce((n, team) => n + team.members.length, 0)
  function changeTeam(key: number, values: Partial<DraftTeam>) {
    setTeams((rows) => rows.map((row) => (row.key === key ? { ...row, ...values } : row)))
  }
  async function reload() {
    if (!base) return
    setBusy(true)
    setError(null)
    try {
      const t = await fetchTeam(base.id)
      setBase(t)
      setName(t.name)
      setDescription(t.description)
      setStarting(String(t.starting_points))
      setReturning(String(t.return_points))
      setUma(t.uma)
      setOkaMode(t.oka_override == null ? 'derived' : 'custom')
      setOka(t.oka_override ?? '0')
      setMode(t.team_settings.schedule_mode)
      setTotal(String(t.team_settings.total_matches ?? 10))
      setGames(String(t.team_settings.games_per_position))
      setCycles(String(t.team_settings.cycles))
      setPositions(t.team_settings.positions)
      setPairing(t.pairing_strategy === 'team_manual_v1' ? 'team_manual_v1' : 'team_balanced_v1')
      setTeams(loadTeams(t))
      setStale(false)
      setNotice('已载入最新团队草稿，请重新核对。')
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice('')
    if (
      !name.trim() ||
      !integer(starting, 2147483647) ||
      !integer(returning, 2147483647) ||
      (mode === 'free' && !integer(total, 10000)) ||
      (mode === 'positions' &&
        (!integer(games, 100) ||
          !integer(cycles, 100) ||
          !positions.length ||
          positions.some((p) => !p.trim()) ||
          new Set(positions).size !== positions.length)) ||
      (okaMode === 'custom' && !validCustomOka(oka))
    ) {
      setError(new Error('请填写完整名称及有效的整数配置，位置名称须不重复，Oka须为非负精确小数。'))
      return
    }
    const allPlayers = teams.flatMap((team) => team.members.map((p) => p.player_id))
    if (
      teams.some((team) => !team.name.trim()) ||
      new Set(teams.map((team) => team.name.trim())).size !== teams.length ||
      new Set(allPlayers).size !== allPlayers.length ||
      memberCount > 4096
    ) {
      setError(new Error('请填写不重复的队名；同一选手在本赛事中只能属于一队。'))
      return
    }
    setBusy(true)
    try {
      const body: TeamInput = {
        competition_type: 'team',
        name: name.trim(),
        description,
        starting_points: Number(starting),
        return_points: Number(returning),
        uma,
        oka_override: okaMode === 'custom' ? oka : null,
        pairing_strategy: pairing,
        schedule_mode: mode,
        total_matches: mode === 'free' ? Number(total) : null,
        positions,
        games_per_position: Number(games),
        cycles: Number(cycles),
        teams: teams.map((team) => ({
          ...(team.id ? { id: team.id } : {}),
          name: team.name.trim(),
          player_ids: team.members.map((p) => p.player_id),
          captain_player_id: team.captain ? Number(team.captain) : null,
        })),
        ...(base ? { revision: base.revision } : {}),
      }
      saved(await saveTeam(body, base?.id))
    } catch (e) {
      setError(e as Error)
      setStale(e instanceof ApiError && e.code === 'stale_tournament')
    } finally {
      setBusy(false)
    }
  }
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
          <span className="eyebrow">TEAM TOURNAMENT</span>
          <SheetTitle>{base ? '编辑团队赛草稿' : '创建团队赛'}</SheetTitle>
          <SheetDescription>队伍与成员人数可配置，每桌四支不同队伍各一人。</SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          variant="ghost"
          size="icon"
          disabled={busy}
          aria-label="关闭团队赛表单"
          onClick={close}
        >
          <X />
        </Button>
        <form className="machine-form tournament-form" onSubmit={(e) => void submit(e)}>
          <fieldset disabled={busy || locked}>
            <section>
              <h3>赛事与计分</h3>
              <label>
                赛事名称
                <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
              </label>
              <label>
                赛事说明
                <textarea
                  value={description}
                  maxLength={3000}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <div className="team-form-grid">
                <label>
                  开局点数
                  <input
                    inputMode="numeric"
                    value={starting}
                    onChange={(e) => setStarting(e.target.value)}
                  />
                </label>
                <label>
                  返还原点
                  <input
                    inputMode="numeric"
                    value={returning}
                    onChange={(e) => setReturning(e.target.value)}
                  />
                </label>
              </div>
              <div className="uma-fields">
                {uma.map((v, i) => (
                  <label key={i}>
                    Uma · 第{i + 1}名
                    <input
                      value={v}
                      onChange={(e) =>
                        setUma((rows) => rows.map((old, j) => (j === i ? e.target.value : old)))
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                头名赏设置
                <Select
                  aria-label="团队头名赏设置"
                  value={okaMode}
                  onValueChange={setOkaMode}
                  options={[
                    { value: 'derived', label: '自动推导' },
                    { value: 'custom', label: '自定义（可为 0）' },
                  ]}
                />
              </label>
              {okaMode === 'custom' && (
                <label>
                  头名赏 Oka
                  <input value={oka} maxLength={64} onChange={(e) => setOka(e.target.value)} />
                </label>
              )}
              <p className="field-note">
                生效头名赏：{okaMode === 'derived' ? previewOka(starting, returning) : oka}
                。团队积分为已确认队员积分的精确总和。
              </p>
            </section>
            <section>
              <h3>赛程方式</h3>
              <label>
                赛程模式
                <Select
                  aria-label="团队赛程模式"
                  value={mode}
                  onValueChange={(value) => setMode(value as 'free' | 'positions')}
                  options={[
                    { value: 'free', label: '按整体场次' },
                    { value: 'positions', label: '固定位置依次循环' },
                  ]}
                />
              </label>
              <label>
                队伍编排
                <Select
                  aria-label="团队队伍编排"
                  value={pairing}
                  onValueChange={(value) => setPairing(value as typeof pairing)}
                  options={[
                    { value: 'team_balanced_v1', label: '均衡随机编排' },
                    { value: 'team_manual_v1', label: '手动安排四队' },
                  ]}
                />
              </label>
              {mode === 'free' ? (
                <label>
                  总桌场次
                  <input
                aria-label="总桌场次"
                    inputMode="numeric"
                    value={total}
                    onChange={(e) => setTotal(e.target.value)}
                  />
                  <small>一张桌的一个半庄为一桌场；编排须各队等场。</small>
                </label>
              ) : (
                <>
                  <div className="team-form-grid">
                    <label>
                      每位置每队场数
                      <input
                        inputMode="numeric"
                        value={games}
                        onChange={(e) => setGames(e.target.value)}
                      />
                    </label>
                    <label>
                      循环次数
                      <input
                        inputMode="numeric"
                        value={cycles}
                        onChange={(e) => setCycles(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="team-position-editor">
                    {positions.map((p, i) => (
                      <div key={i}>
                        <label>
                          位置 {i + 1}
                          <input
                            value={p}
                            maxLength={80}
                            onChange={(e) =>
                              setPositions((rows) =>
                                rows.map((v, j) => (i === j ? e.target.value : v)),
                              )
                            }
                          />
                        </label>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`上移位置 ${i + 1}`}
                          disabled={i === 0}
                          onClick={() =>
                            setPositions((rows) => {
                              const copy = [...rows]
                              ;[copy[i - 1], copy[i]] = [copy[i], copy[i - 1]]
                              return copy
                            })
                          }
                        >
                          <ArrowUp size={16} />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`下移位置 ${i + 1}`}
                          disabled={i === positions.length - 1}
                          onClick={() =>
                            setPositions((rows) => {
                              const copy = [...rows]
                              ;[copy[i + 1], copy[i]] = [copy[i], copy[i + 1]]
                              return copy
                            })
                          }
                        >
                          <ArrowDown size={16} />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`移除位置 ${i + 1}`}
                          disabled={positions.length === 1}
                          onClick={() => setPositions((rows) => rows.filter((_, j) => i !== j))}
                        >
                          <Trash2 size={16} />
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={positions.length >= 32}
                    onClick={() => setPositions((rows) => [...rows, ''])}
                  >
                    添加位置
                  </Button>
                  <p className="field-note">
                    按位置顺序完成本阶段所有场次后再进入下个位置，完成整套后开始下个循环。不成立的分桌组合会提示修改，配置不会自动变化。
                  </p>
                </>
              )}
            </section>
            <section>
              <div className="competition-section-heading">
                <h3>队伍与成员</h3>
                <span>
                  {teams.length} 支队伍 · {memberCount} 名成员
                </span>
              </div>
              <div className="team-roster-editor">
                {teams.map((team, i) => (
                  <article key={team.key} aria-label={`第 ${i + 1} 支队伍`}>
                    <div className="competition-section-heading">
                      <strong>第 {i + 1} 支队伍</strong>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`移除队伍 ${i + 1}`}
                        onClick={() => setTeams((rows) => rows.filter((r) => r.key !== team.key))}
                      >
                        移除队伍
                      </Button>
                    </div>
                    <label>
                      队伍名称
                      <input
                        aria-label={`队伍 ${i + 1} 名称`}
                        value={team.name}
                        maxLength={80}
                        onChange={(e) => changeTeam(team.key, { name: e.target.value })}
                      />
                    </label>
                    <PlayerPicker
                      selected={team.members}
                      change={(members) =>
                        changeTeam(team.key, {
                          members,
                          captain: members.some((p) => String(p.player_id) === team.captain)
                            ? team.captain
                            : '',
                        })
                      }
                      disabled={busy || locked}
                      maxSelected={4096}
                      blockedPlayerIds={teams
                        .filter((other) => other.key !== team.key)
                        .flatMap((other) => other.members.map((p) => p.player_id))}
                      label={`搜索队伍 ${i + 1} 成员`}
                      hintText="人数可配置；同一选手只能属于本赛事的一支队伍，出场名单由队长指定。"
                    />
                    <label>
                      队长标记（可选）
                      <Select
                        aria-label={`队伍 ${i + 1} 队长`}
                        value={team.captain}
                        onValueChange={(value) => changeTeam(team.key, { captain: value })}
                        options={[
                          { value: '', label: '不设置队长标记' },
                          ...team.members.map((p) => ({
                            value: p.player_id,
                            label: p.display_name,
                          })),
                        ]}
                      />
                    </label>
                  </article>
                ))}
              </div>
              <Button
                type="button"
                variant="outline"
                disabled={teams.length >= 256}
                onClick={() => {
                  setTeams((rows) => [...rows, { key: newKey, name: '', members: [], captain: '' }])
                  setNewKey((v) => v - 1)
                }}
              >
                <Plus size={16} />
                添加队伍
              </Button>
            </section>
          </fieldset>
          <FormFeedback error={error} success={notice} />
          {stale && (
            <Button type="button" variant="outline" disabled={busy} onClick={() => void reload()}>
              重新加载最新团队草稿
            </Button>
          )}
          <p className="field-note">保存为草稿；赛程预览、队长出场名单和开场均在团队工作台确认。</p>
          <div className="machine-form-footer">
            <Button type="button" variant="outline" disabled={busy} onClick={close}>
              取消
            </Button>
            <Button type="submit" disabled={busy || locked}>
              {busy ? '正在保存…' : '保存团队草稿'}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
