import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <section className="placeholder-panel">
      <div className="empty-state">
        <span className="eyebrow">404 / PAGE NOT FOUND</span>
        <h2>这张牌，暂时不在牌桌上</h2>
        <p>请检查页面地址，或返回仪表盘继续浏览。</p>
        <Button asChild>
          <Link to="/dashboard">
            <ArrowLeft size={16} />
            返回仪表盘
          </Link>
        </Button>
      </div>
    </section>
  )
}
