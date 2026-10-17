import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithClient } from '../../test/render'
import { MAX_FILE_SIZE } from '../../upload/validation'
import { server } from '../../test/server'
import { UploadPanel } from './UploadPanel'

const S3_URL = 'https://s3.test/upload'

type PresignRequest = { files: { client_ref: string; filename: string }[] }

function uploadHandlers() {
  const presignedNames: string[][] = []
  server.use(
    http.post('*/api/attachments/presign', async ({ request }) => {
      const { files } = (await request.json()) as PresignRequest
      presignedNames.push(files.map((f) => f.filename))
      return HttpResponse.json(
        {
          uploads: files.map((f) => ({
            client_ref: f.client_ref,
            public_id: `p-${f.filename}`,
            url: S3_URL,
            fields: { key: 'k' },
          })),
        },
        { status: 201 },
      )
    }),
    http.post(S3_URL, () => new HttpResponse(null, { status: 204 })),
    http.post('*/api/attachments/:publicId/complete', ({ params }) =>
      HttpResponse.json({ public_id: params.publicId, status: 'COMPLETED' }),
    ),
  )
  return { presignedNames }
}

function png(name: string, size = 3) {
  return new File([new Uint8Array(size)], name, { type: 'image/png' })
}

async function select(files: File[]) {
  await userEvent.setup().upload(screen.getByLabelText('이미지 선택'), files)
}

function row(name: string) {
  return within(screen.getByRole('list', { name: '업로드 목록' })).getByText(name).closest('li')!
}

describe('UploadPanel', () => {
  it('selecting files shows per-file progress and done state', async () => {
    uploadHandlers()
    renderWithClient(<UploadPanel />)

    await select([png('a.png'), png('b.png')])

    for (const name of ['a.png', 'b.png']) {
      expect(await within(row(name)).findByText('완료')).toBeInTheDocument()
      expect(within(row(name)).getByRole('progressbar')).toHaveAttribute('value', '3')
    }
  })

  it('retry failed only resends failed files', async () => {
    const { presignedNames } = uploadHandlers()
    let conflicted = false
    server.use(
      http.post('*/api/attachments/p-a.png/complete', () => {
        if (conflicted) return
        conflicted = true
        return HttpResponse.json({ detail: 'object_missing' }, { status: 409 })
      }),
    )
    renderWithClient(<UploadPanel />)
    await select([png('a.png'), png('b.png')])
    expect(await within(row('a.png')).findByText('실패(다시 시도 가능)')).toBeInTheDocument()
    expect(await within(row('b.png')).findByText('완료')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: '실패한 파일 다시 시도' }))

    expect(await within(row('a.png')).findByText('완료')).toBeInTheDocument()
    expect(presignedNames).toEqual([['a.png', 'b.png'], ['a.png']])
  })

  it('cancel all marks unfinished uploads cancelled and shows notice', async () => {
    uploadHandlers()
    let started = 0
    server.use(
      http.post(
        S3_URL,
        () =>
          new Promise<Response>(() => {
            started++
          }),
      ),
    )
    renderWithClient(<UploadPanel />)
    await select([png('a.png'), png('b.png')])
    await waitFor(() => expect(started).toBe(2))

    await userEvent.setup().click(screen.getByRole('button', { name: '전체 취소' }))

    expect(within(row('a.png')).getByText('취소됨')).toBeInTheDocument()
    expect(within(row('b.png')).getByText('취소됨')).toBeInTheDocument()
    expect(screen.getByText(/이미 전송된 파일은 목록에 나타날 수 있습니다/)).toBeInTheDocument()
  })

  it('oversized file shows guidance message', async () => {
    const { presignedNames } = uploadHandlers()
    renderWithClient(<UploadPanel />)

    await select([png('big.png', MAX_FILE_SIZE + 1)])

    const rejected = screen.getByRole('list', { name: '올릴 수 없는 파일' })
    expect(within(rejected).getByText('big.png')).toBeInTheDocument()
    expect(within(rejected).getByText('2.5MB 이하 파일만 올릴 수 있습니다')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: '업로드 목록' })).queryByText('big.png')).toBeNull()
    await new Promise((r) => setTimeout(r, 50))
    expect(presignedNames).toEqual([])
  })
})
