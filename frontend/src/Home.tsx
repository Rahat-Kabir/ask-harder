import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  type InterviewSummary,
  type Quota,
  type Skill,
} from './api'
import { formatTag, SESSION_LABELS } from './formatTag'
import { SCORE_MAX } from './scoring'
import { useDrill } from './useDrill'

type Briefing = {
  skills: Skill[]
  quota: Quota | null
  interviews: InterviewSummary[]
}

// what to do today: a dropping skill beats the merely-weakest one
function suggestedAction(skills: Skill[]): { skill: Skill; reason: string } | null {
  const dropping = skills
    .filter((skill) => skill.trend !== null && skill.trend < 0)
    .sort((a, b) => (a.trend ?? 0) - (b.trend ?? 0))[0]
  if (dropping) {
    return {
      skill: dropping,
      reason: `${formatTag(dropping.tag)} dropped ▼${Math.abs(
        Math.round(dropping.trend ?? 0),
      )} since your previous interview`,
    }
  }
  const weakest = skills[0]
  if (weakest) {
    return {
      skill: weakest,
      reason: `your weakest area is ${formatTag(weakest.tag)} (${Math.round(weakest.average)} / ${SCORE_MAX})`,
    }
  }
  return null
}

function BriefingSection({ skills, quota, interviews }: Briefing) {
  const { startDrill, drilling, drillError } = useDrill()
  const lastReport = interviews.find(
    (interview) =>
      interview.status === 'complete' && interview.overall_score !== null,
  )
  const weakest = skills[0]
  const action = suggestedAction(skills)

  return (
    <section className="home-briefing">
      <h2>Today</h2>
      <div className="score-grid profile-stats">
        {quota && (
          <div>
            <span>Interviews left today</span>
            <strong>
              {quota.remaining} of {quota.limit}
            </strong>
          </div>
        )}
        {lastReport && (
          <div>
            <span>Last report</span>
            <strong>
              <Link to={`/interviews/${lastReport.id}/report`}>
                {lastReport.overall_score !== null
                  ? Math.round(lastReport.overall_score)
                  : null}{' '}
                / {SCORE_MAX} ·{' '}
                {lastReport.practice_tag
                  ? 'Practice'
                  : SESSION_LABELS[lastReport.session_type]}
              </Link>
            </strong>
          </div>
        )}
        {weakest && (
          <div>
            <span>Weakest skill</span>
            <strong>
              <Link to={`/skills/${weakest.tag}`}>
                {formatTag(weakest.tag)} · {Math.round(weakest.average)}
                {weakest.trend !== null && (
                  <span
                    className={
                      weakest.trend >= 0 ? 'skill-trend up' : 'skill-trend down'
                    }
                  >
                    {' '}
                    {weakest.trend >= 0 ? '▲' : '▼'}
                    {Math.abs(Math.round(weakest.trend))}
                  </span>
                )}
              </Link>
            </strong>
          </div>
        )}
      </div>

      {action && (
        <div className="home-action">
          <p>Suggestion: {action.reason} — drill it.</p>
          {drillError && <p className="error">{drillError}</p>}
          <button
            type="button"
            className="secondary-button"
            onClick={() => startDrill(action.skill.tag)}
            disabled={drilling}
          >
            {drilling
              ? 'Building your drill…'
              : `Drill ${formatTag(action.skill.tag)}`}
          </button>
        </div>
      )}

      <p className="home-footer-link">
        <Link to="/skills">All skills</Link> ·{' '}
        <Link to="/interviews">History</Link>
      </p>
    </section>
  )
}

export function Home() {
  const [briefing, setBriefing] = useState<Briefing | null>(null)

  useEffect(() => {
    Promise.all([api.getSkills(), api.getQuota(), api.listInterviews()])
      .then(([skillsData, quota, interviewsData]) =>
        setBriefing({
          skills: skillsData.skills,
          quota,
          interviews: interviewsData.interviews,
        }),
      )
      // the briefing is additive — the hero works without it
      .catch(() => setBriefing(null))
  }, [])

  const hasActivity = briefing !== null && briefing.interviews.length > 0

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

      {hasActivity && (
        <BriefingSection
          skills={briefing.skills}
          quota={briefing.quota}
          interviews={briefing.interviews}
        />
      )}
    </main>
  )
}
