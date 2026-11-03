import { createContext, useContext } from 'react'

export type HealthState = {
  status: 'loading' | 'connected' | 'error' | 'offline'
  message: string
  checkedAt: Date | null
  check: () => void
}

export const HealthContext = createContext<HealthState | null>(null)

export function useHealth() {
  const value = useContext(HealthContext)
  if (!value) throw new Error('useHealth requires HealthProvider')
  return value
}
