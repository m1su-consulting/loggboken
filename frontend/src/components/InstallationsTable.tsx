import { useEffect, useState } from 'react'
import { deleteInstallation, searchInstallations } from '../api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import type { InstallationSearchItem, SortDir, SortField } from '../types'
import { SortableHeader } from './SortableHeader'
import { SourceTypeBadge } from './SourceTypeBadge'
import { StatTile } from './StatTile'
import { StatusBadge } from './StatusBadge'

const PAGE_SIZE = 20
const API_KEY_STORAGE_KEY = 'loggboken-api-key'

const COLUMNS: { field: SortField; label: string }[] = [
  { field: 'environment_name', label: 'Miljö' },
  { field: 'host_or_cluster', label: 'Host / Cluster' },
  { field: 'source_type', label: 'Typ' },
  { field: 'artifact_name', label: 'Artefakt' },
  { field: 'artifact_version', label: 'Version' },
  { field: 'status', label: 'Status' },
  { field: 'last_seen_at', label: 'Uppdaterad' },
]

interface Stats {
  total: number
  rpm: number
  kubernetes: number
  removed: number
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString('sv-SE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function InstallationsTable() {
  const [searchInput, setSearchInput] = useState('')
  const q = useDebouncedValue(searchInput, 300)
  const [environmentInput, setEnvironmentInput] = useState('')
  const environment = useDebouncedValue(environmentInput, 300)
  const [sourceType, setSourceType] = useState('')
  const [includeRemoved, setIncludeRemoved] = useState(false)
  const [sortBy, setSortBy] = useState<SortField>('last_seen_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [offset, setOffset] = useState(0)
  const [refreshKey, setRefreshKey] = useState(0)

  const [apiKey, setApiKey] = useState(() => localStorage.getItem(API_KEY_STORAGE_KEY) ?? '')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const [items, setItems] = useState<InstallationSearchItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    localStorage.setItem(API_KEY_STORAGE_KEY, apiKey)
  }, [apiKey])

  useEffect(() => {
    setOffset(0)
  }, [q, environment, sourceType, includeRemoved, sortBy, sortDir])

  useEffect(() => {
    const controller = new AbortController()
    const base = {
      q,
      environment,
      sortBy: 'last_seen_at' as SortField,
      sortDir: 'desc' as SortDir,
      limit: 1,
      offset: 0,
      signal: controller.signal,
    }

    Promise.all([
      searchInstallations({ ...base, sourceType: '', includeRemoved: false }),
      searchInstallations({ ...base, sourceType: 'rpm', includeRemoved: false }),
      searchInstallations({ ...base, sourceType: 'kubernetes', includeRemoved: false }),
      searchInstallations({ ...base, sourceType: '', includeRemoved: true }),
    ])
      .then(([active, rpm, kubernetes, withRemoved]) => {
        setStats({
          total: active.total,
          rpm: rpm.total,
          kubernetes: kubernetes.total,
          removed: withRemoved.total - active.total,
        })
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setStats(null)
      })

    return () => controller.abort()
  }, [q, environment, refreshKey])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    searchInstallations({
      q,
      environment,
      sourceType,
      includeRemoved,
      sortBy,
      sortDir,
      limit: PAGE_SIZE,
      offset,
      signal: controller.signal,
    })
      .then((data) => {
        setItems(data.items)
        setTotal(data.total)
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [q, environment, sourceType, includeRemoved, sortBy, sortDir, offset, refreshKey])

  function handleSort(field: SortField) {
    if (field === sortBy) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortDir('asc')
    }
  }

  async function handleDelete(item: InstallationSearchItem) {
    if (!apiKey) {
      setDeleteError('Ange en API-nyckel för att kunna ta bort installationer.')
      return
    }
    if (!window.confirm(`Ta bort ${item.artifact_name} från ${item.environment_name}?`)) {
      return
    }

    setDeletingId(item.id)
    setDeleteError(null)
    try {
      await deleteInstallation(item.id, apiKey)
      setRefreshKey((k) => k + 1)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Okänt fel vid borttagning.')
    } finally {
      setDeletingId(null)
    }
  }

  const rangeStart = total === 0 ? 0 : offset + 1
  const rangeEnd = Math.min(offset + PAGE_SIZE, total)

  return (
    <>
      {stats && (
        <div className="stat-row">
          <StatTile label="Aktiva installationer" value={stats.total} accent="var(--color-accent)" />
          <StatTile label="RPM" value={stats.rpm} accent="var(--color-rpm)" />
          <StatTile label="Kubernetes" value={stats.kubernetes} accent="var(--color-kubernetes)" />
          <StatTile label="Borttagna" value={stats.removed} accent="var(--color-text-muted)" />
        </div>
      )}

      <div className="panel">
        <div className="toolbar">
          <input
            type="search"
            className="search-input"
            placeholder="Sök på miljö, host eller artefakt…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <input
            type="search"
            className="environment-input"
            placeholder="Miljö (t.ex. proj1 — matchar proj1 och proj1-xxx)"
            value={environmentInput}
            onChange={(e) => setEnvironmentInput(e.target.value)}
          />
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="">Alla källtyper</option>
            <option value="rpm">RPM</option>
            <option value="kubernetes">Kubernetes</option>
          </select>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={includeRemoved}
              onChange={(e) => setIncludeRemoved(e.target.checked)}
            />
            Visa borttagna
          </label>
          <input
            type="password"
            className="api-key-input"
            placeholder="API-nyckel (för borttagning)"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>

        {error && <p className="error">Kunde inte hämta data: {error}</p>}
        {deleteError && <p className="error">{deleteError}</p>}

        <div className={loading ? 'table-wrap loading' : 'table-wrap'}>
          <table>
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <SortableHeader
                    key={col.field}
                    field={col.field}
                    label={col.label}
                    currentSortBy={sortBy}
                    currentSortDir={sortDir}
                    onSort={handleSort}
                  />
                ))}
                <th>Åtgärd</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.environment_name}</td>
                  <td>{item.host_or_cluster ?? '—'}</td>
                  <td>
                    <SourceTypeBadge sourceType={item.source_type} />
                  </td>
                  <td>{item.artifact_name}</td>
                  <td className="mono">{item.artifact_version}</td>
                  <td>
                    <StatusBadge status={item.status} />
                  </td>
                  <td>{formatDate(item.last_seen_at)}</td>
                  <td>
                    {item.status === 'active' && (
                      <button
                        type="button"
                        className="delete-button"
                        disabled={deletingId === item.id}
                        onClick={() => handleDelete(item)}
                        title={`Ta bort ${item.artifact_name} från ${item.environment_name}`}
                      >
                        {deletingId === item.id ? '…' : 'Ta bort'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!loading && items.length === 0 && !error && (
            <p className="empty-state">Inga träffar.</p>
          )}
        </div>

        <div className="pagination">
          <span>
            {total === 0 ? 'Inga resultat' : `Visar ${rangeStart}–${rangeEnd} av ${total}`}
          </span>
          <div className="pagination-buttons">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ‹ Föregående
            </button>
            <button
              type="button"
              disabled={rangeEnd >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Nästa ›
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
