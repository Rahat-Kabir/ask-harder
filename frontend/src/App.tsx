import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { api, type User } from './api'
import { AuthPage } from './AuthPage'
import { Home } from './Home'
import { IntakePage } from './IntakePage'
import { InterviewPage } from './InterviewPage'
import { Layout } from './Layout'
import { MethodologyPage } from './MethodologyPage'
import { ReportPage } from './ReportPage'
import { SkillsPage } from './SkillsPage'

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

  return (
    <BrowserRouter>
      <Routes>
        {/* public — the eval-results page needs no account */}
        <Route path="methodology" element={<MethodologyPage />} />
        {auth === 'anonymous' ? (
          <Route
            path="*"
            element={<AuthPage onAuthed={(user) => setAuth({ user })} />}
          />
        ) : (
          <Route
            element={
              <Layout user={auth.user} onLogout={() => setAuth('anonymous')} />
            }
          >
            <Route index element={<Home />} />
            <Route path="interviews/new" element={<IntakePage />} />
            <Route path="interviews/:id" element={<InterviewPage />} />
            <Route path="interviews/:id/report" element={<ReportPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        )}
      </Routes>
    </BrowserRouter>
  )
}
