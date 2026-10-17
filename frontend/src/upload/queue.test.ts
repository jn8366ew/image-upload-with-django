import { describe, expect, it } from 'vitest'
import { type QueueAction, type QueueState, type Stage, queueReducer } from './queue'

const file = new File(['x'], 'a.png', { type: 'image/png' })
const presign = { publicId: 'p1', url: 'https://upload.test', fields: { key: 'k' } }

function statusOf(state: QueueState, clientRef: string) {
  return state.find((e) => e.clientRef === clientRef)?.status
}

function at(stage: Stage): QueueState {
  let state = queueReducer([], { type: 'added', files: [{ clientRef: 'c1', file }] })
  state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1'] })
  if (stage === 'presign') return state
  state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
  if (stage === 'upload') return state
  return queueReducer(state, { type: 'uploaded', clientRef: 'c1' })
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
    const state = queueReducer(at(stage), { type: 'failed', clientRef: 'c1', stage, status: 400 })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: false })
  })

  it('409 on complete moves to retryable failed', () => {
    const state = queueReducer(at('complete'), {
      type: 'failed',
      clientRef: 'c1',
      stage: 'complete',
      status: 409,
    })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: true, attempt: 0 })
  })

  it('network error retries with backoff up to 4 times', () => {
    let state = at('upload')

    for (const [i, status] of [undefined, 0, 500, 503].entries()) {
      state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload', status })
      expect(state[0]).toMatchObject({ status: 'backoff', attempt: i + 1, presign })
    }
  })

  it('exhausted retries move to retryable failed', () => {
    let state = at('upload')

    for (const status of [403, undefined, 403, 503]) {
      state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload', status })
    }
    expect(state[0]).toMatchObject({ status: 'backoff', attempt: 4 })

    state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload' })

    expect(state[0]).toMatchObject({ status: 'failed', retryable: true })
  })

  it.each(['presign', 'complete'] as const)(
    'api 403 on presign or complete moves to fatal failed (%s)',
    (stage) => {
      const state = queueReducer(at(stage), { type: 'failed', clientRef: 'c1', stage, status: 403 })

      expect(state[0]).toMatchObject({ status: 'failed', retryable: false })
    },
  )

  it.each([
    ['presign', 503, 'queued'],
    ['upload', 403, 'queued'],
    ['upload', 503, 'uploading'],
    ['complete', 503, 'confirming'],
  ] as const)('backoff resumes at failed stage (%s %i → %s)', (stage, status, resumed) => {
    let state = queueReducer(at(stage), { type: 'failed', clientRef: 'c1', stage, status })

    state = queueReducer(state, { type: 'retry_due', clientRef: 'c1' })

    expect(state[0].status).toBe(resumed)
  })

  it.each([
    [404, false],
    [413, false],
    [429, true],
  ])('unclassified 4xx moves to fatal failed, 429 to retryable (%i)', (status, retryable) => {
    const state = queueReducer(at('presign'), {
      type: 'failed',
      clientRef: 'c1',
      stage: 'presign',
      status,
    })

    expect(state[0]).toMatchObject({ status: 'failed', retryable, attempt: 0 })
  })

  it('cancel moves uploading file to cancelled', () => {
    const state = queueReducer(at('upload'), { type: 'cancelled', clientRef: 'c1' })

    expect(state[0].status).toBe('cancelled')
  })

  describe('terminal states ignore further actions', () => {
    const terminal: [string, () => QueueState][] = [
      ['done', () => queueReducer(at('complete'), { type: 'completed', clientRef: 'c1' })],
      ['cancelled', () => queueReducer(at('upload'), { type: 'cancelled', clientRef: 'c1' })],
      [
        'fatal failed',
        () =>
          queueReducer(at('presign'), { type: 'failed', clientRef: 'c1', stage: 'presign', status: 400 }),
      ],
    ]
    const actions: QueueAction[] = [
      { type: 'presign_started', clientRefs: ['c1'] },
      { type: 'presigned', clientRef: 'c1', presign },
      { type: 'progress', clientRef: 'c1', loaded: 1 },
      { type: 'uploaded', clientRef: 'c1' },
      { type: 'completed', clientRef: 'c1' },
      { type: 'failed', clientRef: 'c1', stage: 'upload' },
      { type: 'retry_due', clientRef: 'c1' },
      { type: 'cancelled', clientRef: 'c1' },
    ]

    it.each(terminal.flatMap(([name, build]) => actions.map((a) => [name, a.type, build, a] as const)))(
      '%s ignores %s',
      (_name, _type, build, action) => {
        const state = build()

        expect(queueReducer(state, action)[0]).toBe(state[0])
      },
    )
  })

  it('retry_requested requeues only retryable failed', () => {
    let state = queueReducer([], {
      type: 'added',
      files: [
        { clientRef: 'c1', file },
        { clientRef: 'c2', file },
      ],
    })
    state = queueReducer(state, { type: 'presign_started', clientRefs: ['c1', 'c2'] })
    state = queueReducer(state, { type: 'presigned', clientRef: 'c1', presign })
    for (let i = 0; i < 5; i++) {
      state = queueReducer(state, { type: 'failed', clientRef: 'c1', stage: 'upload' })
    }
    state = queueReducer(state, { type: 'failed', clientRef: 'c2', stage: 'presign', status: 400 })
    const fatal = state[1]

    state = queueReducer(state, { type: 'retry_requested' })

    expect(state[0]).toMatchObject({ status: 'queued', attempt: 0, presign: undefined })
    expect(state[1]).toBe(fatal)
  })
})
