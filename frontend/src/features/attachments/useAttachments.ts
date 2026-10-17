import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { listAttachments } from '../../api/attachments'

export const ATTACHMENTS_KEY = ['attachments']

export function useAttachments() {
  const query = useInfiniteQuery({
    queryKey: ATTACHMENTS_KEY,
    queryFn: ({ pageParam }) => listAttachments(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  })
  return {
    items: query.data?.pages.flatMap((page) => page.items) ?? [],
    hasMore: query.hasNextPage,
    loadMore: () => void query.fetchNextPage(),
  }
}

export function useRefreshAttachments() {
  const queryClient = useQueryClient()
  return useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ATTACHMENTS_KEY }),
    [queryClient],
  )
}
