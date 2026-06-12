import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from './api'

// drills are deliberately Screen-sized: 3 questions on one skill
export function useDrill() {
  const navigate = useNavigate()
  const [drilling, setDrilling] = useState(false)
  const [drillError, setDrillError] = useState<string | null>(null)

  async function startDrill(tag: string) {
    setDrilling(true)
    setDrillError(null)
    try {
      const created = await api.createInterview({
        practice_tag: tag,
        session_type: 'screen',
      })
      if (created.status === 'preparing') {
        await api.waitUntilInterviewReady(created.id)
      }
      navigate(`/interviews/${created.id}`)
    } catch (err) {
      setDrillError(
        err instanceof ApiError ? err.message : 'Could not start the drill',
      )
      setDrilling(false)
    }
  }

  return { startDrill, drilling, drillError }
}
