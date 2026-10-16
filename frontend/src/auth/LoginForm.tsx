import { type FormEvent, useState } from 'react'
import type { SessionUser } from '../api/auth'
import { useLogin } from './useLogin'

export function LoginForm({ onLoggedIn }: { onLoggedIn: (user: SessionUser) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const loginMutation = useLogin(onLoggedIn)

  function submit(event: FormEvent) {
    event.preventDefault()
    loginMutation.mutate({ username, password })
  }

  return (
    <form onSubmit={submit}>
      <label>
        아이디
        <input value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        비밀번호
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      <button type="submit" disabled={loginMutation.isPending}>
        로그인
      </button>
      {loginMutation.isError && <p role="alert">아이디 또는 비밀번호가 올바르지 않습니다</p>}
    </form>
  )
}
