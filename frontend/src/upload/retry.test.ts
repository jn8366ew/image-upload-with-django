import { describe, expect, it } from 'vitest'
import { retryDelay } from './retry'

describe('retryDelay', () => {
  it('retry delay grows exponentially with full jitter', () => {
    expect([1, 2, 3, 4].map((n) => retryDelay(n, () => 1))).toEqual([1000, 2000, 4000, 8000])
    expect(retryDelay(3, () => 0.5)).toBe(2000)
    expect(retryDelay(4, () => 0)).toBe(0)
  })
})
