import { describe, expect, it } from 'vitest'
import { MAX_FILE_SIZE, validateFile } from './validation'

const png = { name: 'a.png', size: 1, type: 'image/png' }

describe('validateFile', () => {
  it('rejects file over size limit', () => {
    expect(validateFile({ ...png, size: MAX_FILE_SIZE + 1 })).toBe('too_large')
    expect(validateFile({ ...png, size: MAX_FILE_SIZE })).toBeNull()
  })

  it('rejects disallowed mime type and accepts png and jpeg', () => {
    for (const type of ['image/heic', 'image/svg+xml', 'image/gif', '']) {
      expect(validateFile({ ...png, type })).toBe('unsupported_type')
    }
    expect(validateFile({ ...png, type: 'image/png' })).toBeNull()
    expect(validateFile({ ...png, type: 'image/jpeg' })).toBeNull()
  })

  it('rejects filename over 255 code points or with control characters', () => {
    expect(validateFile({ ...png, name: '😀'.repeat(251) + '.png' })).toBeNull()
    expect(validateFile({ ...png, name: '😀'.repeat(252) + '.png' })).toBe('invalid_name')
    for (const name of ['a\x00.png', 'a\n.png', 'a\x7f.png']) {
      expect(validateFile({ ...png, name })).toBe('invalid_name')
    }
  })
})
