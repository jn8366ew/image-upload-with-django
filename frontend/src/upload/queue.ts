export type Status = 'queued' | 'presigning' | 'uploading' | 'confirming' | 'backoff' | 'done' | 'failed'

export type Presign = { publicId: string; url: string; fields: Record<string, string> }

export type Entry = {
  clientRef: string
  file: File
  status: Status
  loaded: number
  attempt: number
  presign?: Presign
  retryable?: boolean
}

export type QueueState = Entry[]

export type QueueAction =
  | { type: 'added'; files: { clientRef: string; file: File }[] }
  | { type: 'presign_started'; clientRefs: string[] }
  | { type: 'presigned'; clientRef: string; presign: Presign }
  | { type: 'progress'; clientRef: string; loaded: number }
  | { type: 'uploaded'; clientRef: string }
  | { type: 'completed'; clientRef: string }
  | { type: 'failed'; clientRef: string; stage: 'presign' | 'upload' | 'complete'; status?: number }

function update(state: QueueState, clientRef: string, patch: Partial<Entry>): QueueState {
  return state.map((e) => (e.clientRef === clientRef ? { ...e, ...patch } : e))
}

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case 'added':
      return [...state, ...action.files.map((f) => ({ ...f, status: 'queued' as const, loaded: 0, attempt: 0 }))]
    case 'presign_started':
      return state.map((e) =>
        action.clientRefs.includes(e.clientRef) ? { ...e, status: 'presigning' } : e,
      )
    case 'presigned':
      return update(state, action.clientRef, { status: 'uploading', presign: action.presign })
    case 'progress':
      return update(state, action.clientRef, { loaded: action.loaded })
    case 'uploaded':
      return update(state, action.clientRef, { status: 'confirming' })
    case 'completed':
      return update(state, action.clientRef, { status: 'done' })
    case 'failed':
      if (action.status === 400) {
        return update(state, action.clientRef, { status: 'failed', retryable: false })
      }
      if (action.status === 409) {
        return update(state, action.clientRef, { status: 'failed', retryable: true })
      }
      return state.map((e) =>
        e.clientRef === action.clientRef
          ? { ...e, status: 'backoff', attempt: e.attempt + 1, presign: undefined }
          : e,
      )
  }
}
