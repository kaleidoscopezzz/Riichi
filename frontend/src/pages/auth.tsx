import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { Moon, Sun, ArrowRight, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/components/auth-context'
import { useTheme } from '@/components/theme-context'
import { FormFeedback } from '@/components/form-feedback'
import { Button } from '@/components/ui/button'
import { safeReturnPath } from '@/lib/redirect'

export function AuthPage() {
  const auth = useAuth()
  const { theme, setTheme } = useTheme()
  const location = useLocation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    document.title = '管理员登录 · Riichi'
  }, [])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    const username = String(form.get('username')).trim(),
      password = String(form.get('password'))
    if (!username || !password) {
      setError(new Error('请填写管理员用户名和密码。'))
      return
    }
    setBusy(true)
    try {
      // Success re-renders with the signed-in admin; the single redirect below
      // then returns to the page the guard came from.
      await auth.signIn(username, password)
    } catch (problem) {
      setError(problem instanceof Error ? problem : new Error('登录失败。'))
    } finally {
      setBusy(false)
    }
  }
  if (auth.user?.is_staff)
    return (
      <Navigate to={safeReturnPath((location.state as { from?: unknown } | null)?.from)} replace />
    )
  return (
    <main className="auth-shell">
      <section className="auth-story">
        <Link to="/login" className="auth-brand">
          R
          <span>
            riichi<small>TOURNAMENT SYSTEM</small>
          </span>
        </Link>
        <div>
          <span className="eyebrow">YOUR TOURNAMENT, WELL ORGANIZED</span>
          <h1>
            从容开赛，
            <br />
            <em>专注每场对局。</em>
          </h1>
          <p>
            为雀庄老板设计的赛事管理后台。
            <br />
            维护选手、组织比赛，清晰记录每一分。
          </p>
        </div>
        <span className="auth-assurance">
          <ShieldCheck size={18} /> 管理员专属 · 选手无需注册
        </span>
      </section>
      <section className="auth-form-panel">
        <Button
          className="auth-theme"
          variant="ghost"
          size="icon"
          aria-label="切换主题"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? <Sun /> : <Moon />}
        </Button>
        <div className="auth-form-wrap">
          <span className="eyebrow">RIICHI PREMIUM</span>
          <h2>欢迎回到 Riichi</h2>
          <p>登录雀庄管理后台。</p>
          <form onSubmit={submit} className="account-form" aria-label="登录表单">
            <label>
              用户名
              <input
                name="username"
                autoComplete="username"
                maxLength={150}
                required
                disabled={busy}
              />
            </label>
            <label>
              密码
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                maxLength={128}
                required
                disabled={busy}
              />
            </label>
            <FormFeedback error={error} />
            <Button type="submit" disabled={busy || auth.loading}>
              {busy ? '正在处理…' : '登录'}
              <ArrowRight size={16} />
            </Button>
          </form>
          <p className="auth-scope">仅管理员可登录。选手档案由雀庄维护。会话使用安全 Cookie。</p>
        </div>
      </section>
    </main>
  )
}
