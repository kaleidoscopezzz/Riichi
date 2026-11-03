import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Plus,
  Search,
  Grid2X2,
  Check,
  Wrench,
  CircleSlash,
  ArrowUpRight,
  RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { FormFeedback } from '@/components/form-feedback'
import { MachineEditor, MachineRetirement } from '@/components/machine-editor'
import {
  fetchMachines,
  fetchMachine,
  machineLabels,
  type Machine,
  type MachinePage,
} from '@/services/machines'

export function MachinesPage() {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<MachinePage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [revision, setRevision] = useState(0)
  const [editor, setEditor] = useState<{ machine?: Machine; readOnly?: boolean } | null>(null)
  const [retiring, setRetiring] = useState<Machine | null>(null)
  const [success, setSuccess] = useState('')
  const [opening, setOpening] = useState<number | null>(null)
  const newButton = useRef<HTMLButtonElement>(null)
  const lastAction = useRef<HTMLButtonElement | null>(null)
  const focusPending = useRef(false)
  const listPanel = useRef<HTMLElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void fetchMachines(page, search, status, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value)
      })
      .catch((problem) => {
        if (!controller.signal.aborted) setError(problem)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [page, search, status, revision])
  useEffect(() => {
    if (editor || retiring || loading || !focusPending.current) return
    const frame = requestAnimationFrame(() => {
      const target =
        lastAction.current?.isConnected && !lastAction.current.disabled
          ? lastAction.current
          : newButton.current && !newButton.current.disabled
            ? newButton.current
            : listPanel.current
      target?.focus()
      focusPending.current = false
    })
    return () => cancelAnimationFrame(frame)
  }, [editor, retiring, loading, data])
  function submit(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setSearch(query.trim())
    setRevision((v) => v + 1)
  }
  function close() {
    focusPending.current = true
    setEditor(null)
    setRetiring(null)
  }
  function saved(machine: Machine) {
    close()
    setSuccess(
      machine.status === 'retired'
        ? `设备 ${machine.machine_no} 已退役，历史档案已保留。`
        : `设备 ${machine.machine_no} 已保存。`,
    )
    setRevision((v) => v + 1)
  }
  async function open(
    machine: Machine,
    mode: 'view' | 'edit' | 'retire',
    button: HTMLButtonElement,
  ) {
    lastAction.current = button
    setOpening(machine.id)
    setError(null)
    setSuccess('')
    try {
      const fresh = await fetchMachine(machine.id)
      if (mode === 'retire') setRetiring(fresh)
      else setEditor({ machine: fresh, readOnly: mode === 'view' || fresh.status === 'retired' })
    } catch (problem) {
      setError(problem as Error)
    } finally {
      setOpening(null)
    }
  }
  const full = !!data && data.summary.active >= 4
  return (
    <div className="machine-workspace">
      <section className="machine-overview">
        <div>
          <span className="eyebrow">PHYSICAL RESOURCES / 设备资源</span>
          <h2>每一台设备，都有清晰的归属。</h2>
          <p>维护物理设备台账，为下一场对局做好准备。</p>
        </div>
        <Button
          ref={newButton}
          onClick={(event) => {
            lastAction.current = event.currentTarget
            setEditor({})
            setSuccess('')
          }}
          disabled={loading || !!error || full || opening !== null}
        >
          <Plus size={17} />
          新建设备
        </Button>
      </section>
      <div className="machine-stats">
        {(
          [
            { key: 'active', label: '现役设备', icon: Grid2X2 },
            { key: 'available', label: '当前可用', icon: Check },
            { key: 'maintenance', label: '维护中', icon: Wrench },
            { key: 'disabled', label: '停用', icon: CircleSlash },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <Card className={`machine-stat stat-${key}`} key={key}>
            <div>
              <span>{label}</span>
              <Icon size={18} />
            </div>
            <p>
              {data && !loading && !error ? data.summary[key] : '—'}
              {key === 'active' && <small> / 4 台</small>}
            </p>
            <span>
              {key === 'active'
                ? '维护中与停用设备同样占用容量'
                : key === 'available'
                  ? '设备可用，不代表当前未被占用'
                  : key === 'maintenance'
                    ? '检修完成后可恢复为可用'
                    : '可随时通过编辑恢复为可用'}
            </span>
          </Card>
        ))}
      </div>
      {full && !loading && !error && (
        <div className="capacity-notice" role="status">
          <Grid2X2 size={18} />
          <div>
            <strong>现役容量已满</strong>
            <p>当前已管理 4 台现役设备。退役一台后，可新增替代设备。</p>
          </div>
        </div>
      )}
      <FormFeedback success={success} />
      <section className="settings-panel machine-list" ref={listPanel} tabIndex={-1}>
        <div className="section-heading">
          <div>
            <span className="eyebrow">MACHINE DIRECTORY</span>
            <h2>设备台账</h2>
          </div>
          <Button variant="ghost" onClick={() => setRevision((v) => v + 1)} disabled={loading}>
            <RefreshCw size={15} />
            刷新列表
          </Button>
        </div>
        <form className="machine-toolbar" onSubmit={submit}>
          <div className="machine-search">
            <Search size={17} />
            <label className="sr-only" htmlFor="machine-search">
              搜索设备编号或名称
            </label>
            <input
              id="machine-search"
              placeholder="搜索设备编号或名称"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={100}
            />
          </div>
          <Button type="submit" variant="outline">
            搜索
          </Button>
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
              {Object.entries(machineLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </form>
        <FormFeedback error={error} />
        {loading ? (
          <div className="machine-loading" role="status">
            正在加载设备台账…
          </div>
        ) : error ? (
          <div className="list-empty">
            <h3>暂时无法读取设备</h3>
            <p>请检查网络或重新加载，写操作不会自动重试。</p>
            <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
              重新加载
            </Button>
          </div>
        ) : !data?.results.length ? (
          <div className="machine-empty">
            <Grid2X2 size={32} strokeWidth={1.3} />
            <h3>{search || status ? '没有匹配的设备' : '还没有设备档案'}</h3>
            <p>
              {search || status
                ? '调整编号、名称或状态筛选，查看其他设备。'
                : '点击“新建设备”，登记第一台物理麻将机。'}
            </p>
          </div>
        ) : (
          <div className="machine-rows" role="table" aria-label="设备列表">
            <div className="machine-row machine-row-heading" role="row">
              <span role="columnheader">编号 / 设备名称</span>
              <span role="columnheader">位置</span>
              <span role="columnheader">状态</span>
              <span role="columnheader">更新时间</span>
              <span role="columnheader">管理操作</span>
            </div>
            {data.results.map((machine) => (
              <div className="machine-row" role="row" key={machine.id}>
                <div role="cell" className="machine-identity">
                  <span className="machine-number">{machine.machine_no}</span>
                  <div>
                    <strong>{machine.name}</strong>
                    <small>物理设备 · ID {machine.id}</small>
                  </div>
                </div>
                <span role="cell" className="machine-location">
                  {machine.location || '未填写位置'}
                </span>
                <span role="cell">
                  <Badge variant="outline" className={`machine-status status-${machine.status}`}>
                    {machineLabels[machine.status]}
                  </Badge>
                </span>
                <time role="cell" dateTime={machine.updated_at}>
                  {new Date(machine.updated_at).toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
                <div role="cell" className="machine-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={opening !== null}
                    onClick={(e) => void open(machine, 'view', e.currentTarget)}
                    aria-label={`查看设备 ${machine.machine_no} 详情`}
                  >
                    详情
                    <ArrowUpRight size={13} />
                  </Button>
                  {machine.status !== 'retired' && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={opening !== null}
                        onClick={(e) => void open(machine, 'edit', e.currentTarget)}
                        aria-label={`编辑设备 ${machine.machine_no}`}
                      >
                        编辑
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="retire-action"
                        disabled={opening !== null}
                        onClick={(e) => void open(machine, 'retire', e.currentTarget)}
                        aria-label={`退役设备 ${machine.machine_no}`}
                      >
                        退役
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {data && !loading && !error && (
          <div className="pagination">
            <span>
              共 {data.count} 条记录 · 第 {page} 页
            </span>
            <Button
              variant="outline"
              disabled={!data.previous}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </Button>
            <Button variant="outline" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
              下一页
            </Button>
          </div>
        )}
        <p className="machine-list-note">
          已退役设备保留历史档案。设备编号用于识别，设备可用状态与赛事占用无关。
        </p>
      </section>
      {editor && (
        <MachineEditor key={editor.machine?.id || 'new'} {...editor} close={close} saved={saved} />
      )}
      {retiring && <MachineRetirement machine={retiring} close={close} saved={saved} />}
    </div>
  )
}
