import { useEffect, useReducer, useState } from 'react'
import { uploadApi } from '../../api/attachments'
import {
  isFinished,
  isRetryable,
  type QueueAction,
  type QueueState,
  queueReducer,
} from '../../upload/queue'
import { createRunner } from '../../upload/runner'
import { type RejectReason, validateFile } from '../../upload/validation'

function buildRunner(reactDispatch: (a: QueueAction) => void) {
  let state: QueueState = []
  let seq = 0
  return createRunner({
    api: uploadApi,
    // 실행기는 dispatch 직후의 상태로 다음 행동을 정하므로, React 렌더를 기다리지 않고 사본에 먼저 반영합니다.
    dispatch: (action) => {
      state = queueReducer(state, action)
      reactDispatch(action)
    },
    getEntry: (clientRef) => state.find((e) => e.clientRef === clientRef),
    nextRef: () => `f${++seq}`,
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    random: Math.random,
  })
}

export function useUploader() {
  const [entries, reactDispatch] = useReducer(queueReducer, [])
  const [rejected, setRejected] = useState<{ name: string; reason: RejectReason }[]>([])
  const [runner] = useState(() => buildRunner(reactDispatch))

  useEffect(() => () => runner.cancelAll(), [runner])

  return {
    entries,
    rejected,
    select: (files: File[]) => {
      const accepted: File[] = []
      const nextRejected: { name: string; reason: RejectReason }[] = []
      for (const file of files) {
        const reason = validateFile(file)
        if (reason) nextRejected.push({ name: file.name, reason })
        else accepted.push(file)
      }
      setRejected(nextRejected)
      if (accepted.length > 0) void runner.add(accepted)
    },
    canRetry: entries.some(isRetryable),
    retry: () => void runner.retry(),
    canCancel: entries.some((e) => !isFinished(e)),
    cancelAll: () => runner.cancelAll(),
  }
}
