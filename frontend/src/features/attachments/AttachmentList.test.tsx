import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithClient } from '../../test/render'
import { server } from '../../test/server'
import { AttachmentList } from './AttachmentList'

type Item = { public_id: string; original_filename: string; uploaded_at: string }

function item(publicId: string, filename: string, uploadedAt = '2026-10-17T00:05:00Z'): Item {
  return { public_id: publicId, original_filename: filename, uploaded_at: uploadedAt }
}

function listHandler(results: Item[]) {
  server.use(
    http.get('*/api/attachments', () => HttpResponse.json({ next: null, previous: null, results })),
  )
}

describe('AttachmentList', () => {
  afterEach(() => vi.restoreAllMocks())

  it('list shows filename and upload time', async () => {
    listHandler([item('p1', 'cat.png', '2026-10-17T00:05:00Z')])

    renderWithClient(<AttachmentList timeZone="UTC" />)

    expect(await screen.findByText('cat.png')).toBeInTheDocument()
    expect(screen.getByText('2026-10-17 00:05')).toBeInTheDocument()
  })

  it('load more fetches next page', async () => {
    server.use(
      http.get('*/api/attachments', ({ request }) =>
        new URL(request.url).searchParams.get('cursor') === 'c2'
          ? HttpResponse.json({ next: null, previous: null, results: [item('p2', 'old.png')] })
          : HttpResponse.json({
              next: 'http://testserver/api/attachments?cursor=c2',
              previous: null,
              results: [item('p1', 'new.png')],
            }),
      ),
    )
    renderWithClient(<AttachmentList timeZone="UTC" />)
    expect(await screen.findByText('new.png')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: '더 보기' }))

    expect(await screen.findByText('old.png')).toBeInTheDocument()
    expect(screen.getByText('new.png')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull()
  })

  it('download calls download endpoint, never an s3 url', async () => {
    listHandler([item('p1', 'cat.png')])
    renderWithClient(<AttachmentList timeZone="UTC" />)

    const link = await screen.findByRole('link', { name: 'cat.png 다운로드' })

    expect(link).toHaveAttribute('href', '/api/attachments/p1/download')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('delete removes item from list immediately', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    listHandler([item('p1', 'cat.png'), item('p2', 'dog.png')])
    server.use(
      http.delete('*/api/attachments/p1', async () => {
        await gate
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithClient(<AttachmentList timeZone="UTC" />)

    await userEvent.setup().click(await screen.findByRole('button', { name: 'cat.png 삭제' }))

    expect(screen.queryByText('cat.png')).toBeNull()
    expect(screen.getByText('dog.png')).toBeInTheDocument()
    release()
  })
})
