import { useEffect, useState } from 'react'
import { diffEnvironments } from '../api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useEnvironmentOptions } from '../hooks/useEnvironmentOptions'
import type { EnvironmentDiffResponse, EnvironmentVersion } from '../types'
import { DiffStatusBadge } from './DiffStatusBadge'
import { SourceTypeBadge } from './SourceTypeBadge'

function DiffSideCell({ entries }: { entries: EnvironmentVersion[] }) {
  if (entries.length === 0) {
    return <span className="diff-missing">Ej installerad</span>
  }
  return (
    <div className="diff-entries">
      {entries.map((entry) => (
        <div key={entry.environment_name} className="diff-entry">
          <span className="mono">{entry.version}</span>{' '}
          <span className="diff-env-name">
            ({entry.environment_name}
            {entry.host_or_cluster ? ` · ${entry.host_or_cluster}` : ''})
          </span>
        </div>
      ))}
    </div>
  )
}

function useDiff(left: string, right: string, sourceType: string) {
  const [result, setResult] = useState<EnvironmentDiffResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!left || !right) {
      setResult(null)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)

    diffEnvironments({ left, right, sourceType, signal: controller.signal })
      .then(setResult)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [left, right, sourceType])

  return { result, loading, error }
}

function matchedSummary(label: string, side: EnvironmentDiffResponse['left'] | undefined) {
  if (!side) return null
  const matches = side.matched_environments.length > 0 ? side.matched_environments.join(', ') : 'inga miljöer hittade'
  return (
    <span>
      <strong>{label}:</strong> {matches}
    </span>
  )
}

export function EnvironmentDiff() {
  const [leftInput, setLeftInput] = useState('')
  const [rightInput, setRightInput] = useState('')
  const left = useDebouncedValue(leftInput, 300)
  const right = useDebouncedValue(rightInput, 300)
  const environmentOptions = useEnvironmentOptions()

  const rpm = useDiff(left, right, 'rpm')
  const kubernetes = useDiff(left, right, 'kubernetes')

  const loading = rpm.loading || kubernetes.loading
  const error = rpm.error ?? kubernetes.error

  const rows = [
    ...(rpm.result?.items.map((item) => ({ ...item, sourceType: 'rpm' as const })) ?? []),
    ...(kubernetes.result?.items.map((item) => ({ ...item, sourceType: 'kubernetes' as const })) ?? []),
  ]

  const hasResults = rpm.result !== null || kubernetes.result !== null

  return (
    <div className="panel">
      <div className="toolbar">
        <input
          type="search"
          className="environment-input"
          list="environment-options-diff"
          placeholder="Vänster miljö (t.ex. proj1)"
          value={leftInput}
          onChange={(e) => setLeftInput(e.target.value)}
        />
        <input
          type="search"
          className="environment-input"
          list="environment-options-diff"
          placeholder="Höger miljö (t.ex. proj2)"
          value={rightInput}
          onChange={(e) => setRightInput(e.target.value)}
        />
        <datalist id="environment-options-diff">
          {environmentOptions.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>

      {!left || !right ? (
        <p className="empty-state">Fyll i två miljöer att jämföra — RPM och Kubernetes visas samtidigt.</p>
      ) : (
        <>
          {error && <p className="error">Kunde inte hämta diff: {error}</p>}

          {hasResults && (
            <div className="diff-sides">
              <div>
                {matchedSummary('Vänster RPM', rpm.result?.left)} · {matchedSummary('Vänster Kubernetes', kubernetes.result?.left)}
              </div>
              <div>
                {matchedSummary('Höger RPM', rpm.result?.right)} · {matchedSummary('Höger Kubernetes', kubernetes.result?.right)}
              </div>
            </div>
          )}

          <div className={loading ? 'table-wrap loading' : 'table-wrap'}>
            <table>
              <thead>
                <tr>
                  <th>Typ</th>
                  <th>Artefakt</th>
                  <th>{left}</th>
                  <th>{right}</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={`${item.sourceType}-${item.artifact_name}`} className={`diff-row-${item.status}`}>
                    <td>
                      <SourceTypeBadge sourceType={item.sourceType} />
                    </td>
                    <td>{item.artifact_name}</td>
                    <td>
                      <DiffSideCell entries={item.left} />
                    </td>
                    <td>
                      <DiffSideCell entries={item.right} />
                    </td>
                    <td>
                      <DiffStatusBadge status={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {hasResults && rows.length === 0 && !error && (
              <p className="empty-state">Inga artefakter hittades för någon av miljöerna.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
