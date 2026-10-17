export type Status =
  | 'queued'
  | 'presigning'
  | 'uploading'
  | 'confirming'
  | 'backoff'
  | 'done'
  | 'failed'
  | 'cancelled'

export type Stage = 'presign' | 'upload' | 'complete'

export type Presign = { publicId: string; url: string; fields: Record<string, string> }

export type Entry = {
  clientRef: string
  file: File
  status: Status
  loaded: number
  attempt: number
  presign?: Presign
  retryable?: boolean
  failedStage?: Stage
}

export type QueueState = Entry[]

export type QueueAction =
  | { type: 'added'; files: { clientRef: string; file: File }[] }
  | { type: 'presign_started'; clientRefs: string[] }
  | { type: 'presigned'; clientRef: string; presign: Presign }
  | { type: 'progress'; clientRef: string; loaded: number }
  | { type: 'uploaded'; clientRef: string }
  | { type: 'completed'; clientRef: string }
  | { type: 'failed'; clientRef: string; stage: Stage; status?: number; timeout?: boolean }
  | { type: 'retry_due'; clientRef: string }
  | { type: 'cancelled'; clientRef: string }
  | { type: 'retry_requested' }

const MAX_RETRIES = 4

type Outcome = 'backoff' | 'retryable' | 'fatal'

function classify(stage: Stage, status?: number, timeout?: boolean): Outcome {
  if (timeout) return 'retryable'
  if (status === 409 || status === 429) return 'retryable'
  if (!status || status >= 500 || (status === 403 && stage === 'upload')) return 'backoff'
  return 'fatal'
}

export function isFinished(e: Entry) {
  return e.status === 'done' || e.status === 'failed' || e.status === 'cancelled'
}

export function isRetryable(e: Entry) {
  return e.status === 'failed' && e.retryable === true
}

function isTerminal(e: Entry) {
  return isFinished(e) && !isRetryable(e)
}

function update(
  state: QueueState,
  clientRefs: string[],
  patch: Partial<Entry> | ((e: Entry) => Partial<Entry>),
): QueueState {
  return state.map((e) =>
    clientRefs.includes(e.clientRef) && !isTerminal(e)
      ? { ...e, ...(typeof patch === 'function' ? patch(e) : patch) }
      : e,
  )
}

function fail(e: Entry, stage: Stage, status?: number, timeout?: boolean): Partial<Entry> {
  const outcome = classify(stage, status, timeout)
  if (outcome === 'fatal') return { status: 'failed', retryable: false }
  if (outcome === 'retryable' || e.attempt >= MAX_RETRIES) {
    return { status: 'failed', retryable: true }
  }
  return {
    status: 'backoff',
    attempt: e.attempt + 1,
    failedStage: stage,
    presign: status === 403 ? undefined : e.presign,
  }
}

function resume(e: Entry): Status {
  if (!e.presign) return 'queued'
  return e.failedStage === 'complete' ? 'confirming' : 'uploading'
}

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case 'added':
      return [
        ...state,
        ...action.files.map((f) => ({ ...f, status: 'queued' as const, loaded: 0, attempt: 0 })),
      ]
    case 'presign_started':
      return update(state, action.clientRefs, { status: 'presigning' })
    case 'presigned':
      return update(state, [action.clientRef], { status: 'uploading', presign: action.presign })
    case 'progress':
      return update(state, [action.clientRef], { loaded: action.loaded })
    case 'uploaded':
      return update(state, [action.clientRef], { status: 'confirming' })
    case 'completed':
      return update(state, [action.clientRef], { status: 'done' })
    case 'failed':
      return update(state, [action.clientRef], (e) => fail(e, action.stage, action.status, action.timeout))
    case 'retry_due':
      return update(state, [action.clientRef], (e) => ({ status: resume(e) }))
    case 'cancelled':
      return update(state, [action.clientRef], { status: 'cancelled' })
    case 'retry_requested':
      return update(
        state,
        state.filter(isRetryable).map((e) => e.clientRef),
        { status: 'queued', attempt: 0, presign: undefined },
      )
  }
}
