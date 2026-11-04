import { useEffect, useState, type FormEvent } from 'react'
import { api, type Player } from '@/services/api'
import { useAuth } from '@/components/auth-context'
import { Button } from '@/components/ui/button'
import { FormFeedback } from '@/components/form-feedback'

export function ProfilePage() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<Player | null>(null)
  const [nickname, setNickname] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [success, setSuccess] = useState('')
  async function load() {
    setLoading(true)
    setError(null)
    try {
      const value = await api<Player>('/players/me/')
      setProfile(value)
      setNickname(value.nickname)
    } catch (problem) {
      setError(problem as Error)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    void load()
  }, [])
  async function save(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSuccess('')
    if (!nickname.trim()) {
      setError(new Error('管理员显示名称不能为空。'))
      return
    }
    setBusy(true)
    try {
      setProfile(
        await api<Player>('/players/me/', { method: 'PATCH', body: { nickname: nickname.trim() } }),
      )
      setNickname(nickname.trim())
      setSuccess('管理员显示名称已保存。')
    } catch (problem) {
      setError(problem as Error)
    } finally {
      setBusy(false)
    }
  }
  if (loading) return <p role="status">正在加载个人资料…</p>
  return (
    <section className="settings-panel profile-panel">
      <span className="eyebrow">ADMINISTRATOR PROFILE</span>
      <h2>管理员资料</h2>
      <p>此处维护后台显示名称；比赛选手请在选手管理中维护。</p>
      <dl className="system-info">
        <div>
          <dt>登录用户名</dt>
          <dd>{user?.username}</dd>
        </div>
        <div>
          <dt>账号权限</dt>
          <dd>{user?.is_staff ? '管理员' : '普通用户'}</dd>
        </div>
        <div>
          <dt>注册时间</dt>
          <dd>{user && new Date(user.date_joined).toLocaleString('zh-CN')}</dd>
        </div>
      </dl>
      <FormFeedback error={error} success={success} />
      {profile ? (
        <form className="account-form" onSubmit={save}>
          <label>
            显示名称
            <input
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              maxLength={80}
              required
              disabled={busy}
            />
          </label>
          <Button type="submit" disabled={busy}>
            {busy ? '正在保存…' : '保存显示名称'}
          </Button>
        </form>
      ) : (
        <Button onClick={() => void load()}>重新加载</Button>
      )}
    </section>
  )
}
