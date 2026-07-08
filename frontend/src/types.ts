export interface Environment {
  id: string
  name: string
  source_type: string
  host_or_cluster: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface EnvironmentListResponse {
  items: Environment[]
  total: number
  limit: number
  offset: number
}

export type InstallationStatus = 'active' | 'removed'

export interface InstallationSearchItem {
  id: string
  environment_id: string
  environment_name: string
  host_or_cluster: string | null
  source_type: string
  artifact_id: string
  artifact_name: string
  artifact_version: string
  status: InstallationStatus
  first_seen_at: string
  last_seen_at: string
  removed_at: string | null
  source_of_removal: string | null
}

export interface InstallationSearchResponse {
  items: InstallationSearchItem[]
  total: number
  limit: number
  offset: number
}

export type SortField =
  | 'environment_name'
  | 'host_or_cluster'
  | 'source_type'
  | 'artifact_name'
  | 'artifact_version'
  | 'status'
  | 'first_seen_at'
  | 'last_seen_at'

export type SortDir = 'asc' | 'desc'

export type DiffStatus = 'same' | 'different' | 'left_only' | 'right_only'

export interface EnvironmentVersion {
  environment_name: string
  version: string
  host_or_cluster: string | null
}

export interface EnvironmentDiffItem {
  artifact_name: string
  left: EnvironmentVersion[]
  right: EnvironmentVersion[]
  status: DiffStatus
}

export interface EnvironmentDiffSide {
  query: string
  source_type: string
  matched_environments: string[]
}

export interface EnvironmentDiffResponse {
  left: EnvironmentDiffSide
  right: EnvironmentDiffSide
  items: EnvironmentDiffItem[]
  summary: Record<DiffStatus, number>
}
