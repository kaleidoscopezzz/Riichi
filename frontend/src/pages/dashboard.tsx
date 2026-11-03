import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  CircleDashed,
  Flag,
  LayoutGrid,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { navigation } from '@/components/navigation'
import { HealthStatus } from '@/components/health-status'

function TableIllustration() {
  return (
    <div className="table-illustration" aria-hidden="true">
      <div className="table-ring ring-outer" />
      <div className="table-ring ring-inner" />
      <div className="mahjong-table">
        <span className="table-corner corner-tl" />
        <span className="table-corner corner-tr" />
        <span className="table-corner corner-bl" />
        <span className="table-corner corner-br" />
        <div className="table-center">
          <span>立直</span>
          <small>RIICHI</small>
        </div>
        <div className="tile-row tiles-top">
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <i key={item} />
          ))}
        </div>
        <div className="tile-row tiles-bottom">
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <i key={item} />
          ))}
        </div>
        <div className="tile-row tiles-left">
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <i key={item} />
          ))}
        </div>
        <div className="tile-row tiles-right">
          {[0, 1, 2, 3, 4, 5].map((item) => (
            <i key={item} />
          ))}
        </div>
      </div>
      <span className="illustration-caption">FOUR PLAYERS. ONE CHAMPION.</span>
      <span className="illustration-plus plus-top">+</span>
      <span className="illustration-plus plus-bottom">+</span>
    </div>
  )
}

export function DashboardPage() {
  return (
    <div className="dashboard">
      <section className="welcome-panel">
        <div className="welcome-copy">
          <Badge variant="outline" className="premium-badge">
            <Sparkles size={12} />
            RIICHI PREMIUM
          </Badge>
          <h2>
            让每一场对局，
            <br />
            <span>井然有序。</span>
          </h2>
          <p>
            从第一轮落座，到最终冠军揭晓。
            <br />
            一个专注个人赛事的立直麻将管理工作空间。
          </p>
          <div className="hero-actions">
            <Button asChild className="gold-button">
              <Link to="/tournaments">
                进入赛事管理
                <ArrowRight size={16} />
              </Link>
            </Button>
            <Link className="text-link" to="/settings">
              查看系统信息
              <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="hero-note">
            <span className="tiny-dot" />
            基础工作空间已就绪，赛事功能将逐步开放
          </div>
        </div>
        <TableIllustration />
      </section>
      <section aria-labelledby="quick-access-title" className="quick-access">
        <div className="section-heading">
          <div>
            <span className="eyebrow">QUICK ACCESS</span>
            <h2 id="quick-access-title">一切，从这里开始</h2>
          </div>
          <span className="subtle-label">赛事管理的每个环节，都有条不紊</span>
        </div>
        <div className="quick-access-grid">
          {navigation.slice(1, 4).map(({ path, title, icon: Icon }, index) => (
            <Link to={path} className="quick-card-link" key={path}>
              <Card className="quick-card">
                <div className="quick-card-top">
                  <span className={`quick-icon quick-icon-${index}`}>
                    <Icon size={21} />
                  </span>
                  <ArrowUpRight size={18} className="card-arrow" />
                </div>
                <h3>{title}</h3>
                <p>
                  {
                    [
                      '组织个人赛事，串联每一轮对局',
                      '管理参赛选手，汇聚同场竞技者',
                      '统一设备编号，让每张牌桌各就其位',
                    ][index]
                  }
                </p>
                <div className="quick-card-bottom">
                  <span>功能准备中</span>
                  <ArrowRight size={14} />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>
      <div className="dashboard-bottom">
        <HealthStatus />
        <section className="foundation-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">BUILT FOR RIICHI</span>
              <h2>专注赛事，稳步前行</h2>
            </div>
            <Flag size={19} className="gold-text" />
          </div>
          <p className="foundation-description">
            当前为工程基础阶段。我们先把体验与连接准备好，再逐步构建完整的赛事流程。
          </p>
          <div className="phase-row">
            <span className="phase-icon complete">
              <CheckCheck size={17} />
            </span>
            <div>
              <h3>基础工作空间</h3>
              <p>统一界面 · 页面导航 · 服务连接</p>
            </div>
            <Badge variant="outline" className="phase-badge">
              当前阶段
            </Badge>
          </div>
          <div className="phase-row">
            <span className="phase-icon">
              <CircleDashed size={18} />
            </span>
            <div>
              <h3>个人赛事管理</h3>
              <p>账号与选手 · 分桌 · 计分与排名</p>
            </div>
            <span className="upcoming-label">后续规划</span>
          </div>
          <div className="foundation-bottom">
            <LayoutGrid size={14} />
            <span>四人立直麻将 · 仅个人赛</span>
            <Link to="/settings" aria-label="查看系统设置">
              <ArrowUpRight size={16} />
            </Link>
          </div>
        </section>
      </div>
    </div>
  )
}
