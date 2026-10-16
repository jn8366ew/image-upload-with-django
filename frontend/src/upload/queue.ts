export type Status = 'queued' | 'presigning' | 'uploading' | 'confirming' | 'done'

export type Presign = { publicId: string; url: string; fields: Record<string, string> }

export type Entry = {
  clientRef: string
  file: File
  status: Status
  loaded: number
  presign?: Presign
}

export type QueueState = Entry[]

export type QueueAction =
  | { type: 'added'; files: { clientRef: string; file: File }[] }
  | { type: 'presign_started'; clientRefs: string[] }
  | { type: 'presigned'; clientRef: string; presign: Presign }
  | { type: 'progress'; clientRef: string; loaded: number }
  | { type: 'uploaded'; clientRef: string }
  | { type: 'completed'; clientRef: string }

function update(state: QueueState, clientRef: string, patch: Partial<Entry>): QueueState {
  return state.map((e) => (e.clientRef === clientRef ? { ...e, ...patch } : e))
}

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case 'added':
      return [...state, ...action.files.map((f) => ({ ...f, status: 'queued' as const, loaded: 0 }))]
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
  }
}
