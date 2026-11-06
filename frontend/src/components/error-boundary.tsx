import { Component, type ReactNode } from 'react'
import { Button } from './ui/button'

type Props = {
  children: ReactNode
  /** A change (e.g. the route path) clears a previous failure. */
  resetKey?: unknown
  /** Injected in tests; defaults to a full page reload. */
  reload?: () => void
}

const reloadPage = () => window.location.reload()

// React only supports render-error boundaries as class components. React itself
// logs the error; the page never shows stack traces or internal messages.
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidUpdate(previous: Props) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey)
      this.setState({ failed: false })
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="session-state app-error" aria-labelledby="app-error-title">
        <span className="eyebrow">UNEXPECTED ERROR</span>
        <div role="alert">
          <h1 id="app-error-title">页面暂时无法显示</h1>
          <p>页面出现了意外错误。已保存的赛事、成绩与选手数据不受影响，重新加载后即可继续操作。</p>
        </div>
        <Button onClick={() => (this.props.reload ?? reloadPage)()}>重新加载</Button>
      </main>
    )
  }
}
