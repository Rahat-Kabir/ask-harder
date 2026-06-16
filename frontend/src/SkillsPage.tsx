import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type Skill } from './api'
import { formatTag } from './formatTag'
import { LoadingState } from './LoadingState'
import { SCORE_MAX } from './scoring'

function SkillRow({ skill }: { skill: Skill }) {
  // average already arrives on the 0-100 scale, so it is its own bar percentage
  const percent = skill.average
  return (
    <li className="skill-row">
      <Link to={`/skills/${skill.tag}`} className="skill-row-link">
        <div className="skill-row-header">
          <span className="skill-tag">{formatTag(skill.tag)}</span>
          <span className="skill-numbers">
            {skill.trend !== null && (
              <span
                className={
                  skill.trend >= 0 ? 'skill-trend up' : 'skill-trend down'
                }
                title="Change vs your previous interview on this skill"
              >
                {skill.trend >= 0 ? '▲' : '▼'} {Math.abs(Math.round(skill.trend))}
              </span>
            )}
            <span className="skill-average">
              {Math.round(skill.average)} / {SCORE_MAX}
            </span>
          </span>
        </div>
        <div
          className="skill-bar-track"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={SCORE_MAX}
          aria-valuenow={Math.round(skill.average)}
          aria-label={`${skill.tag}: ${Math.round(skill.average)} out of ${SCORE_MAX}`}
        >
          <div className="skill-bar-fill" style={{ width: `${percent}%` }} />
        </div>
        <p className="skill-meta">
          {skill.evaluation_count}{' '}
          {skill.evaluation_count === 1 ? 'judged answer' : 'judged answers'} ·
          view the receipts
        </p>
      </Link>
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
