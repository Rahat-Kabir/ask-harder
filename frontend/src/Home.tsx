import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Skill } from './api'

function formatTag(tag: string): string {
  const [, subtopic] = tag.split('/')
  return (subtopic ?? tag).replace(/-/g, ' ')
}

export function Home() {
  const [weakest, setWeakest] = useState<Skill[]>([])

  useEffect(() => {
    api
      .getSkills()
      .then((data) => setWeakest(data.skills.slice(0, 3)))
      .catch(() => setWeakest([]))
  }, [])

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

      <p className="home-footer-link">
        <Link to="/methodology">How we test the judge</Link>
      </p>

      {weakest.length > 0 && (
        <section className="home-skills-teaser">
          <h2>Weakest areas</h2>
          <ul>
            {weakest.map((skill) => (
              <li key={skill.tag}>
                {formatTag(skill.tag)} — {skill.average.toFixed(1)} / 5
              </li>
            ))}
          </ul>
          <Link to="/skills">View all skills</Link>
        </section>
      )}
    </main>
  )
}
