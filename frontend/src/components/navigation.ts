import { LayoutDashboard, Trophy, UsersRound, Grid2X2, Settings2, UserRound } from 'lucide-react'

export const navigation = [
  { path: '/dashboard', title: '仪表盘', caption: '工作台概览', icon: LayoutDashboard },
  { path: '/tournaments', title: '赛事管理', caption: '管理每一场精彩对局', icon: Trophy },
  { path: '/players', title: '选手管理', caption: '连接每一位参赛选手', icon: UsersRound },
  { path: '/machines', title: '麻将机管理', caption: '有序安排比赛设备', icon: Grid2X2 },
  { path: '/settings', title: '系统设置', caption: '系统信息与外观偏好', icon: Settings2 },
  { path: '/profile', title: '个人资料', caption: '管理我的选手身份', icon: UserRound },
] as const
