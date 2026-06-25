import type { EvidenceItem } from './api'

// Grounded judge observations, each marked as credit (+) or gap (−). The
// polarity is the point: without it a list of neutral quotes reads as all
// praise next to a low score. Shared by the report and skill-detail pages.
export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  return (
    <ul className="evidence-list">
      {evidence.map((item) => (
        <li
          key={item.claim}
          className={`evidence-item ${item.supports ? 'evidence-credit' : 'evidence-gap'}`}
        >
          <span
            className="evidence-mark"
            aria-label={item.supports ? 'Earned credit' : 'Cost you'}
          >
            {item.supports ? '+' : '–'}
          </span>
          <div className="evidence-body">
            <strong>{item.claim}</strong>
            <blockquote>{item.quote}</blockquote>
          </div>
        </li>
      ))}
    </ul>
  )
}
