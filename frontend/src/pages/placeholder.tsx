import { Link, useLocation } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, Check, CircleDashed } from 'lucide-react'
import { navigation } from '@/components/navigation'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const details = {
  '/tournaments': {
    title: '精彩赛事，即将从这里开始',
    description: '组织个人赛、安排轮次与分桌，并记录每一场对局的结果。',
    features: ['赛事与轮次管理', '随机与积分分桌', '点数录入与个人排名'],
  },
  '/players': {
    title: '等待每一位选手入席',
    description: '查看已注册选手，并为个人赛事选择参赛成员。',
    features: ['系统账号与选手资料', '赛事参赛成员管理', '赛事选手选择'],
  },
  '/machines': {
    title: '让每一张牌桌，各就其位',
    description: '管理独立编号的物理麻将桌，单场选择一至四张。',
    features: ['设备独立编号', '设备与赛事分桌关联', '单场最多四张'],
  },
} as const

export function PlaceholderPage() {
  const { pathname } = useLocation()
  const item = navigation.find((entry) => entry.path === pathname)!
  const detail = details[pathname as keyof typeof details]
  const Icon = item.icon
  return (
    <section className="placeholder-panel">
      <div className="placeholder-status">
        <span className="tiny-dot" />
        FOUNDATION / WORK IN PROGRESS<Badge variant="outline">功能准备中</Badge>
      </div>
      <div className="empty-state">
        <div className="empty-illustration">
          <div className="empty-orbit" />
          <div className="empty-icon">
            <Icon size={34} strokeWidth={1.3} />
          </div>
          <span className="empty-spark">+</span>
        </div>
        <span className="eyebrow">{item.title}</span>
        <h2>{detail.title}</h2>
        <p>
          {detail.description}
          <br />
          当前为工程骨架阶段，尚未开放数据管理。
        </p>
        <Button asChild variant="outline">
          <Link to="/dashboard">
            <ArrowLeft size={15} />
            返回仪表盘
          </Link>
        </Button>
      </div>
      <div className="placeholder-roadmap">
        <div>
          <span className="roadmap-label">
            <Check size={14} />
            工作空间已就绪
          </span>
          <span>后续规划</span>
        </div>
        <ul>
          {detail.features.map((feature) => (
            <li key={feature}>
              <CircleDashed size={15} />
              {feature}
              <ArrowUpRight size={14} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
