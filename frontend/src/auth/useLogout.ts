import { useMutation } from '@tanstack/react-query'
import { logout } from '../api/auth'

export function useLogout(onLoggedOut: () => void) {
  const mutation = useMutation({ mutationFn: logout, onSuccess: onLoggedOut })
  return { logout: () => mutation.mutate(), isPending: mutation.isPending }
}
