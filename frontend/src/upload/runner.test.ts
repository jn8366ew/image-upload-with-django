import { describe, expect, it } from 'vitest'
import { type QueueAction, type QueueState, queueReducer } from './queue'
import { createRunner, type UploadApi, UploadError } from './runner'

function png(name: string) {
  return new File(['x'], name, { type: 'image/png' })
}

function harness(api: Partial<UploadApi>) {
  let state: QueueState = []
  let seq = 0
  const actions: QueueAction[] = []
  const presignCalls: string[][] = []
  const sleeps: number[] = []
  const fullApi: UploadApi = {
    presign: async (files) => {
      presignCalls.push(files.map((f) => f.clientRef))
      return files.map((f) => ({
        clientRef: f.clientRef,
        presign: { publicId: `p-${f.clientRef}`, url: 'https://upload.test', fields: {} },
      }))
    },
    upload: async () => {},
    complete: async () => {},
    ...api,
  }
  const runner = createRunner({
    api: fullApi,
    dispatch: (action: QueueAction) => {
      actions.push(action)
      state = queueReducer(state, action)
    },
    getEntry: (ref) => state.find((e) => e.clientRef === ref),
    nextRef: () => `c${++seq}`,
    sleep: async (ms) => {
      sleeps.push(ms)
    },
    random: () => 0.5,
  })
  return { runner, presignCalls, actions, sleeps, statuses: () => state.map((e) => e.status) }
}

describe('runner', () => {
  it('presigns in batches of at most 10', async () => {
    const { runner, presignCalls } = harness({})

    await runner.add(Array.from({ length: 12 }, (_, i) => png(`${i}.png`)))

    expect(presignCalls.map((refs) => refs.length)).toEqual([10, 2])
  })

  it('uploads then completes each file, reporting progress', async () => {
    const completed: string[] = []
    const { runner, actions, statuses } = harness({
      upload: async (_presign, _file, { onProgress }) => onProgress(1),
      complete: async (publicId) => {
        completed.push(publicId)
      },
    })

    await runner.add([png('a.png'), png('b.png')])

    expect(statuses()).toEqual(['done', 'done'])
    expect(completed.sort()).toEqual(['p-c1', 'p-c2'])
    expect(actions.filter((a) => a.type === 'progress')).toHaveLength(2)
  })

  it('waits retry delay then resumes at failed stage', async () => {
    let uploads = 0
    let completes = 0
    const { runner, sleeps, statuses } = harness({
      upload: async () => {
        if (++uploads === 1) throw new UploadError(503)
      },
      complete: async () => {
        if (++completes === 1) throw new UploadError(503)
      },
    })

    await runner.add([png('a.png')])

    expect(statuses()).toEqual(['done'])
    expect(sleeps).toEqual([500, 1000])
    expect([uploads, completes]).toEqual([2, 2])
  })

  it('403 re-presigns only that file', async () => {
    let failedOnce = false
    const { runner, presignCalls, statuses } = harness({
      upload: async (presign) => {
        if (presign.publicId === 'p-c1' && !failedOnce) {
          failedOnce = true
          throw new UploadError(403)
        }
      },
    })

    await runner.add([png('a.png'), png('b.png')])

    expect(presignCalls).toEqual([['c1', 'c2'], ['c1']])
    expect(statuses()).toEqual(['done', 'done'])
  })

  it('stops on fatal failure without further calls', async () => {
    let calls = 0
    const { runner, sleeps, statuses } = harness({
      presign: async () => {
        throw new UploadError(400)
      },
      upload: async () => {
        calls++
      },
      complete: async () => {
        calls++
      },
    })

    await runner.add([png('a.png'), png('b.png')])

    expect(statuses()).toEqual(['failed', 'failed'])
    expect(calls).toBe(0)
    expect(sleeps).toEqual([])
  })

  it('cancel aborts in-flight and skips not-yet-started files', async () => {
    const signals: AbortSignal[] = []
    const { runner, sleeps, statuses } = harness({
      upload: (_presign, _file, { signal }) =>
        new Promise((_resolve, reject) => {
          signals.push(signal)
          signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    })

    const done = runner.add(['a', 'b', 'c', 'd'].map((n) => png(`${n}.png`)))
    await new Promise((r) => setTimeout(r, 0))
    runner.cancelAll()
    await done

    expect(signals).toHaveLength(3)
    expect(signals.every((s) => s.aborted)).toBe(true)
    expect(statuses()).toEqual(['cancelled', 'cancelled', 'cancelled', 'cancelled'])
    expect(sleeps).toEqual([])
  })

  it('cancel stops later presign batches and keeps done files', async () => {
    const { runner, presignCalls, statuses } = harness({
      upload: (presign, _file, { signal }) =>
        presign.publicId === 'p-c1'
          ? Promise.resolve()
          : new Promise((_resolve, reject) => {
              signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
            }),
    })

    const done = runner.add(Array.from({ length: 11 }, (_, i) => png(`${i}.png`)))
    await new Promise((r) => setTimeout(r, 0))
    runner.cancelAll()
    await done

    expect(presignCalls).toHaveLength(1)
    expect(statuses()).toEqual(['done', ...Array(10).fill('cancelled')])
  })

  it('add after cancel uploads normally', async () => {
    const { runner, statuses } = harness({
      upload: async (_presign, _file, { signal }) => {
        if (signal.aborted) throw new DOMException('aborted', 'AbortError')
      },
    })
    runner.cancelAll()

    await runner.add([png('a.png')])

    expect(statuses()).toEqual(['done'])
  })
})
