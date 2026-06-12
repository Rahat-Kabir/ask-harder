import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type Skill } from './api'
import { LoadingState } from './LoadingState'

function formatTag(tag: string): string {
  const [category, subtopic] = tag.split('/')
  if (!subtopic) return tag
  return `${category.replace(/_/g, ' ')} · ${subtopic.replace(/-/g, ' ')}`
}

function SkillRow({ skill }: { skill: Skill }) {
  const percent = (skill.average / 5) * 100
  return (
    <li className="skill-row">
      <div className="skill-row-header">
        <span className="skill-tag">{formatTag(skill.tag)}</span>
        <span className="skill-average">{skill.average.toFixed(1)} / 5</span>
      </div>
      <div
        className="skill-bar-track"
        role="meter"
        aria-valuemin={1}
        aria-valuemax={5}
        aria-valuenow={skill.average}
        aria-label={`${skill.tag}: ${skill.average.toFixed(1)} out of 5`}
      >
        <div className="skill-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <p className="skill-meta">
        {skill.evaluation_count}{' '}
        {skill.evaluation_count === 1 ? 'judged answer' : 'judged answers'}
      </p>
    </li>
  )
}

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getSkills()
      .then((data) => setSkills(data.skills))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Could not load skills'),
      )
  }, [])

  if (error) {
    return (
      <main className="page skills-page">
        <p className="error">{error}</p>
        <Link to="/">Back home</Link>
      </main>
    )
  }

  if (!skills) {
    return (
      <main className="page skills-page">
        <LoadingState label="Loading skills…" />
      </main>
    )
  }

  return (
    <main className="page skills-page">
      <div className="report-header">
        <h1>Skill tracking</h1>
        <p className="lede">
          Averages from your judged answers, weakest first. More interviews sharpen
          the picture.
        </p>
      </div>

      {skills.length === 0 ? (
        <div className="skills-empty">
          <p>Finish an interview to start tracking your skills.</p>
          <Link to="/interviews/new" className="primary-button">
            Start interview
          </Link>
        </div>
      ) : (
        <ul className="skill-list">
          {skills.map((skill) => (
            <SkillRow key={skill.tag} skill={skill} />
          ))}
        </ul>
      )}
    </main>
  )
}
