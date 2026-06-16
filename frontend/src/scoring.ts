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

// Per-dimension 0-100 averages across every scored question — feeds the
// report's summary scorecard so a candidate can see the shape of their
// performance at a glance instead of scrolling every question.
export function dimensionAverages(scoresList: Scores[]): Scores {
  const totals = { correctness: 0, depth: 0, structure: 0, communication: 0 }
  for (const scores of scoresList) {
    totals.correctness += scores.correctness
    totals.depth += scores.depth
    totals.structure += scores.structure
    totals.communication += scores.communication
  }
  const count = scoresList.length || 1
  return {
    correctness: toHundred(totals.correctness / count),
    depth: toHundred(totals.depth / count),
    structure: toHundred(totals.structure / count),
    communication: toHundred(totals.communication / count),
  }
}

// Color band for a 0-100 score — red below 50, amber through 74, green at 75+.
// Drives bar and badge color so weak answers read as weak at a glance.
export function scoreBand(score: number): 'low' | 'mid' | 'high' {
  if (score < 50) return 'low'
  if (score < 75) return 'mid'
  return 'high'
}
