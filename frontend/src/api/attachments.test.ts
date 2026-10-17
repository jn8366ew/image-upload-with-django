import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/server'
import { UploadError } from '../upload/runner'
import { createUploadApi, uploadApi } from './attachments'

const S3_URL = 'https://s3.test/upload'
const file = new File(['x'], 'a.png', { type: 'image/png' })
const presign = { publicId: 'p1', url: S3_URL, fields: { key: 'k' } }
const noop = () => {}

const calls = {
  presign: () => uploadApi.presign([{ clientRef: 'c1', file }]),
  upload: () =>
    uploadApi.upload(presign, file, { onProgress: noop, signal: new AbortController().signal }),
  complete: () => uploadApi.complete('p1', new AbortController().signal),
}

function respondAll(response: () => Response) {
  server.use(
    http.post('*/api/attachments/presign', response),
    http.post(S3_URL, response),
    http.post('*/api/attachments/p1/complete', response),
  )
}

describe('uploadApi', () => {
  it.each([
    ['presign', 400],
    ['upload', 403],
    ['complete', 409],
    ['complete', 503],
  ] as const)(
    'wrapper converts 4xx and 5xx responses to UploadError with status (%s %i)',
    async (name, status) => {
      respondAll(() => HttpResponse.json({ detail: 'x' }, { status }))

      const error = await calls[name]().catch((e: unknown) => e)

      expect(error).toBeInstanceOf(UploadError)
      expect((error as UploadError).status).toBe(status)
    },
  )

  it('wrapper converts network error to UploadError without status', async () => {
    respondAll(() => HttpResponse.error())

    const error = await calls.upload().catch((e: unknown) => e)

    expect(error).toBeInstanceOf(UploadError)
    expect((error as UploadError).status).toBeUndefined()
  })

  it.each(['presign', 'upload', 'complete'] as const)(
    'wrapper marks timeout on UploadError (%s)',
    async (name) => {
      respondAll(() => delay('infinite') as never)
      const fast = createUploadApi({ uploadTimeout: 100, apiTimeout: 100 })
      const signal = new AbortController().signal
      const run = {
        presign: () => fast.presign([{ clientRef: 'c1', file }]),
        upload: () => fast.upload(presign, file, { onProgress: noop, signal }),
        complete: () => fast.complete('p1', signal),
      }[name]

      const error = await run().catch((e: unknown) => e)

      expect(error).toBeInstanceOf(UploadError)
      expect((error as UploadError).timeout).toBe(true)
    },
  )

  it('wrapper rethrows abort without converting', async () => {
    server.use(http.post(S3_URL, () => new Promise<Response>(() => {})))
    const controller = new AbortController()

    const pending = uploadApi
      .upload(presign, file, { onProgress: noop, signal: controller.signal })
      .catch((e: unknown) => e)
    controller.abort()
    const error = await pending

    expect(error).not.toBeInstanceOf(UploadError)
    expect(controller.signal.aborted).toBe(true)
  })
})
