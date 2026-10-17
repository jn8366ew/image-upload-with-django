import { runPool } from './pool'
import { type Entry, isFinished, isRetryable, type Presign, type QueueAction, type Stage } from './queue'
import { retryDelay } from './retry'

export type UploadApi = {
  presign(files: { clientRef: string; file: File }[]): Promise<{ clientRef: string; presign: Presign }[]>
  upload(
    presign: Presign,
    file: File,
    options: { onProgress: (loaded: number) => void; signal: AbortSignal },
  ): Promise<void>
  complete(publicId: string, signal: AbortSignal): Promise<void>
}

export class UploadError extends Error {
  readonly status?: number
  readonly timeout: boolean

  constructor(status?: number, timeout = false) {
    super('upload request failed')
    this.status = status
    this.timeout = timeout
  }
}

export type RunnerDeps = {
  api: UploadApi
  dispatch: (action: QueueAction) => void
  getEntry: (clientRef: string) => Entry | undefined
  nextRef: () => string
  sleep: (ms: number) => Promise<void>
  random: () => number
}

const PRESIGN_BATCH = 10
const CONCURRENCY = 3

function failure(error: unknown) {
  const { status, timeout } = error as UploadError
  return { status, timeout }
}

export function createRunner({ api, dispatch, getEntry, nextRef, sleep, random }: RunnerDeps) {
  let controller = new AbortController()
  const clientRefs: string[] = []
  let chain = Promise.resolve()

  async function step(
    signal: AbortSignal,
    clientRef: string,
    stage: Stage,
    run: () => Promise<void>,
    next: QueueAction,
  ) {
    try {
      await run()
      dispatch(next)
    } catch (error) {
      if (signal.aborted) return
      dispatch({ type: 'failed', clientRef, stage, ...failure(error) })
    }
  }

  async function presignBatch(batch: { clientRef: string; file: File }[]) {
    dispatch({ type: 'presign_started', clientRefs: batch.map((f) => f.clientRef) })
    try {
      for (const { clientRef, presign } of await api.presign(batch)) {
        dispatch({ type: 'presigned', clientRef, presign })
      }
    } catch (error) {
      for (const { clientRef } of batch) {
        dispatch({ type: 'failed', clientRef, stage: 'presign', ...failure(error) })
      }
    }
  }

  async function process(signal: AbortSignal, clientRef: string, file: File) {
    while (!signal.aborted) {
      const entry = getEntry(clientRef)!
      const presign = entry.presign!
      if (entry.status === 'queued') {
        await presignBatch([{ clientRef, file }])
      } else if (entry.status === 'uploading') {
        await step(
          signal,
          clientRef,
          'upload',
          () =>
            api.upload(presign, file, {
              onProgress: (loaded) => dispatch({ type: 'progress', clientRef, loaded }),
              signal,
            }),
          { type: 'uploaded', clientRef },
        )
      } else if (entry.status === 'confirming') {
        await step(signal, clientRef, 'complete', () => api.complete(presign.publicId, signal), {
          type: 'completed',
          clientRef,
        })
      } else if (entry.status === 'backoff') {
        await sleep(retryDelay(entry.attempt, random))
        dispatch({ type: 'retry_due', clientRef })
      } else {
        return
      }
    }
  }

  async function run(signal: AbortSignal, files: { clientRef: string; file: File }[]) {
    for (let i = 0; i < files.length; i += PRESIGN_BATCH) {
      if (signal.aborted) return
      const batch = files.slice(i, i + PRESIGN_BATCH)
      await presignBatch(batch)
      await runPool(
        batch.map(({ clientRef, file }) => () => process(signal, clientRef, file)),
        CONCURRENCY,
      )
    }
  }

  function enqueue(files: { clientRef: string; file: File }[]) {
    if (controller.signal.aborted) controller = new AbortController()
    const { signal } = controller
    chain = chain.then(() => run(signal, files))
    return chain
  }

  return {
    retry(): Promise<void> {
      const requeued = clientRefs
        .map((clientRef) => getEntry(clientRef)!)
        .filter(isRetryable)
      dispatch({ type: 'retry_requested' })
      return enqueue(requeued.map(({ clientRef, file }) => ({ clientRef, file })))
    },
    cancelAll(): void {
      controller.abort()
      for (const clientRef of clientRefs) {
        if (!isFinished(getEntry(clientRef)!)) {
          dispatch({ type: 'cancelled', clientRef })
        }
      }
    },
    add(files: File[]): Promise<void> {
      const added = files.map((file) => ({ clientRef: nextRef(), file }))
      dispatch({ type: 'added', files: added })
      clientRefs.push(...added.map((f) => f.clientRef))
      return enqueue(added)
    },
  }
}
