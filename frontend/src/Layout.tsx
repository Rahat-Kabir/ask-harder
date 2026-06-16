import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api, type User } from './api'

export type LayoutContext = {
  user: User
  onLogout: () => void
}

// the live interview is a focused, full-height workspace — a footer there
// competes with the answer box, so it's suppressed. /interviews/new (intake)
// and /interviews/:id/report are ordinary content pages and keep the footer.
function isInterviewWorkspace(pathname: string): boolean {
  return /^\/interviews\/[^/]+$/.test(pathname) && pathname !== '/interviews/new'
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>ask-harder — a mock interviewer that actually says no.</span>
      <nav className="site-footer-links" aria-label="Footer">
        <Link to="/methodology">How we test the judge</Link>
        <a
          href="https://github.com/Rahat-Kabir/ask-harder"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
        <span className="site-footer-note">Portfolio project · 2026</span>
      </nav>
    </footer>
  )
}

export function Layout({
  user,
  onLogout,
}: {
  user: User
  onLogout: () => void
}) {
  const { pathname } = useLocation()

  async function logout() {
    await api.logout()
    onLogout()
  }

  return (
    <div className="shell">
      <header>
        <Link to="/" className="brand">
          ask-harder
        </Link>
        <nav className="header-nav" aria-label="Main">
          <NavLink to="/interviews" end>
            History
          </NavLink>
          <NavLink to="/skills">Skills</NavLink>
          <NavLink to="/interviews/new">New interview</NavLink>
        </nav>
        <div className="session">
          <Link to="/profile" className="session-email" title={user.email}>
            {user.email}
          </Link>
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <Outlet context={{ user, onLogout } satisfies LayoutContext} />
      {!isInterviewWorkspace(pathname) && <SiteFooter />}
    </div>
  )
}
