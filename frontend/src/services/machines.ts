import { api } from './api'

export type MachineStatus = 'available' | 'maintenance' | 'disabled' | 'retired'
export type Machine = {
  id: number
  machine_no: string
  name: string
  location: string
  description: string
  status: MachineStatus
  created_at: string
  updated_at: string
}
export type MachineInput = {
  machine_no?: string
  name: string
  location: string
  description: string
  status: Exclude<MachineStatus, 'retired'>
}
export type MachinePage = {
  count: number
  next: string | null
  previous: string | null
  results: Machine[]
  summary: Record<MachineStatus | 'active', number>
}
export const machineLabels: Record<MachineStatus, string> = {
  available: '可用',
  maintenance: '维护中',
  disabled: '停用',
  retired: '已退役',
}
export const fetchMachines = (page: number, search: string, status: string, signal?: AbortSignal) =>
  api<MachinePage>(
    `/machines/?page=${page}&search=${encodeURIComponent(search)}&status=${status}`,
    { signal },
  )
export const fetchMachine = (id: number) => api<Machine>(`/machines/${id}/`)
export const saveMachine = (values: MachineInput, id?: number) =>
  api<Machine>(id ? `/machines/${id}/` : '/machines/', {
    method: id ? 'PATCH' : 'POST',
    body: values,
  })
export const retireMachine = (id: number) =>
  api<Machine>(`/machines/${id}/retire/`, { method: 'POST', body: {} })
