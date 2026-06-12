import type { SessionType } from './api'

// "databases/indexing" → "databases · indexing" for display
export function formatTag(tag: string): string {
  const [category, subtopic] = tag.split('/')
  if (!subtopic) return tag
  return `${category.replace(/_/g, ' ')} · ${subtopic.replace(/-/g, ' ')}`
}

export const SESSION_LABELS: Record<SessionType, string> = {
  screen: 'Screen',
  round: 'Round',
  full_loop: 'Full loop',
}
