import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { ArrowUpRight, ChevronRight, Menu, Moon, Sun, Layers3 } from 'lucide-react'
import { navigation } from '@/components/navigation'
import { HealthBadge } from '@/components/health-status'
import { useTheme } from '@/components/theme-context'
import { useAuth } from '@/components/auth-context'
import { Button } from '@/components/ui/button'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

function Brand() {
  return (
    <Link to="/dashboard" className="brand" aria-label="Riichi 首页">
      <span className="brand-mark">
        R<span />
      </span>
      <span className="brand-word">
        riichi<span>TOURNAMENT SYSTEM</span>
      </span>
    </Link>
  )
}

function Sidebar({ close }: { close?: () => void }) {
  const { user } = useAuth()
  return (
    <div className="sidebar-inner">
      <Brand />
      <div className="navigation-label">工作空间</div>
      <nav aria-label="主导航" className="main-nav">
        {navigation
          .filter(
            (item) =>
              !['/players', '/machines', '/tournaments'].includes(item.path) || user?.is_staff,
          )
          .map(({ path, title, icon: Icon }) => (
            <NavLink
              to={path}
              key={path}
              onClick={close}
              className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
            >
              <Icon size={19} />
              <span>{title}</span>
              <ChevronRight size={14} className="nav-chevron" />
            </NavLink>
          ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="foundation-note">
          <Layers3 size={20} />
          <div>
            <p>从容组织，专注对局</p>
            <span>为立直麻将赛事而设计</span>
          </div>
          <ArrowUpRight size={15} />
        </div>
        <div className="sidebar-version">
          <span className="tiny-dot" />
          RIICHI PREMIUM<span>V1.0</span>
        </div>
      </div>
    </div>
  )
}

export function AppLayout() {
  const { user, signOut } = useAuth()
  const [logoutError, setLogoutError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
  async function exit() {
    setLoggingOut(true)
    setLogoutError('')
    try {
      await signOut()
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : '退出失败，请重试。')
    } finally {
      setLoggingOut(false)
    }
  }
  const { pathname } = useLocation()
  const page =
    navigation.find((item) => item.path === pathname) ||
    (/^\/tournaments\/\d+\/rounds$/.test(pathname)
      ? { ...navigation[1], title: '分桌工作台', caption: '第一轮座次与真实设备占用' }
      : undefined)
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  useEffect(() => {
    document.title = `${page?.title ?? '页面未找到'} · Riichi`
  }, [page])
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        跳转到主要内容
      </a>
      <aside className="desktop-sidebar">
        <Sidebar />
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="mobile-menu"
                  aria-label="打开导航菜单"
                >
                  <Menu />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="mobile-sidebar">
                <SheetHeader className="sr-only">
                  <SheetTitle>工作空间导航</SheetTitle>
                  <SheetDescription>访问 Riichi 的各个基础页面</SheetDescription>
                </SheetHeader>
                <Sidebar close={() => setOpen(false)} />
              </SheetContent>
            </Sheet>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <Link to="/dashboard">工作空间</Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{page?.title ?? '页面未找到'}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
          <div className="topbar-right">
            <HealthBadge />
            <span className="topbar-divider" />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? '切换为亮色主题' : '切换为暗色主题'}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </Button>
            <Link to="/profile" className="current-user" aria-label="我的个人资料">
              {user?.username}
            </Link>
            <Button
              variant="ghost"
              className="logout-button"
              onClick={() => void exit()}
              disabled={loggingOut}
            >
              {loggingOut ? '退出中…' : '退出'}
            </Button>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {pathname === '/dashboard' ? 'YOUR TOURNAMENT WORKSPACE' : 'RIICHI WORKSPACE'}
              </span>
              <h1>{page?.title ?? '页面未找到'}</h1>
              <p>{page?.caption ?? '这个地址还没有对应的页面'}</p>
            </div>
            <span className="edition-label">个人赛 · V1.0</span>
          </div>
          <Outlet />
          {logoutError && (
            <p role="alert" className="form-feedback error">
              {logoutError}
            </p>
          )}
        </main>
        <footer className="app-footer">
          <span>
            RIICHI<span className="footer-dot">·</span>让对局回归精彩
          </span>
          <span>
            Foundation 05<span className="footer-dot">/</span>首轮分桌与设备分配
          </span>
        </footer>
      </div>
    </div>
  )
}
