import type { InstallationStatus } from '../types'

export function StatusBadge({ status }: { status: InstallationStatus }) {
  return <span className={`badge badge-${status}`}>{status === 'active' ? 'Aktiv' : 'Borttagen'}</span>
}
