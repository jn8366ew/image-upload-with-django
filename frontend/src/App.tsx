import { useState } from 'react'
import type { SessionUser } from './api/auth'
import { LoginForm } from './auth/LoginForm'

function App() {
  const [user, setUser] = useState<SessionUser | null>(null)

  return (
    <main>
      <h1>Image Upload</h1>
      {user ? (
        <section>
          <h2>업로드</h2>
          <p>{user.username}</p>
        </section>
      ) : (
        <LoginForm onLoggedIn={setUser} />
      )}
    </main>
  )
}

export default App
