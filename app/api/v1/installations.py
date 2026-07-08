from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas import (
    IngestRequest,
    IngestResponse,
    InstallationOut,
    InstallationSearchListResponse,
    InstallationSearchOut,
)
from app.auth import ApiKey, check_source_type_access
from app.deps import get_connection
from app.errors import ApiError
from app.ingestion import parse_or_record_failure
from app.repositories import artifacts as artifacts_repo
from app.repositories import environments as environments_repo
from app.repositories import installations as installations_repo

router = APIRouter(tags=["installations"])

SortField = Literal[
    "environment_name",
    "host_or_cluster",
    "source_type",
    "artifact_name",
    "artifact_version",
    "status",
    "first_seen_at",
    "last_seen_at",
]


@router.get("/installations", response_model=InstallationSearchListResponse)
async def search_installations(
    q: str | None = None,
    environment: str | None = None,
    source_type: str | None = None,
    include_removed: bool = False,
    sort_by: SortField = "last_seen_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_connection),
) -> InstallationSearchListResponse:
    """Global sök över alla installationer (över alla miljöer), med fritext
    över miljönamn/host/artefaktnamn, filter på source_type/status, samt
    sortering — det data-underlag frontendens tabell bygger på.

    `environment` är ett separat, precist filter (till skillnad från `q` som
    är fri substr-sökning över flera fält): exakt namnmatchning ELLER
    "prefix-"-gruppering, t.ex. `environment=proj1` matchar både en miljö som
    heter exakt "proj1" och alla som heter "proj1-xxx" (vanligt för
    Kubernetes-namespaces som delar ett projektprefix)."""
    rows, total = await installations_repo.search_installations(
        conn,
        q=q,
        environment=environment,
        source_type=source_type,
        include_removed=include_removed,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    items = [
        InstallationSearchOut(
            id=row["id"],
            environment_id=row["environment_id"],
            environment_name=row["environment_name"],
            host_or_cluster=row["environment_host_or_cluster"],
            source_type=row["environment_source_type"],
            artifact_id=row["artifact_id"],
            artifact_name=row["artifact_name"],
            artifact_version=row["artifact_version"],
            status=row["status"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            removed_at=row["removed_at"],
            source_of_removal=row["source_of_removal"],
        )
        for row in rows
    ]
    return InstallationSearchListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/installations", response_model=IngestResponse, status_code=201)
async def create_installation(
    body: IngestRequest,
    api_key: ApiKey,
    conn: asyncpg.Connection = Depends(get_connection),
) -> IngestResponse:
    check_source_type_access(api_key, body.source_type)
    parsed = await parse_or_record_failure(conn, endpoint="installations", body=body)

    first = parsed[0]
    async with conn.transaction():
        environment = await environments_repo.get_or_create(
            conn,
            name=first.environment_name,
            source_type=first.source_type,
            host_or_cluster=first.host_or_cluster,
            metadata=first.environment_metadata,
        )

        upserted = 0
        for item in parsed:
            artifact = await artifacts_repo.upsert(
                conn,
                name=item.artifact_name,
                version=item.artifact_version,
                source_type=item.source_type,
                raw_data=item.raw_data,
            )
            await installations_repo.upsert_active(
                conn,
                environment_id=environment["id"],
                artifact_id=artifact["id"],
                raw_data=item.raw_data,
            )
            upserted += 1

    return IngestResponse(environment_id=environment["id"], upserted=upserted)


@router.delete("/installations/{installation_id}", response_model=InstallationOut)
async def delete_installation(
    installation_id: UUID,
    api_key: ApiKey,
    conn: asyncpg.Connection = Depends(get_connection),
) -> InstallationOut:
    existing = await installations_repo.get_by_id(conn, installation_id)
    if existing is None:
        raise ApiError(
            status_code=404, error="installation_not_found", detail=str(installation_id)
        )
    environment = await environments_repo.get_by_id(conn, existing["environment_id"])
    check_source_type_access(api_key, environment["source_type"])
    if existing["status"] == "removed":
        raise ApiError(
            status_code=409,
            error="already_removed",
            detail="installationen är redan markerad som borttagen",
        )

    row = await installations_repo.mark_removed_manual(conn, installation_id)
    artifact = await artifacts_repo.get_by_id(conn, row["artifact_id"])
    return InstallationOut(
        id=row["id"],
        environment_id=row["environment_id"],
        artifact_id=row["artifact_id"],
        artifact_name=artifact["name"],
        artifact_version=artifact["version"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        removed_at=row["removed_at"],
        status=row["status"],
        source_of_removal=row["source_of_removal"],
    )
