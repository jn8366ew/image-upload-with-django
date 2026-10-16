import { describe, expect, it } from 'vitest'
import { runPool } from './pool'

function deferred() {
  let resolve!: () => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('runPool', () => {
  it('never runs more than limit tasks at once', async () => {
    const pending = Array.from({ length: 5 }, deferred)
    let running = 0
    let maxRunning = 0
    let started = 0
    const tasks = pending.map((d) => async () => {
      running++
      started++
      maxRunning = Math.max(maxRunning, running)
      try {
        await d.promise
      } finally {
        running--
      }
    })

    const done = runPool(tasks, 2)
    for (const d of pending) {
      await flush()
      d.resolve()
    }
    await done

    expect(maxRunning).toBe(2)
    expect(started).toBe(5)
  })

  it('one failure does not stop other tasks', async () => {
    const finished: number[] = []
    const tasks = [0, 1, 2, 3].map((i) => async () => {
      await flush()
      if (i === 0) throw new Error('boom')
      finished.push(i)
    })

    await runPool(tasks, 2)

    expect(finished.sort()).toEqual([1, 2, 3])
  })

  it('resolves after all tasks settle', async () => {
    const slow = deferred()
    const error = new Error('boom')
    let settled = false
    const done = runPool(
      [
        () => slow.promise.then(() => 'a'),
        () => Promise.reject(error),
        () => Promise.resolve('c'),
      ],
      2,
    ).then((results) => {
      settled = true
      return results
    })

    await flush()
    expect(settled).toBe(false)
    slow.resolve()

    expect(await done).toEqual([
      { status: 'fulfilled', value: 'a' },
      { status: 'rejected', reason: error },
      { status: 'fulfilled', value: 'c' },
    ])
  })
})
