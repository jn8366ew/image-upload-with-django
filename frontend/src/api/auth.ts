import { api } from './client'

export type Credentials = { username: string; password: string }
export type SessionUser = { username: string }

export async function login(credentials: Credentials): Promise<SessionUser> {
  await api.get('/auth/csrf')
  const { data } = await api.post<SessionUser>('/auth/login', credentials)
  return data
}
