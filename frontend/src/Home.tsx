import { Link } from 'react-router-dom'

export function Home() {
  return (
    <main className="page home-page">
      <h1>The interviewer that actually says no.</h1>
      <p>
        Paste a job description, take a tailored mock interview, and get
        evidence-grounded feedback.
      </p>
      <Link to="/interviews/new" className="primary-button">
        Start interview
      </Link>
    </main>
  )
}
