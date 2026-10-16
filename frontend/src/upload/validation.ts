export const MAX_FILE_SIZE = 2_621_440

const MAX_NAME_LENGTH = 255

const ALLOWED_TYPES = ['image/png', 'image/jpeg']

export type RejectReason = 'too_large' | 'unsupported_type' | 'invalid_name'

function isValidName(name: string): boolean {
  // 서버(Python len)와 같게 코드 포인트 수로 셉니다. String.length는 이모지를 2로 셉니다.
  const chars = [...name]
  return (
    chars.length <= MAX_NAME_LENGTH &&
    chars.every((c) => c.charCodeAt(0) >= 32 && c.charCodeAt(0) !== 127)
  )
}

export function validateFile(file: Pick<File, 'name' | 'size' | 'type'>): RejectReason | null {
  if (!ALLOWED_TYPES.includes(file.type)) return 'unsupported_type'
  if (file.size > MAX_FILE_SIZE) return 'too_large'
  if (!isValidName(file.name)) return 'invalid_name'
  return null
}
