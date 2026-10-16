import { describe, expect, it } from 'vitest'
import { MAX_FILE_SIZE, validateFile } from './validation'

describe('validateFile', () => {
  it('rejects file over size limit', () => {
    expect(validateFile({ size: MAX_FILE_SIZE + 1, type: 'image/png' })).toBe('too_large')
    expect(validateFile({ size: MAX_FILE_SIZE, type: 'image/png' })).toBeNull()
  })

  it('rejects disallowed mime type and accepts png and jpeg', () => {
    for (const type of ['image/heic', 'image/svg+xml', 'image/gif', '']) {
      expect(validateFile({ size: 1, type })).toBe('unsupported_type')
    }
    expect(validateFile({ size: 1, type: 'image/png' })).toBeNull()
    expect(validateFile({ size: 1, type: 'image/jpeg' })).toBeNull()
  })
})
