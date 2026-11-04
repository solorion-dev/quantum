import { Badge } from '@dsect/ui'
import type { GitHubLink, SyncInfo, TrackerItem } from '../types'
import { isStale, needsTriage, priorityLabel, priorityTone, syncLabel } from '../lib/meta'

/** GitHub link badge with sync dot. Colour is never the only signal: state is in text + title. */
export function GitHubBadge({ github, sync, compact = false }: { github: GitHubLink | null; sync: SyncInfo; compact?: boolean }) {
  if (!github) return null
  const kind = github.type === 'pull_request' ? 'PR' : 'Issue'
  const text = `${kind} #${github.number}`
  const desc = `GitHub ${kind.toLowerCase()} ${github.repo}#${github.number}, ${syncLabel[sync.state]}${sync.error ? `: ${sync.error}` : ''}`
  return (
    <span className={`tb-gh tb-gh--${sync.state}`} title={desc}>
      <span className={`tb-sync-dot tb-sync-dot--${sync.state}`} aria-hidden="true" />
      <span aria-hidden="true">{text}</span>
      <span className="sr-only">{desc}</span>
      {!compact && sync.state !== 'synced' && <span className="tb-gh-state" aria-hidden="true">{syncLabel[sync.state]}</span>}
    </span>
  )
}

export function PriorityBadge({ p }: { p: TrackerItem['priority'] }) {
  return <Badge size="sm" tone={priorityTone[p]}>{priorityLabel[p]}</Badge>
}

export function FlagBadges({ item }: { item: TrackerItem }) {
  return (
    <>
      {isStale(item) && <span className="tb-flag" title="No update in 14 days">Stale</span>}
      {needsTriage(item) && <span className="tb-flag" title="No assignee, no priority, or backlog with no labels">Needs triage</span>}
    </>
  )
}
