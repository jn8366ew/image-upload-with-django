import { describe, expect, it } from 'vitest'
import { type QueueState, queueReducer } from './queue'

const file = new File(['x'], 'a.png', { type: 'image/png' })
const presign = { publicId: 'p1', url: 'https://upload.test', fields: { key: 'k' } }

function statusOf(state: QueueState, clientRef: string) {
  return state.find((e) => e.clientRef === clientRef)?.status
}

describe('queueReducer', () => {
  it('queued → presigning → uploading → confirming → done', () => {
    let state: QueueState = []

    state = queueReducer(state, { type: 'added', files: [{ clientRef: 'c1', file }] })
    expect(statusOf(state, 'c1')).toBe('queued')

    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
    expect(statusOf(state, 'c1')).toBe('presigning')

    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    expect(statusOf(state, 'c1')).toBe('uploading')

    state = queueReducer(state, { type: 'uploaded', clientRef: 'c1' })
    expect(statusOf(state, 'c1')).toBe('confirming')

    state = queueReducer(state, { type: 'completed', clientRef: 'c1' })
    expect(statusOf(state, 'c1')).toBe('done')
  })

  it('progress event updates only the target file', () => {
    let state: QueueState = queueReducer([], {
      type: 'added',
      files: [
        { clientRef: 'c1', file },
        { clientRef: 'c2', file },
      ],
    })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1', 'c2'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c2', presign })

    state = queueReducer(state, { type: 'progress', clientRef: 'c1', loaded: 100 })

    expect(state.map((e) => e.loaded)).toEqual([100, 0])
  })

  it('403 clears presign and retries', () => {
    let state: QueueState = queueReducer([], {
      type: 'added',
      files: [
        { clientRef: 'c1', file },
        { clientRef: 'c2', file },
      ],
    })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1', 'c2'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c2', presign })
    const before = state[1]

    state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload', status: 403 })

    expect(state[0]).toMatchObject({ status: 'backoff', attempt: 1, presign: undefined })
    expect(state[1]).toBe(before)
  })

  it.each(['presign', 'upload', 'complete'] as const)('400 moves to fatal failed (%s)', (stage) => {
    const steps = { presign: 0, upload: 1, complete: 2 }[stage]
    let state: QueueState = queueReducer([], { type: 'added', files: [{ clientRef: 'c1', file }] })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
    if (steps >= 1) state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    if (steps >= 2) state = queueReducer(state, { type: 'uploaded', clientRef: 'c1' })

    state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage, status: 400 })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: false })
  })

  it('409 on complete moves to retryable failed', () => {
    let state: QueueState = queueReducer([], { type: 'added', files: [{ clientRef: 'c1', file }] })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    state = queueReducer(state, { type: 'uploaded', clientRef: 'c1' })

    state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'complete', status: 409 })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: true, attempt: 0 })
  })

  it('network error retries with backoff up to 4 times', () => {
    let state: QueueState = queueReducer([], { type: 'added', files: [{ clientRef: 'c1', file }] })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })

    for (const [i, status] of [undefined, 0, 500, 503].entries()) {
      state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload', status })
      expect(state[0]).toMatchObject({ status: 'backoff', attempt: i + 1, presign })
    }
  })

  it('exhausted retries move to retryable failed', () => {
    let state: QueueState = queueReducer([], { type: 'added', files: [{ clientRef: 'c1', file }] })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })

    for (const status of [403, undefined, 403, 503]) {
      state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload', status })
    }
    expect(state[0]).toMatchObject({ status: 'backoff', attempt: 4 })

    state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload' })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: true })
  })
})
