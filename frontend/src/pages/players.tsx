import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Plus, Search, RefreshCw, UsersRound, X } from 'lucide-react'
import { api, type Player } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { FormFeedback } from '@/components/form-feedback'

type Page = { count: number; next: string | null; previous: string | null; results: Player[] }
type Action = { mode: 'new' | 'edit' | 'delete' | 'archive' | 'restore'; row?: Player }
export function PlayersPage() {
  const [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [status, setStatus] = useState('active'),
    [page, setPage] = useState(1)
  const [data, setData] = useState<Page | null>(null),
    [loading, setLoading] = useState(true),
    [opening, setOpening] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [revision, setRevision] = useState(0),
    [success, setSuccess] = useState(''),
    [action, setAction] = useState<Action | null>(null)
  const trigger = useRef<HTMLElement | null>(null),
    panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const c = new AbortController()
    setLoading(true)
    setError(null)
    void api<Page>(`/players/?${new URLSearchParams({ page: String(page), search, status })}`, {
      signal: c.signal,
    })
      .then((v) => {
        if (!c.signal.aborted) setData(v)
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e)
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false)
      })
    return () => c.abort()
  }, [page, search, status, revision])
  function close() {
    setAction(null)
    requestAnimationFrame(() =>
      (trigger.current?.isConnected ? trigger.current : panel.current)?.focus(),
    )
  }
  async function open(mode: Action['mode'], id?: number) {
    trigger.current = document.activeElement as HTMLElement
    setError(null)
    setSuccess('')
    setOpening(true)
    try {
      setAction({ mode, row: id ? await api<Player>(`/players/${id}/`) : undefined })
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
    <div className="player-workspace">
      <section className="competition-hero">
        <div>
          <span className="eyebrow">PLAYER DIRECTORY</span>
          <h2>选手管理</h2>
          <p>由雀庄维护参赛档案，选手无需账号或登录。</p>
        </div>
        <Button disabled={opening} onClick={() => void open('new')}>
          <Plus size={17} />
          新增选手
        </Button>
      </section>
      <FormFeedback success={success} error={error} />
      <section ref={panel} tabIndex={-1} className="settings-panel player-list">
        <div className="section-heading">
          <div>
            <h3>选手档案</h3>
            <p>归档不会修改历史名单、成绩或冠军。</p>
          </div>
          <Button variant="ghost" disabled={loading} onClick={() => setRevision((v) => v + 1)}>
            <RefreshCw size={16} />
            刷新列表
          </Button>
        </div>
        <form className="machine-toolbar" onSubmit={submit}>
          <div className="machine-search">
            <Search size={17} />
            <input
              aria-label="搜索选手昵称"
              placeholder="搜索选手昵称"
              value={query}
              maxLength={150}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button type="submit" variant="outline">
            搜索
          </Button>
          <label className="machine-filter">
            选手状态
            <Select
              aria-label="选手状态"
              value={status}
              onValueChange={(value) => {
                setStatus(value)
                setPage(1)
              }}
              options={[
                { value: 'active', label: '有效选手' },
                { value: 'archived', label: '已归档' },
                { value: '', label: '全部选手' },
              ]}
            />
          </label>
        </form>
        {loading ? (
          <p role="status">正在加载选手…</p>
        ) : error ? (
          <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
            重新加载
          </Button>
        ) : !data?.results.length ? (
          <div className="list-empty">
            <UsersRound size={30} />
            <h3>没有匹配的选手</h3>
            <p>可调整筛选或新增选手，保存后即可选择参赛。</p>
          </div>
        ) : (
          <div role="table" aria-label="选手列表">
            <div className="player-row player-row-heading" role="row">
              {['选手昵称', '状态', '赛事引用', '建立时间', '管理操作'].map((x) => (
                <span role="columnheader" key={x}>
                  {x}
                </span>
              ))}
            </div>
            {data.results.map((p) => (
              <div className="player-row" role="row" key={p.id}>
                <div role="cell">
                  <strong>{p.nickname}</strong>
                  <small>选手 #{p.id}</small>
                </div>
                <span role="cell">
                  <Badge variant="outline">{p.is_active === false ? '已归档' : '有效'}</Badge>
                </span>
                <span role="cell">{p.reference_count || 0} 场</span>
                <time role="cell">{new Date(p.created_at).toLocaleDateString('zh-CN')}</time>
                <div role="cell" className="player-actions">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={opening}
                    aria-label={`编辑选手 ${p.nickname}`}
                    onClick={() => void open('edit', p.id)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={opening}
                    aria-label={`${p.is_active === false ? '恢复' : '归档'}选手 ${p.nickname}`}
                    onClick={() => void open(p.is_active === false ? 'restore' : 'archive', p.id)}
                  >
                    {p.is_active === false ? '恢复' : '归档'}
                  </Button>
                  {p.can_delete && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={opening}
                      aria-label={`删除选手 ${p.nickname}`}
                      onClick={() => void open('delete', p.id)}
                    >
                      删除
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {data && !loading && !error && (
          <div className="pagination">
            <span>
              共 {data.count} 位选手 · 第 {page} 页
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
      {action && (
        <PlayerAction
          key={`${action.mode}-${action.row?.id}`}
          action={action}
          close={close}
          saved={(message) => {
            close()
            setSuccess(message)
            setPage(1)
            setRevision((v) => v + 1)
          }}
        />
      )}
    </div>
  )
}

function PlayerAction({
  action,
  close,
  saved,
}: {
  action: Action
  close: () => void
  saved: (message: string) => void
}) {
  const [nickname, setNickname] = useState(action.row?.nickname || ''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null)
  const edit = action.mode === 'new' || action.mode === 'edit'
  const title = {
    new: '新增选手',
    edit: '编辑选手',
    delete: '删除选手',
    archive: '归档选手',
    restore: '恢复选手',
  }[action.mode]
  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (edit && !nickname.trim()) {
      setError(new Error('选手昵称不能为空。'))
      return
    }
    setBusy(true)
    try {
      if (edit) {
        await api(action.row ? `/players/${action.row.id}/` : '/players/', {
          method: action.row ? 'PATCH' : 'POST',
          body: { nickname: nickname.trim() },
        })
      } else {
        await api(
          `/players/${action.row!.id}/${action.mode === 'delete' ? '' : action.mode + '/'}`,
          { method: action.mode === 'delete' ? 'DELETE' : 'POST', body: { confirmed: true } },
        )
      }
      saved(`${title}成功。`)
    } catch (e) {
      setError(e as Error)
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
      <SheetContent className="machine-sheet tournament-sheet" showCloseButton={false}>
        <SheetHeader>
          <span className="eyebrow">PLAYER RECORD</span>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {edit
              ? '仅维护选手业务资料，不创建登录凭据。'
              : `${action.row?.nickname} · 选手 #${action.row?.id}`}
          </SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          size="icon"
          variant="ghost"
          aria-label="关闭选手操作"
          disabled={busy}
          onClick={close}
        >
          <X />
        </Button>
        <form className="account-form machine-form" onSubmit={submit}>
          {edit ? (
            <label>
              选手昵称
              <input
                aria-label="选手昵称"
                autoFocus
                maxLength={80}
                required
                disabled={busy}
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
              />
            </label>
          ) : (
            <div className="confirmation-preview">
              <h3>请确认{title}</h3>
              <p>
                {action.mode === 'delete'
                  ? '此档案尚未被任何赛事引用，将删除选手档案。此操作不可恢复。'
                  : action.mode === 'archive'
                    ? `此选手已被 ${action.row?.reference_count || 0} 场草稿或历史赛事引用。归档后不再进入新赛事有效名单，历史参赛关系、昵称快照与成绩保持不变。`
                    : '恢复后可重新选择参加新赛事，不会修改历史结果。'}
              </p>
            </div>
          )}
          <FormFeedback error={error} />
          {error && (
            <p className="field-hint">请关闭并刷新列表核对最新状态；写操作不会自动重试。</p>
          )}
          <div className="machine-form-footer">
            <Button type="button" variant="outline" disabled={busy} onClick={close}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? '正在提交…' : edit ? '保存选手' : `确认${title}`}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
