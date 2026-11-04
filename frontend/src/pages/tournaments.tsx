import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Flag, Plus, RefreshCw, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FormFeedback } from '@/components/form-feedback'
import { TournamentDetail, TournamentEditor } from '@/components/tournament-editor'
import {
  fetchTournament,
  fetchTournaments,
  type Page,
  type Tournament,
} from '@/services/tournaments'

export function TournamentsPage() {
  const [data, setData] = useState<Page<Tournament> | null>(null)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [success, setSuccess] = useState('')
  const [revision, setRevision] = useState(0)
  const [modal, setModal] = useState<{ mode: 'edit' | 'view' | 'start'; row?: Tournament } | null>(
    null,
  )
  const [opening, setOpening] = useState(false)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const list = useRef<HTMLElement>(null)
  const focusPending = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void fetchTournaments(page, search, status, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value)
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [page, search, status, revision])
  useEffect(() => {
    if (modal || loading || !focusPending.current) return
    const frame = requestAnimationFrame(() => {
      ;(trigger.current?.isConnected ? trigger.current : list.current)?.focus()
      focusPending.current = false
    })
    return () => cancelAnimationFrame(frame)
  }, [modal, loading])
  function close() {
    setModal(null)
    focusPending.current = true
  }
  function saved(row: Tournament) {
    close()
    setSuccess(
      row.status === 'started'
        ? `“${row.name}”已启动，规则与名单已冻结。`
        : `“${row.name}”草稿已保存。`,
    )
    setRevision((v) => v + 1)
  }
  async function open(id: number, mode: 'view' | 'start') {
    setOpening(true)
    setError(null)
    try {
      setModal({ mode, row: await fetchTournament(id) })
    } catch (e) {
      setError(e as Error)
    } finally {
      setOpening(false)
    }
  }
  function submit(e: FormEvent) {
    e.preventDefault()
    setSearch(query.trim())
    setPage(1)
    setRevision((v) => v + 1)
  }
  return (
    <div className="tournament-workspace">
      <section className="tournament-hero">
        <div>
          <span className="eyebrow">INDIVIDUAL TOURNAMENTS</span>
          <h2>从一份规则，开启一场赛事。</h2>
          <p>独立配置每场个人赛，确认选手与规则后启动。</p>
        </div>
        <Button
          onClick={(e) => {
            trigger.current = e.currentTarget
            setModal({ mode: 'edit' })
            setSuccess('')
          }}
        >
          <Plus size={17} />
          创建赛事
        </Button>
      </section>
      <div className="tournament-boundary">
        <Flag size={20} />
        <p>启动后选桌、录入成绩并逐轮重排，完成指定轮次后决出冠军。</p>
      </div>
      <FormFeedback success={success} />
      <section className="settings-panel tournament-list" ref={list} tabIndex={-1}>
        <div className="section-heading">
          <div>
            <span className="eyebrow">TOURNAMENT DIRECTORY</span>
            <h2>赛事档案</h2>
          </div>
          <Button variant="ghost" disabled={loading} onClick={() => setRevision((v) => v + 1)}>
            <RefreshCw size={15} />
            刷新列表
          </Button>
        </div>
        <form className="machine-toolbar" onSubmit={submit}>
          <div className="machine-search">
            <Search size={17} />
            <input
              aria-label="搜索赛事名称"
              placeholder="搜索赛事名称"
              value={query}
              maxLength={120}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button variant="outline">搜索</Button>
          <label className="machine-filter">
            状态筛选
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setPage(1)
              }}
            >
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="started">已启动</option>
              <option value="completed">已完赛</option>
            </select>
          </label>
        </form>
        <FormFeedback error={error} />
        {loading ? (
          <div className="machine-loading" role="status">
            正在加载赛事档案…
          </div>
        ) : error ? (
          <div className="list-empty">
            <h3>暂时无法读取赛事</h3>
            <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
              重新加载
            </Button>
          </div>
        ) : !data?.results.length ? (
          <div className="machine-empty">
            <Flag size={34} strokeWidth={1.3} />
            <h3>{search || status ? '没有匹配的赛事' : '第一场赛事，从这里开始'}</h3>
            <p>
              {search || status
                ? '调整搜索或筛选条件。'
                : '创建草稿，邀请真实选手，配置属于这场赛事的规则。'}
            </p>
          </div>
        ) : (
          <div className="tournament-rows" role="table" aria-label="赛事列表">
            <div className="tournament-row tournament-row-heading" role="row">
              {['赛事名称', '状态', '参赛人数', '总轮数', '创建时间', '操作'].map((v) => (
                <span role="columnheader" key={v}>
                  {v}
                </span>
              ))}
            </div>
            {data.results.map((row) => (
              <div className="tournament-row" role="row" key={row.id}>
                <div role="cell">
                  <strong>{row.name}</strong>
                  <small>个人赛 · ID {row.id}</small>
                </div>
                <span role="cell">
                  <Badge variant="outline" className={`tournament-status ${row.status}`}>
                    {row.status === 'draft' ? '草稿' : row.status === 'completed' ? '已完赛' : '已启动'}
                  </Badge>
                </span>
                <span role="cell">{row.participant_count} 人</span>
                <span role="cell">{row.round_count} 轮</span>
                <time role="cell">{new Date(row.created_at).toLocaleDateString('zh-CN')}</time>
                <div role="cell">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={opening}
                    aria-label={`查看赛事 ${row.name}`}
                    onClick={(e) => {
                      trigger.current = e.currentTarget
                      void open(row.id, 'view')
                    }}
                  >
                    查看详情
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        {data && !loading && !error && (
          <div className="pagination">
            <span>
              共 {data.count} 场 · 第 {page} 页
            </span>
            <Button
              variant="outline"
              disabled={!data.previous}
              onClick={() => setPage((v) => v - 1)}
            >
              上一页
            </Button>
            <Button variant="outline" disabled={!data.next} onClick={() => setPage((v) => v + 1)}>
              下一页
            </Button>
          </div>
        )}
      </section>
      {modal?.mode === 'edit' && (
        <TournamentEditor
          key={modal.row?.id || 'new'}
          tournament={modal.row}
          close={close}
          saved={saved}
        />
      )}{' '}
      {modal && modal.mode !== 'edit' && modal.row && (
        <TournamentDetail
          key={`${modal.row.id}-${modal.mode}`}
          row={modal.row}
          confirm={modal.mode === 'start'}
          close={close}
          saved={saved}
          edit={() => setModal({ mode: 'edit', row: modal.row })}
          prepareStart={() => void open(modal.row!.id, 'start')}
        />
      )}
    </div>
  )
}
