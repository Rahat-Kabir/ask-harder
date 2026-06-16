import type { Scores } from './api'

export const SCORE_MAX = 100

// Map the judge's 1-5 scoring onto a 0-100 scale for display: 1->0, 3->50,
// 5->100. The judge still scores in 1-5 buckets; this mirrors the backend's
// to_hundred so any client-computed average renders on the same scale.
export function toHundred(average: number): number {
  return Math.round(25 * average - 25)
}

// One question's (or answer's) overall on the 0-100 scale.
export function overallOf(scores: Scores): number {
  const values = [
    scores.correctness,
    scores.depth,
    scores.structure,
    scores.communication,
  ]
  const average = values.reduce((sum, value) => sum + value, 0) / values.length
  return toHundred(average)
}
