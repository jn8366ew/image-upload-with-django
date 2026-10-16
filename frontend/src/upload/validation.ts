export const MAX_FILE_SIZE = 2_621_440

const ALLOWED_TYPES = ['image/png', 'image/jpeg']

export type RejectReason = 'too_large' | 'unsupported_type'

export function validateFile(file: Pick<File, 'size' | 'type'>): RejectReason | null {
  if (!ALLOWED_TYPES.includes(file.type)) return 'unsupported_type'
  if (file.size > MAX_FILE_SIZE) return 'too_large'
  return null
}
