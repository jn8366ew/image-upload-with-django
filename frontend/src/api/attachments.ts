import axios, { isAxiosError, isCancel } from 'axios'
import type { Presign } from '../upload/queue'
import { type UploadApi, UploadError } from '../upload/runner'
import { api } from './client'

type PresignResponse = {
  uploads: { client_ref: string; public_id: string; url: string; fields: Record<string, string> }[]
}

// MSW는 XHR timeout을 구현하지 않아(실측) axios timeout 대신 signal로 끊습니다. 실제 브라우저에서도 같은 경로입니다.
async function converting<T>(
  timeoutMs: number,
  callerSignal: AbortSignal,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  try {
    return await run(AbortSignal.any([callerSignal, timeoutSignal]))
  } catch (error) {
    if (timeoutSignal.aborted && !callerSignal.aborted) throw new UploadError(undefined, true)
    if (isAxiosError(error) && !isCancel(error)) throw new UploadError(error.response?.status)
    throw error
  }
}

export function createUploadApi({ uploadTimeout = 30_000, apiTimeout = 15_000 } = {}): UploadApi {
  async function presign(files: { clientRef: string; file: File }[], signal: AbortSignal) {
    const { data } = await api.post<PresignResponse>(
      '/attachments/presign',
      {
        files: files.map(({ clientRef, file }) => ({
          client_ref: clientRef,
          filename: file.name,
          content_type: file.type,
          size: file.size,
        })),
      },
      { signal },
    )
    return data.uploads.map((u) => ({
      clientRef: u.client_ref,
      presign: { publicId: u.public_id, url: u.url, fields: u.fields },
    }))
  }

  async function upload(
    presign: Presign,
    file: File,
    { onProgress, signal }: { onProgress: (loaded: number) => void; signal: AbortSignal },
  ) {
    const form = new FormData()
    for (const [name, value] of Object.entries(presign.fields)) form.append(name, value)
    // S3 presigned POST는 file 뒤에 오는 필드를 무시합니다. file은 반드시 마지막에 넣습니다.
    form.append('file', file)
    await axios.post(presign.url, form, {
      withCredentials: false,
      signal,
      // event.loaded는 multipart 본문 전체(필드·경계 포함) 바이트라 파일 크기를 넘습니다. 비율로 환산합니다.
      onUploadProgress: (event) => onProgress(Math.round((event.progress ?? 0) * file.size)),
    })
  }

  async function complete(publicId: string, signal: AbortSignal) {
    await api.post(`/attachments/${publicId}/complete`, null, { signal })
  }

  return {
    presign: (files) =>
      converting(apiTimeout, new AbortController().signal, (s) => presign(files, s)),
    upload: (p, file, { onProgress, signal }) =>
      converting(uploadTimeout, signal, (s) => upload(p, file, { onProgress, signal: s })),
    complete: (publicId, signal) =>
      converting(apiTimeout, signal, (s) => complete(publicId, s)),
  }
}

export const uploadApi = createUploadApi()
