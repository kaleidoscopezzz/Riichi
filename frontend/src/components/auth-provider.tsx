import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, ApiError, type User } from '@/services/api'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const restore = useCallback(async () => {
    const current = ++generation.current
    setLoading(true)
    setError('')
    try {
      const restored = await api<User>('/auth/me/')
      if (current === generation.current) setUser(restored)
    } catch (problem) {
      if (current !== generation.current) return
      setUser(null)
      if (!(problem instanceof ApiError && problem.code === 'not_authenticated'))
        setError(problem instanceof Error ? problem.message : '无法恢复登录状态。')
    } finally {
      if (current === generation.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    void restore()
    const expire = () => {
      generation.current++
      setUser(null)
      setLoading(false)
    }
    window.addEventListener('riichi-session-expired', expire)
    return () => {
      generation.current++
      window.removeEventListener('riichi-session-expired', expire)
    }
  }, [restore])
  async function signIn(username: string, password: string) {
    generation.current++
    setUser(await api<User>('/auth/login/', { method: 'POST', body: { username, password } }))
    setError('')
    setLoading(false)
  }
  async function signOut() {
    generation.current++
    await api('/auth/logout/', { method: 'POST', body: {} })
    setUser(null)
  }
  return (
    <AuthContext.Provider value={{ user, loading, error, restore, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
