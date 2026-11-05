import { useEffect, useId, useRef, useState } from 'react'
import { Popover } from 'radix-ui'
import { Check, Search, X } from 'lucide-react'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { findPlayers, type Participant } from '@/services/tournaments'
import type { Player } from '@/services/api'

// Multi-select combobox: focus stays in the input, while Radix owns collision
// avoidance and the portal/dismissal layer inside the tournament Sheet.
export function PlayerPicker({
  selected,
  change,
  disabled,
}: {
  selected: Participant[]
  change: (value: Participant[]) => void
  disabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [composing, setComposing] = useState(false)
  const composition = useRef(false)
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [rows, setRows] = useState<Player[]>([])
  const [next, setNext] = useState(false)
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [active, setActive] = useState(-1)
  const input = useRef<HTMLInputElement>(null)
  const anchor = useRef<HTMLDivElement>(null)
  const list = useId()
  const hint = useId()
  const isSelected = (id: number) => selected.some((p) => p.player_id === id)
  const unavailable = (p: Player) => !p.is_active || isSelected(p.id) || selected.length >= 16

  useEffect(() => {
    if (!open || disabled || composing) return
    const controller = new AbortController()
    // Guard even transports/test doubles which don't honor AbortSignal.
    let current = true
    setLoading(true)
    setError('')
    if (page === 1) {
      setRows([])
      setNext(false)
      setCount(0)
      setActive(-1)
    }
    const timer = window.setTimeout(
      () => {
        void findPlayers(page, query.trim(), controller.signal)
          .then((data) => {
            if (!current) return
            const eligible = data.results.filter((p) => p.is_active)
            setRows((previous) =>
              Array.from(
                new Map(
                  [...(page === 1 ? [] : previous), ...eligible].map((p) => [p.id, p]),
                ).values(),
              ),
            )
            setNext(Boolean(data.next))
            setCount(data.count)
          })
          .catch(() => {
            if (current) setError('选手查询失败，请检查网络后重试。')
          })
          .finally(() => {
            if (current) setLoading(false)
          })
      },
      page === 1 && query.trim() ? 250 : 0,
    )
    return () => {
      current = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [open, disabled, query, composing, page, retry])

  useEffect(() => {
    if (active >= 0)
      document.getElementById(`${list}-${rows[active]?.id}`)?.scrollIntoView({ block: 'nearest' })
  }, [active, list, rows])

  function choose(player: Player) {
    if (disabled || unavailable(player) || composition.current) return
    change([
      ...selected,
      {
        id: 0,
        player_id: player.id,
        display_name: player.nickname,
        username: player.username || '',
        is_active: true,
        display_name_snapshot: '',
      },
    ])
    setQuery('')
    setPage(1)
    setActive(-1)
    setOpen(true)
    input.current?.focus()
  }

  return (
    <section className="participant-picker" aria-label="选择参赛选手">
      <div className="tournament-section-heading">
        <h3>参赛名单</h3>
        <Badge variant="outline">已选 {selected.length} / 16 人</Badge>
      </div>
      <p className="field-hint">
        草稿可暂留空；启动需要 4、8、12 或 16 人。由雀庄管理员维护有效选手。
      </p>
      <div className="selected-players" aria-label="已选人员">
        {selected.length ? (
          selected.map((p) => (
            <button
              type="button"
              key={p.player_id}
              disabled={disabled}
              aria-label={`移除 ${p.display_name}（选手 #${p.player_id}）`}
              onClick={() => change(selected.filter((v) => v.player_id !== p.player_id))}
            >
              <span>{p.display_name}</span>
              <X size={13} aria-hidden="true" />
            </button>
          ))
        ) : (
          <span className="field-hint">尚未选择选手</span>
        )}
      </div>
      <Popover.Root open={open && !disabled} onOpenChange={setOpen}>
        <Popover.Anchor asChild>
          <div ref={anchor} className="machine-search player-combobox-search">
            <Search size={16} aria-hidden="true" />
            <input
              ref={input}
              role="combobox"
              aria-label="搜索参赛选手"
              aria-expanded={open && !disabled}
              aria-controls={list}
              aria-autocomplete="list"
              aria-haspopup="listbox"
              aria-describedby={hint}
              aria-activedescendant={
                open && !disabled && !composing && active >= 0 && rows[active]
                  ? `${list}-${rows[active].id}`
                  : undefined
              }
              placeholder="输入昵称，实时查找选手"
              autoComplete="off"
              maxLength={150}
              disabled={disabled}
              value={query}
              onFocus={() => setOpen(true)}
              onChange={(e) => {
                setQuery(e.target.value)
                setPage(1)
                setActive(-1)
                setOpen(true)
              }}
              onCompositionStart={() => {
                composition.current = true
                setComposing(true)
              }}
              onCompositionEnd={(e) => {
                composition.current = false
                setComposing(false)
                setQuery(e.currentTarget.value)
                setPage(1)
              }}
              onKeyDown={(e) => {
                if (composition.current || e.nativeEvent.isComposing || e.keyCode === 229) return
                if (e.key === 'Escape' && open) {
                  e.preventDefault()
                  e.stopPropagation()
                  setOpen(false)
                  setActive(-1)
                } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                  e.preventDefault()
                  setOpen(true)
                  const direction = e.key === 'ArrowDown' ? 1 : -1
                  let index = active < 0 ? (direction === 1 ? -1 : rows.length) : active
                  for (let step = 0; step < rows.length; step++) {
                    index = (index + direction + rows.length) % rows.length
                    if (!unavailable(rows[index])) {
                      setActive(index)
                      break
                    }
                  }
                } else if (e.key === 'Enter') {
                  // Enter in a search field never submits the surrounding draft.
                  e.preventDefault()
                  if (open && active >= 0 && !loading) choose(rows[active])
                  else setOpen(true)
                }
              }}
            />
          </div>
        </Popover.Anchor>
        <Popover.Portal>
          <Popover.Content
            className="player-combobox-popup"
            sideOffset={8}
            collisionPadding={12}
            updatePositionStrategy="always"
            align="start"
            aria-label="参赛选手联想"
            onOpenAutoFocus={(e) => e.preventDefault()}
            onCloseAutoFocus={(e) => e.preventDefault()}
            onInteractOutside={(e) => {
              if (anchor.current?.contains(e.target as Node)) e.preventDefault()
            }}
            onEscapeKeyDown={(e) => {
              e.preventDefault()
              setOpen(false)
              input.current?.focus()
            }}
          >
            <div
              id={list}
              role="listbox"
              aria-label="有效参赛选手"
              aria-multiselectable="true"
              aria-busy={loading || composing}
              className="player-combobox-options"
            >
              {!composing &&
                rows.map((p, index) => (
                  <div
                    role="option"
                    key={p.id}
                    id={`${list}-${p.id}`}
                    aria-selected={isSelected(p.id)}
                    aria-disabled={disabled || unavailable(p)}
                    className="player-combobox-option"
                    data-active={active === index}
                    onMouseDown={(e) => e.preventDefault()}
                    onPointerMove={() => {
                      if (!unavailable(p)) setActive(index)
                    }}
                    onClick={() => choose(p)}
                  >
                    <span>
                      <strong>{p.nickname}</strong>
                      <small>选手 #{p.id}</small>
                    </span>
                    {isSelected(p.id) ? (
                      <span className="player-combobox-selected">
                        <Check size={16} />
                        已选
                      </span>
                    ) : (
                      <span aria-hidden="true">+</span>
                    )}
                  </div>
                ))}
            </div>
            {(loading || composing) && (
              <p role="status">{composing ? '正在输入昵称…' : '正在加载有效选手…'}</p>
            )}
            {error && (
              <div className="player-combobox-feedback">
                <p role="alert">{error}</p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setRetry((v) => v + 1)
                    input.current?.focus()
                  }}
                >
                  重试选手查询
                </Button>
              </div>
            )}
            {!loading && !composing && !error && !rows.length && (
              <p role="status">没有匹配的有效选手。</p>
            )}
            {!composing && !error && rows.length > 0 && (
              <div className="player-combobox-footer">
                <span>
                  已显示 {rows.length} / {count} 人
                </span>
                {next && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={loading}
                    onClick={() => {
                      setPage((v) => v + 1)
                      input.current?.focus()
                    }}
                  >
                    加载更多选手
                  </Button>
                )}
              </div>
            )}
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
      <p id={hint} className="player-combobox-hint" role="status">
        {selected.length >= 16
          ? '已满 16 人，请先移除已选选手后再添加。'
          : '按昵称搜索；使用 ↑ ↓ 和 Enter 选择，Escape 收起。已选人员可点击标签移除。'}
      </p>
    </section>
  )
}
