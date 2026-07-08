import type { SortDir, SortField } from '../types'

interface Props {
  field: SortField
  label: string
  currentSortBy: SortField
  currentSortDir: SortDir
  onSort: (field: SortField) => void
}

export function SortableHeader({ field, label, currentSortBy, currentSortDir, onSort }: Props) {
  const isActive = field === currentSortBy
  return (
    <th
      className={isActive ? 'sortable active' : 'sortable'}
      onClick={() => onSort(field)}
      aria-sort={isActive ? (currentSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <span className="th-content">
        {label}
        <span className="sort-indicator" aria-hidden="true">
          {isActive ? (currentSortDir === 'asc' ? '▲' : '▼') : ''}
        </span>
      </span>
    </th>
  )
}
