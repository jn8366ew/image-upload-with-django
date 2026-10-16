import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchMe, type SessionUser } from '../api/auth'

const SESSION_KEY = ['session']

export function useSession() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: SESSION_KEY, queryFn: fetchMe })
  return {
    user: query.data ?? null,
    isPending: query.isPending,
    setUser: (user: SessionUser | null) => queryClient.setQueryData(SESSION_KEY, user),
  }
}
