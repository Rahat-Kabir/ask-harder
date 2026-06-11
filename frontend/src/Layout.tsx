import { Link, Outlet } from 'react-router-dom'
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
        <nav className="header-nav">
          <Link to="/skills">Skills</Link>
          <Link to="/interviews/new">New interview</Link>
        </nav>
        <div className="session">
          <span>{user.email}</span>
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
