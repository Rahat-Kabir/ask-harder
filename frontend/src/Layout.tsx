import { Link, NavLink, Outlet } from 'react-router-dom'
import { api, type User } from './api'

export function Layout({
  user,
  onLogout,
}: {
  user: User
  onLogout: () => void
}) {
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
          <span className="session-email" title={user.email}>
            {user.email}
          </span>
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
