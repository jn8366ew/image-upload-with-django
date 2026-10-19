import { LoginForm } from './auth/LoginForm'
import { useLogout } from './auth/useLogout'
import { useSession } from './auth/useSession'
import { AttachmentList } from './features/attachments/AttachmentList'
import { useRefreshAttachments } from './features/attachments/useAttachments'
import { UploadPanel } from './features/upload/UploadPanel'

function App() {
  const { user, isPending, setUser } = useSession()
  const { logout, isPending: isLoggingOut } = useLogout(() => setUser(null))
  const refreshAttachments = useRefreshAttachments()

  return (
    <main>
      <header className="header">
        <h1>Image Upload</h1>
        {user && (
          <>
            <p>{user.username}</p>
            <button type="button" onClick={logout} disabled={isLoggingOut}>
              로그아웃
            </button>
          </>
        )}
      </header>
      {isPending ? null : user ? (
        <>
          <section className="card">
            <h2>업로드</h2>
            <UploadPanel onCompleted={refreshAttachments} />
          </section>
          <section className="card">
            <h2>내 이미지</h2>
            <AttachmentList />
          </section>
        </>
      ) : (
        <LoginForm onLoggedIn={setUser} />
      )}
    </main>
  )
}

export default App
