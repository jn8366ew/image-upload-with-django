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
})
