import { Check, Monitor, Moon, Palette, Server, Sun } from 'lucide-react'
import { useTheme } from '@/components/theme-context'
import { HealthStatus } from '@/components/health-status'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

export function SettingsPage() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="settings-grid">
      <section className="settings-panel">
        <div className="settings-section-title">
          <Palette size={20} />
          <div>
            <h2>外观偏好</h2>
            <p>选择适合你的工作空间主题</p>
          </div>
        </div>
        <div className="theme-options">
          {(['dark', 'light'] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={`theme-option ${theme === option ? 'selected' : ''}`}
              onClick={() => setTheme(option)}
              aria-pressed={theme === option}
            >
              <span className={`theme-preview preview-${option}`}>
                <i />
                <i />
                <i />
              </span>
              <span>
                {option === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
                {option === 'dark' ? '深色 · Riichi Premium' : '浅色 · 明亮工作空间'}
                {theme === option && <Check size={15} />}
              </span>
            </button>
          ))}
        </div>
        <p className="settings-note">
          <Monitor size={14} />
          外观偏好仅保存在当前浏览器。
        </p>
      </section>
      <section className="settings-panel">
        <div className="settings-section-title">
          <Server size={20} />
          <div>
            <h2>系统基础信息</h2>
            <p>当前工作空间与工程范围</p>
          </div>
          <Badge variant="outline">Foundation</Badge>
        </div>
        <dl className="system-info">
          <div>
            <dt>产品</dt>
            <dd>Riichi · 立直麻将赛事管理</dd>
          </div>
          <div>
            <dt>目标版本</dt>
            <dd>V1.0 · 个人赛</dd>
          </div>
          <div>
            <dt>当前阶段</dt>
            <dd>F0-03 麻将机资源管理</dd>
          </div>
          <div>
            <dt>服务接口</dt>
            <dd className="mono">GET /api/v1/health/</dd>
          </div>
        </dl>
        <p className="settings-note">账号与选手档案已开放；赛事与计分功能仍在后续规划中。</p>
      </section>
      <HealthStatus />
      <section className="settings-panel settings-about">
        <span className="eyebrow">DESIGNED WITH PURPOSE</span>
        <h2>
          少一点繁杂，
          <br />
          多一点专注。
        </h2>
        <p>
          Riichi 围绕四人立直麻将个人赛设计，
          <br />
          让赛事组织清晰，让每轮对局有据可循。
        </p>
        <Button variant="outline" asChild>
          <a
            href="https://github.com/kaleidoscopezzz/Riichi"
            target="_blank"
            rel="noopener noreferrer"
          >
            查看项目仓库
          </a>
        </Button>
      </section>
    </div>
  )
}
