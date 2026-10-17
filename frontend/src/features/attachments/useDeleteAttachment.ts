import { type InfiniteData, useMutation, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { type AttachmentPage, deleteAttachment } from '../../api/attachments'
import { ATTACHMENTS_KEY } from './useAttachments'

type Pages = InfiniteData<AttachmentPage, string | null>

const DELETE_FAILED = '삭제하지 못했습니다. 잠시 후 다시 시도해 주세요'

function statusOf(error: unknown) {
  return isAxiosError(error) ? error.response?.status : undefined
}

export function useDeleteAttachment() {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: deleteAttachment,
    onMutate: async (publicId: string) => {
      await queryClient.cancelQueries({ queryKey: ATTACHMENTS_KEY })
      const previous = queryClient.getQueryData<Pages>(ATTACHMENTS_KEY)
      queryClient.setQueryData<Pages>(ATTACHMENTS_KEY, (data) =>
        data && {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.filter((item) => item.publicId !== publicId),
          })),
        },
      )
      return { previous }
    },
    onError: (error, _publicId, context) => {
      const status = statusOf(error)
      if (status === 404) return
      queryClient.setQueryData(ATTACHMENTS_KEY, context?.previous)
      if (status === 403) void queryClient.invalidateQueries({ queryKey: ATTACHMENTS_KEY })
    },
  })
  return {
    remove: (publicId: string) => mutation.mutate(publicId),
    errorMessage: mutation.isError && statusOf(mutation.error) !== 404 ? DELETE_FAILED : null,
  }
}
