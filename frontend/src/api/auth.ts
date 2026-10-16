import { isAxiosError } from 'axios'
import { api } from './client'

export type Credentials = { username: string; password: string }
export type SessionUser = { username: string }

export async function login(credentials: Credentials): Promise<SessionUser> {
  await api.get('/auth/csrf')
  const { data } = await api.post<SessionUser>('/auth/login', credentials)
  return data
}

export async function fetchMe(): Promise<SessionUser | null> {
  try {
    const { data } = await api.get<SessionUser>('/auth/me')
    return data
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 403) return null
    throw error
  }
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}
