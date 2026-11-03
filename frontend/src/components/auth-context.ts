import { createContext, useContext } from 'react'
import type { User } from '@/services/api'

export type AuthState = {
  user: User | null
  loading: boolean
  error: string
  restore: () => Promise<void>
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}
export const AuthContext = createContext<AuthState | null>(null)
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider required')
  return context
}
