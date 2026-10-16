import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from './App'
import { api } from './api/client'
import { renderWithClient } from './test/render'
import { server } from './test/server'

function authHandlers(login: Parameters<typeof http.post>[1]) {
  return [
    http.get('*/api/auth/csrf', () => new HttpResponse(null, { status: 204 })),
    http.post('*/api/auth/login', login),
  ]
}

async function submitLogin(username: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('아이디'), username)
  await user.type(screen.getByLabelText('비밀번호'), password)
  await user.click(screen.getByRole('button', { name: '로그인' }))
}

describe('login', () => {
  it('login form posts credentials and shows upload screen', async () => {
    let body: unknown
    server.use(
      ...authHandlers(async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ username: 'alice' })
      }),
    )
    renderWithClient(<App />)

    await submitLogin('alice', 'pw-1234')

    expect(await screen.findByRole('heading', { name: '업로드' })).toBeInTheDocument()
    expect(body).toEqual({ username: 'alice', password: 'pw-1234' })
    expect(screen.queryByLabelText('비밀번호')).not.toBeInTheDocument()
  })

  it('invalid credentials shows error', async () => {
    server.use(
      ...authHandlers(() =>
        HttpResponse.json({ detail: 'invalid credentials' }, { status: 400 }),
      ),
    )
    renderWithClient(<App />)

    await submitLogin('alice', 'wrong')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '아이디 또는 비밀번호가 올바르지 않습니다',
    )
    expect(screen.queryByRole('heading', { name: '업로드' })).not.toBeInTheDocument()
  })

  it('new csrftoken from login response is sent on next POST', async () => {
    const sent: (string | null)[] = []
    server.use(
      http.get(
        '*/api/auth/csrf',
        () =>
          new HttpResponse(null, { status: 204, headers: { 'Set-Cookie': 'csrftoken=OLD; Path=/' } }),
      ),
      http.post('*/api/auth/login', ({ request }) => {
        sent.push(request.headers.get('X-CSRFToken'))
        return HttpResponse.json(
          { username: 'alice' },
          { headers: { 'Set-Cookie': 'csrftoken=NEW; Path=/' } },
        )
      }),
      http.post('*/api/echo', ({ request }) => {
        sent.push(request.headers.get('X-CSRFToken'))
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderWithClient(<App />)

    await submitLogin('alice', 'pw-1234')
    await screen.findByRole('heading', { name: '업로드' })
    await api.post('/echo')

    expect(sent).toEqual(['OLD', 'NEW'])
  })
})
