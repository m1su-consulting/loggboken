import { useEffect, useRef, useState } from 'react'
import { deleteInstallation, searchInstallations } from '../api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useEnvironmentOptions } from '../hooks/useEnvironmentOptions'
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

// Fler åtgärder (t.ex. export) läggs till här senare — bulk-UI:t (kryssrutor +
// dropdown) är byggt för att redan hantera fler än en åtgärd.
const BULK_ACTIONS: { value: string; label: string }[] = [{ value: 'delete', label: 'Ta bort' }]

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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkAction, setBulkAction] = useState(BULK_ACTIONS[0].value)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkError, setBulkError] = useState<string | null>(null)

  const [items, setItems] = useState<InstallationSearchItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const environmentOptions = useEnvironmentOptions()

  const selectAllRef = useRef<HTMLInputElement>(null)

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
    setSelectedIds(new Set())

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

  const selectableItems = items.filter((item) => item.status === 'active')
  const allSelected =
    selectableItems.length > 0 && selectableItems.every((item) => selectedIds.has(item.id))
  const someSelected = selectableItems.some((item) => selectedIds.has(item.id))

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected && !allSelected
    }
  }, [someSelected, allSelected])

  function handleSort(field: SortField) {
    if (field === sortBy) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortDir('asc')
    }
  }

  function toggleRow(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function toggleSelectAll() {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(selectableItems.map((item) => item.id)))
    }
  }

  async function handleBulkApply() {
    if (selectedIds.size === 0) return

    if (bulkAction === 'delete') {
      if (!apiKey) {
        setBulkError('Ange en API-nyckel för att kunna ta bort installationer.')
        return
      }
      if (!window.confirm(`Ta bort ${selectedIds.size} installation(er)?`)) {
        return
      }

      setBulkBusy(true)
      setBulkError(null)
      const results = await Promise.allSettled(
        [...selectedIds].map((id) => deleteInstallation(id, apiKey))
      )
      const failures = results.filter((r) => r.status === 'rejected').length
      if (failures > 0) {
        setBulkError(`${failures} av ${selectedIds.size} kunde inte tas bort.`)
      }
      setSelectedIds(new Set())
      setRefreshKey((k) => k + 1)
      setBulkBusy(false)
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
            placeholder={
              environmentInput
                ? `Sök inom "${environmentInput}" (host eller artefakt)…`
                : 'Sök på miljö, host eller artefakt…'
            }
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <input
            type="search"
            className="environment-input"
            list="environment-options"
            placeholder="Miljö (t.ex. proj1 — matchar proj1 och proj1-xxx)"
            value={environmentInput}
            onChange={(e) => setEnvironmentInput(e.target.value)}
          />
          <datalist id="environment-options">
            {environmentOptions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
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

        <div className="bulk-bar">
          <span className="bulk-count">
            {selectedIds.size > 0 ? `${selectedIds.size} valda` : 'Inga rader valda'}
          </span>
          <select value={bulkAction} onChange={(e) => setBulkAction(e.target.value)}>
            {BULK_ACTIONS.map((action) => (
              <option key={action.value} value={action.value}>
                {action.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="bulk-apply-button"
            disabled={selectedIds.size === 0 || bulkBusy}
            onClick={handleBulkApply}
          >
            {bulkBusy ? 'Arbetar…' : 'Verkställ'}
          </button>
        </div>

        {error && <p className="error">Kunde inte hämta data: {error}</p>}
        {bulkError && <p className="error">{bulkError}</p>}

        <div className={loading ? 'table-wrap loading' : 'table-wrap'}>
          <table>
            <thead>
              <tr>
                <th className="col-checkbox">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    checked={allSelected}
                    disabled={selectableItems.length === 0}
                    onChange={toggleSelectAll}
                    aria-label="Markera alla rader på sidan"
                  />
                </th>
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
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="col-checkbox">
                    {item.status === 'active' && (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleRow(item.id)}
                        aria-label={`Markera ${item.artifact_name} i ${item.environment_name}`}
                      />
                    )}
                  </td>
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
