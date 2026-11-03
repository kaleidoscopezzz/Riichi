import { useEffect, useState, type FormEvent } from 'react'
import { api, type Player } from '@/services/api'
import { Button } from '@/components/ui/button'
import { FormFeedback } from '@/components/form-feedback'

type Page = { count: number; next: string | null; previous: string | null; results: Player[] }
export function PlayersPage() {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void api<Page>(`/players/?page=${page}&search=${encodeURIComponent(search)}`, {
      signal: controller.signal,
    })
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
  }, [page, search, retry])
  function submit(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setSearch(query.trim())
    setRetry((value) => value + 1)
  }
  return (
    <section className="settings-panel player-list">
      <div className="section-heading">
        <div>
          <span className="eyebrow">REGISTERED PLAYERS</span>
          <h2>已注册选手</h2>
        </div>
        <span>管理员只读查询</span>
      </div>
      <form className="player-search" onSubmit={submit}>
        <label className="sr-only" htmlFor="player-search">
          搜索昵称或用户名
        </label>
        <input
          id="player-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={150}
          placeholder="搜索昵称或用户名"
        />
        <Button type="submit">搜索</Button>
      </form>
      <FormFeedback error={error} />
      {loading ? (
        <p role="status">正在加载选手…</p>
      ) : error ? (
        <Button onClick={() => setRetry((value) => value + 1)}>重新加载</Button>
      ) : !data?.results.length ? (
        <div className="list-empty">
          <h3>没有匹配的选手</h3>
          <p>请调整搜索条件。这里只显示已注册的真实账号档案。</p>
        </div>
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>选手昵称</th>
                  <th>用户名</th>
                  <th>注册时间</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((player) => (
                  <tr key={player.id}>
                    <td>{player.nickname}</td>
                    <td>{player.username}</td>
                    <td>{new Date(player.date_joined).toLocaleString('zh-CN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              共 {data.count} 位选手 · 第 {page} 页
            </span>
            <Button variant="outline" disabled={!data.previous} onClick={() => setPage(page - 1)}>
              上一页
            </Button>
            <Button variant="outline" disabled={!data.next} onClick={() => setPage(page + 1)}>
              下一页
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
