from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source_type: str = Field(min_length=1)
    data: dict[str, Any] = Field(min_length=1)


class IngestResponse(BaseModel):
    environment_id: UUID
    upserted: int


class SnapshotResponse(BaseModel):
    environment_id: UUID
    active: int
    removed: int


class EnvironmentOut(BaseModel):
    id: UUID
    name: str
    source_type: str
    host_or_cluster: str | None
    metadata: dict[str, Any] | None
    created_at: datetime


class EnvironmentListResponse(BaseModel):
    items: list[EnvironmentOut]
    total: int
    limit: int
    offset: int


class InstallationOut(BaseModel):
    id: UUID
    environment_id: UUID
    artifact_id: UUID
    artifact_name: str
    artifact_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    removed_at: datetime | None
    status: str
    source_of_removal: str | None


class InstallationListResponse(BaseModel):
    items: list[InstallationOut]
    total: int
    limit: int
    offset: int


class InstallationSearchOut(BaseModel):
    id: UUID
    environment_id: UUID
    environment_name: str
    host_or_cluster: str | None
    source_type: str
    artifact_id: UUID
    artifact_name: str
    artifact_version: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    removed_at: datetime | None
    source_of_removal: str | None


class InstallationSearchListResponse(BaseModel):
    items: list[InstallationSearchOut]
    total: int
    limit: int
    offset: int


class ArtifactEnvironmentOut(BaseModel):
    installation_id: UUID
    environment_id: UUID
    environment_name: str
    host_or_cluster: str | None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    removed_at: datetime | None


class ArtifactEnvironmentListResponse(BaseModel):
    items: list[ArtifactEnvironmentOut]
    total: int
    limit: int
    offset: int


class EnvironmentVersion(BaseModel):
    environment_name: str
    version: str
    host_or_cluster: str | None = None


class EnvironmentDiffItem(BaseModel):
    artifact_name: str
    left: list[EnvironmentVersion]
    right: list[EnvironmentVersion]
    status: Literal["same", "different", "left_only", "right_only"]


class EnvironmentDiffSide(BaseModel):
    query: str
    source_type: str
    matched_environments: list[str]


class EnvironmentDiffResponse(BaseModel):
    left: EnvironmentDiffSide
    right: EnvironmentDiffSide
    items: list[EnvironmentDiffItem]
    summary: dict[str, int]
