export function SourceTypeBadge({ sourceType }: { sourceType: string }) {
  return <span className={`badge badge-source badge-source-${sourceType}`}>{sourceType}</span>
}
