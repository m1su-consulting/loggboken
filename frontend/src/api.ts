import type {
  EnvironmentDiffResponse,
  EnvironmentListResponse,
  InstallationSearchResponse,
  SortDir,
  SortField,
} from './types'

export interface SearchInstallationsParams {
  q: string
  environment: string
  sourceType: string
  includeRemoved: boolean
  sortBy: SortField
  sortDir: SortDir
  limit: number
  offset: number
  signal?: AbortSignal
}

export async function searchInstallations(
  params: SearchInstallationsParams,
): Promise<InstallationSearchResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.environment) query.set('environment', params.environment)
  if (params.sourceType) query.set('source_type', params.sourceType)
  if (params.includeRemoved) query.set('include_removed', 'true')
  query.set('sort_by', params.sortBy)
  query.set('sort_dir', params.sortDir)
  query.set('limit', String(params.limit))
  query.set('offset', String(params.offset))

  const response = await fetch(`/api/v1/installations?${query.toString()}`, {
    signal: params.signal,
  })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<InstallationSearchResponse>
}

export async function listEnvironments(signal?: AbortSignal): Promise<EnvironmentListResponse> {
  const response = await fetch('/api/v1/environments?limit=200', { signal })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<EnvironmentListResponse>
}

export interface DiffEnvironmentsParams {
  left: string
  right: string
  sourceType: string
  signal?: AbortSignal
}

export async function diffEnvironments(
  params: DiffEnvironmentsParams,
): Promise<EnvironmentDiffResponse> {
  const query = new URLSearchParams({
    left: params.left,
    right: params.right,
    source_type: params.sourceType,
  })

  const response = await fetch(`/api/v1/environments/diff?${query.toString()}`, {
    signal: params.signal,
  })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<EnvironmentDiffResponse>
}

async function apiErrorDetail(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: string } | null
  return body?.detail ?? `${response.status} ${response.statusText}`
}

export async function deleteInstallation(id: string, apiKey: string): Promise<void> {
  const response = await fetch(`/api/v1/installations/${id}`, {
    method: 'DELETE',
    headers: { 'X-API-Key': apiKey },
  })
  if (!response.ok) {
    throw new Error(await apiErrorDetail(response))
  }
}
