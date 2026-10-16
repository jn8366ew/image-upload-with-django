import { useMutation } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { type Credentials, login, type SessionUser } from '../api/auth'

export function useLogin(onLoggedIn: (user: SessionUser) => void) {
  const mutation = useMutation({ mutationFn: (c: Credentials) => login(c), onSuccess: onLoggedIn })
  return {
    login: mutation.mutate,
    isPending: mutation.isPending,
    errorMessage: mutation.error ? loginErrorMessage(mutation.error) : null,
  }
}

function loginErrorMessage(error: Error): string {
  if (isAxiosError(error) && error.response?.status === 400) {
    return '아이디 또는 비밀번호가 올바르지 않습니다'
  }
  return '잠시 후 다시 시도해 주세요'
}
