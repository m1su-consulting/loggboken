import type { DiffStatus } from '../types'

const LABELS: Record<DiffStatus, string> = {
  same: 'Samma',
  different: 'Olika version',
  left_only: 'Bara vänster',
  right_only: 'Bara höger',
}

export function DiffStatusBadge({ status }: { status: DiffStatus }) {
  return <span className={`badge badge-diff-${status}`}>{LABELS[status]}</span>
}
