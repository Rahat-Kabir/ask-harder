import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { api, type User } from './api'
import { AuthPage } from './AuthPage'
import { Home } from './Home'
import { IntakePage } from './IntakePage'
import { InterviewPage } from './InterviewPage'
import { Layout } from './Layout'
import { ReportPage } from './ReportPage'

type AuthState = 'checking' | { user: User } | 'anonymous'

export default function App() {
  const [auth, setAuth] = useState<AuthState>('checking')

  useEffect(() => {
    api
      .me()
      .then((user) => setAuth({ user }))
      .catch(() => setAuth('anonymous'))
  }, [])

  if (auth === 'checking') return null
  if (auth === 'anonymous') {
    return <AuthPage onAuthed={(user) => setAuth({ user })} />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          element={
            <Layout user={auth.user} onLogout={() => setAuth('anonymous')} />
          }
        >
          <Route index element={<Home />} />
          <Route path="interviews/new" element={<IntakePage />} />
          <Route path="interviews/:id" element={<InterviewPage />} />
          <Route path="interviews/:id/report" element={<ReportPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
