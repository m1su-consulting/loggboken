import type { CSSProperties } from 'react'

interface Props {
  label: string
  value: number | string
  accent?: string
}

export function StatTile({ label, value, accent }: Props) {
  return (
    <div
      className="stat-tile"
      style={accent ? ({ '--stat-accent': accent } as CSSProperties) : undefined}
    >
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
