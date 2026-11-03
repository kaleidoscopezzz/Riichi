import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Moon, Sun, ArrowRight, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/components/auth-context'
import { useTheme } from '@/components/theme-context'
import { FormFeedback } from '@/components/form-feedback'
import { Button } from '@/components/ui/button'
import { api } from '@/services/api'

export function AuthPage({ register = false }: { register?: boolean }) {
  const auth = useAuth()
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [registered, setRegistered] = useState(false)
  useEffect(() => {
    document.title = `${register ? '注册' : '登录'} · Riichi`
  }, [register])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    const username = String(form.get('username')).trim()
    const password = String(form.get('password'))
    const nickname = String(form.get('nickname') || '').trim()
    const confirm = String(form.get('password_confirm') || '')
    if (!username || !password || (register && !nickname)) {
      setError(new Error('请完整填写必填信息。'))
      return
    }
    if (register && password !== confirm) {
      setError(new Error('两次输入的密码不一致。'))
      return
    }
    if (register && password.length < 8) {
      setError(new Error('密码至少需要 8 个字符。'))
      return
    }
    setBusy(true)
    try {
      if (register) {
        await api('/auth/register/', {
          method: 'POST',
          body: { username, nickname, password, password_confirm: confirm },
        })
        event.currentTarget?.reset()
        setRegistered(true)
      } else {
        await auth.signIn(username, password)
        const from = location.state?.from
        navigate(
          typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')
            ? from
            : '/dashboard',
          { replace: true },
        )
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem : new Error('请求失败。'))
    } finally {
      setBusy(false)
    }
  }
  if (auth.user) return <Navigate to="/dashboard" replace />
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
          <span className="eyebrow">YOUR NEXT ROUND STARTS HERE</span>
          <h1>
            同场竞技，
            <br />
            <em>从这里入席。</em>
          </h1>
          <p>
            专注四人立直麻将个人赛事。
            <br />
            用一个账号，准备好你的选手身份。
          </p>
        </div>
        <span className="auth-assurance">
          <ShieldCheck size={18} />
          你的身份，你的选手档案
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
          <h2>{register ? '创建你的账号' : '欢迎回到 Riichi'}</h2>
          <p>{register ? '注册后自动建立独立的选手档案。' : '登录，进入你的赛事工作空间。'}</p>
          {registered ? (
            <>
              <FormFeedback success="注册成功，请使用新账号登录。" />
              <Button asChild>
                <Link to="/login">
                  前往登录
                  <ArrowRight size={16} />
                </Link>
              </Button>
            </>
          ) : (
            <form
              onSubmit={submit}
              className="account-form"
              aria-label={register ? '注册表单' : '登录表单'}
            >
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
              {register && (
                <label>
                  选手昵称
                  <input
                    name="nickname"
                    autoComplete="nickname"
                    maxLength={80}
                    required
                    disabled={busy}
                  />
                </label>
              )}
              <label>
                密码
                <input
                  name="password"
                  type="password"
                  autoComplete={register ? 'new-password' : 'current-password'}
                  maxLength={128}
                  required
                  disabled={busy}
                />
              </label>
              {register && (
                <>
                  <p className="field-hint">
                    至少 8 个字符，避免常见密码、纯数字及与用户名相似的内容。
                  </p>
                  <label>
                    确认密码
                    <input
                      name="password_confirm"
                      type="password"
                      autoComplete="new-password"
                      maxLength={128}
                      required
                      disabled={busy}
                    />
                  </label>
                </>
              )}
              <FormFeedback error={error} />
              <Button type="submit" disabled={busy || auth.loading}>
                {busy ? '正在处理…' : register ? '注册账号' : '登录'}
                <ArrowRight size={16} />
              </Button>
            </form>
          )}
          <p className="auth-switch">
            {register ? '已有账号？' : '还没有账号？'}{' '}
            <Link to={register ? '/login' : '/register'}>{register ? '返回登录' : '创建账号'}</Link>
          </p>
          <p className="auth-scope">
            {register ? '注册不会授予管理员权限。' : '会话由安全 Cookie 管理。'} 不提供第三方登录。
          </p>
        </div>
      </section>
    </main>
  )
}
