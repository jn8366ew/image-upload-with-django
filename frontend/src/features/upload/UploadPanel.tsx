import type { Entry } from '../../upload/queue'
import type { RejectReason } from '../../upload/validation'
import { useUploader } from './useUploader'

const STATUS_LABEL: Record<Entry['status'], string> = {
  queued: '대기',
  presigning: '준비 중',
  uploading: '업로드 중',
  confirming: '확인 중',
  backoff: '재시도 대기',
  done: '완료',
  failed: '실패',
  cancelled: '취소됨',
}

const REJECT_MESSAGE: Record<RejectReason, string> = {
  too_large: '2.5MB 이하 파일만 올릴 수 있습니다',
  unsupported_type: 'PNG·JPEG만 올릴 수 있습니다',
  invalid_name: '파일명이 너무 길거나 허용되지 않는 문자가 있습니다',
}

const STATUS_TONE: Record<Entry['status'], string> = {
  queued: 'muted',
  presigning: 'active',
  uploading: 'active',
  confirming: 'active',
  backoff: 'active',
  done: 'ok',
  failed: 'err',
  cancelled: 'muted',
}

function labelOf(e: Entry) {
  return e.status === 'failed' && e.retryable ? '실패(다시 시도 가능)' : STATUS_LABEL[e.status]
}

export function UploadPanel({ onCompleted }: { onCompleted?: () => void }) {
  const { entries, rejected, select, canRetry, retry, canCancel, cancelAll } = useUploader(onCompleted)

  return (
    <div>
      <div className="toolbar">
        <label className="file-button">
          이미지 선택
          <input
            type="file"
            multiple
            accept="image/png,image/jpeg"
            onChange={(event) => {
              select([...(event.target.files ?? [])])
              event.target.value = ''
            }}
          />
        </label>
        <button type="button" onClick={retry} disabled={!canRetry}>
          실패한 파일 다시 시도
        </button>
        <button type="button" onClick={cancelAll} disabled={!canCancel}>
          전체 취소
        </button>
      </div>
      <p className="hint">취소는 전송만 멈춥니다. 이미 전송된 파일은 목록에 나타날 수 있습니다.</p>
      {rejected.length > 0 && (
        <ul className="rejected" aria-label="올릴 수 없는 파일">
          {rejected.map((r, i) => (
            <li key={`${r.name}-${i}`}>
              <span>{r.name}</span>
              <span>{REJECT_MESSAGE[r.reason]}</span>
            </li>
          ))}
        </ul>
      )}
      <ul className="rows" aria-label="업로드 목록">
        {entries.map((e) => (
          <li key={e.clientRef} className="upload-row">
            <span className="name">{e.file.name}</span>
            <progress max={e.file.size} value={e.loaded} />
            <span className={`status ${STATUS_TONE[e.status]}`}>{labelOf(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
