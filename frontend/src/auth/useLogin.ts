import { useMutation } from '@tanstack/react-query'
import { type Credentials, login, type SessionUser } from '../api/auth'

export function useLogin(onLoggedIn: (user: SessionUser) => void) {
  return useMutation({ mutationFn: (c: Credentials) => login(c), onSuccess: onLoggedIn })
}
