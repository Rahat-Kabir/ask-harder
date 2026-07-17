import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api, type User } from './api'

export type LayoutContext = {
  user: User
  onLogout: () => void
}

// avatar + dropdown replacing the bare email in the header — a circle reads as
// "your account" and signals clickability that a raw email string doesn't.
function AccountMenu({
  email,
  onLogout,
}: {
  email: string
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  const [menuPath, setMenuPath] = useState(pathname)

  // close on navigation (e.g. after picking Profile) — adjust during render
  // rather than in an effect, which avoids a cascading re-render
  if (pathname !== menuPath) {
    setMenuPath(pathname)
    setOpen(false)
  }

  // dismiss on outside-click and Escape, only while open
  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="account-menu" ref={containerRef}>
      <button
        type="button"
        className="account-avatar"
        aria-label="Your account"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((previous) => !previous)}
      >
        {email.charAt(0).toUpperCase() || '?'}
      </button>
      {open && (
        <div className="account-dropdown" role="menu">
          <span className="account-email" title={email}>
            {email}
          </span>
          <Link to="/profile" className="account-item" role="menuitem">
            Profile
          </Link>
          <button
            type="button"
            className="account-item"
            role="menuitem"
            onClick={onLogout}
          >
            Log out
          </button>
        </div>
      )}
    </div>
  )
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
        <AccountMenu email={user.email} onLogout={logout} />
      </header>
      <Outlet context={{ user, onLogout } satisfies LayoutContext} />
      {!isInterviewWorkspace(pathname) && <SiteFooter />}
    </div>
  )
}
