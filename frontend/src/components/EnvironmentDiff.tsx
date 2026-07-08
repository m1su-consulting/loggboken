import { useEffect, useState } from 'react'
import { diffEnvironments } from '../api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import type { EnvironmentDiffResponse, EnvironmentVersion } from '../types'
import { DiffStatusBadge } from './DiffStatusBadge'

function DiffSideCell({ entries }: { entries: EnvironmentVersion[] }) {
  if (entries.length === 0) {
    return <span className="diff-missing">Ej installerad</span>
  }
  return (
    <div className="diff-entries">
      {entries.map((entry) => (
        <div key={entry.environment_name} className="diff-entry">
          <span className="mono">{entry.version}</span>{' '}
          <span className="diff-env-name">({entry.environment_name})</span>
        </div>
      ))}
    </div>
  )
}

interface ResultSectionProps {
  label: string
  left: string
  right: string
  loading: boolean
  error: string | null
  result: EnvironmentDiffResponse | null
}

function DiffResultSection({ label, left, right, loading, error, result }: ResultSectionProps) {
  return (
    <div className="diff-section">
      <h3 className="diff-section-title">{label}</h3>

      {error && <p className="error">Kunde inte hämta diff: {error}</p>}

      <div className={loading ? 'table-wrap loading' : 'table-wrap'}>
        {result && (
          <div className="diff-sides">
            <div>
              <strong>Vänster ({result.left.query}):</strong>{' '}
              {result.left.matched_environments.length > 0
                ? result.left.matched_environments.join(', ')
                : 'inga miljöer hittade'}
            </div>
            <div>
              <strong>Höger ({result.right.query}):</strong>{' '}
              {result.right.matched_environments.length > 0
                ? result.right.matched_environments.join(', ')
                : 'inga miljöer hittade'}
            </div>
          </div>
        )}

        <table>
          <thead>
            <tr>
              <th>Artefakt</th>
              <th>{left}</th>
              <th>{right}</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {result?.items.map((item) => (
              <tr key={item.artifact_name} className={`diff-row-${item.status}`}>
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

        {result && result.items.length === 0 && !error && (
          <p className="empty-state">Inga artefakter av den här typen hittades för någon av miljöerna.</p>
        )}
      </div>
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

export function EnvironmentDiff() {
  const [leftInput, setLeftInput] = useState('')
  const [rightInput, setRightInput] = useState('')
  const left = useDebouncedValue(leftInput, 300)
  const right = useDebouncedValue(rightInput, 300)

  const rpm = useDiff(left, right, 'rpm')
  const kubernetes = useDiff(left, right, 'kubernetes')

  return (
    <div className="panel">
      <div className="toolbar">
        <input
          type="search"
          className="environment-input"
          placeholder="Vänster miljö (t.ex. proj1)"
          value={leftInput}
          onChange={(e) => setLeftInput(e.target.value)}
        />
        <input
          type="search"
          className="environment-input"
          placeholder="Höger miljö (t.ex. proj2)"
          value={rightInput}
          onChange={(e) => setRightInput(e.target.value)}
        />
      </div>

      {!left || !right ? (
        <p className="empty-state">Fyll i två miljöer att jämföra — RPM och Kubernetes visas samtidigt.</p>
      ) : (
        <>
          <DiffResultSection
            label="RPM"
            left={left}
            right={right}
            loading={rpm.loading}
            error={rpm.error}
            result={rpm.result}
          />
          <DiffResultSection
            label="Kubernetes"
            left={left}
            right={right}
            loading={kubernetes.loading}
            error={kubernetes.error}
            result={kubernetes.result}
          />
        </>
      )}
    </div>
  )
}
