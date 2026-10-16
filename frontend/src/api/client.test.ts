import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { server } from '../test/server'
import { api } from './client'

function setCsrfCookie(value: string) {
  document.cookie = `csrftoken=${value}; path=/`
}

describe('api client', () => {
  afterEach(() => {
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  })

  it('reads csrf token from cookie on every request', async () => {
    const sent: (string | null)[] = []
    server.use(
      http.post('*/api/echo', ({ request }) => {
        sent.push(request.headers.get('X-CSRFToken'))
        return new HttpResponse(null, { status: 204 })
      }),
    )

    setCsrfCookie('AAA')
    await api.post('/echo')
    setCsrfCookie('BBB')
    await api.post('/echo')

    expect(sent).toEqual(['AAA', 'BBB'])
  })
})
