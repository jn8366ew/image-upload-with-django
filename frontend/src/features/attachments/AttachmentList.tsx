import { formatUploadedAt } from './format'
import { useAttachments } from './useAttachments'
import { useDeleteAttachment } from './useDeleteAttachment'

export function AttachmentList({ timeZone }: { timeZone?: string }) {
  const { items, hasMore, loadMore } = useAttachments()
  const { remove, errorMessage } = useDeleteAttachment()

  return (
    <section>
      {errorMessage && <p role="alert">{errorMessage}</p>}
      <ul aria-label="내 이미지">
        {items.map((item) => (
          <li key={item.publicId}>
            <span>{item.filename}</span>
            <time dateTime={item.uploadedAt}>{formatUploadedAt(item.uploadedAt, timeZone)}</time>
            <a
              href={`/api/attachments/${item.publicId}/download`}
              target="_blank"
              rel="noopener"
              aria-label={`${item.filename} 다운로드`}
            >
              다운로드
            </a>
            <button
              type="button"
              aria-label={`${item.filename} 삭제`}
              onClick={() => {
                if (window.confirm(`${item.filename}을(를) 삭제할까요?`)) remove(item.publicId)
              }}
            >
              삭제
            </button>
          </li>
        ))}
      </ul>
      {hasMore && (
        <button type="button" onClick={loadMore}>
          더 보기
        </button>
      )}
    </section>
  )
}
