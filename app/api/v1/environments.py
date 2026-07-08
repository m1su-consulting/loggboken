from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas import (
    EnvironmentDiffItem,
    EnvironmentDiffResponse,
    EnvironmentDiffSide,
    EnvironmentListResponse,
    EnvironmentOut,
    IngestRequest,
    InstallationListResponse,
    InstallationOut,
    SnapshotResponse,
)
from app.auth import ApiKey, check_source_type_access
from app.deps import get_connection
from app.diffing import compute_environment_diff
from app.errors import ApiError
from app.ingestion import parse_or_record_failure, record_and_raise
from app.repositories import artifacts as artifacts_repo
from app.repositories import environments as environments_repo
from app.repositories import installations as installations_repo

router = APIRouter(tags=["environments"])


@router.get("/environments", response_model=EnvironmentListResponse)
async def list_environments(
    source_type: str | None = None,
    host_or_cluster: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_connection),
) -> EnvironmentListResponse:
    rows, total = await environments_repo.list_environments(
        conn,
        source_type=source_type,
        host_or_cluster=host_or_cluster,
        limit=limit,
        offset=offset,
    )
    return EnvironmentListResponse(
        items=[EnvironmentOut(**dict(row)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _run_snapshot(
    conn: asyncpg.Connection,
    *,
    environment: asyncpg.Record,
    body: IngestRequest,
    api_key: ApiKey,
) -> SnapshotResponse:
    environment_id = environment["id"]

    check_source_type_access(api_key, body.source_type)

    if body.source_type != environment["source_type"]:
        await record_and_raise(
            conn,
            endpoint="snapshot",
            body=body,
            api_error=ApiError(
                status_code=400,
                error="source_type_mismatch",
                detail=(
                    f"miljön är av typen '{environment['source_type']}', "
                    f"men payloaden angav '{body.source_type}'"
                ),
            ),
            environment_id=environment_id,
        )

    parsed = await parse_or_record_failure(
        conn,
        endpoint="snapshot",
        body=body,
        environment_id=environment_id,
        allow_empty=True,
    )

    acquired = await environments_repo.try_acquire_snapshot_lock(conn, environment_id)
    if not acquired:
        raise ApiError(
            status_code=409,
            error="snapshot_in_progress",
            detail="en snapshot för denna miljö pågår redan",
        )

    try:
        async with conn.transaction():
            active_artifact_ids: list[UUID] = []
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
                    environment_id=environment_id,
                    artifact_id=artifact["id"],
                    raw_data=item.raw_data,
                )
                active_artifact_ids.append(artifact["id"])

            removed = await installations_repo.mark_removed_by_snapshot_diff(
                conn, environment_id=environment_id, active_artifact_ids=active_artifact_ids
            )
    finally:
        await environments_repo.release_snapshot_lock(conn, environment_id)

    return SnapshotResponse(
        environment_id=environment_id, active=len(active_artifact_ids), removed=removed
    )


@router.post("/environments/{environment_id}/snapshot", response_model=SnapshotResponse)
async def snapshot_environment(
    environment_id: UUID,
    body: IngestRequest,
    api_key: ApiKey,
    conn: asyncpg.Connection = Depends(get_connection),
) -> SnapshotResponse:
    environment = await environments_repo.get_by_id(conn, environment_id)
    if environment is None:
        raise ApiError(status_code=404, error="environment_not_found", detail=str(environment_id))

    return await _run_snapshot(conn, environment=environment, body=body, api_key=api_key)


@router.post(
    "/environments/by-name/{name}/snapshot", response_model=SnapshotResponse
)
async def snapshot_environment_by_name(
    name: str,
    source_type: str,
    body: IngestRequest,
    api_key: ApiKey,
    conn: asyncpg.Connection = Depends(get_connection),
) -> SnapshotResponse:
    """Genväg för källsystem som bara känner sitt eget namn (t.ex. ett
    nattligt cron-jobb för en RPM-host eller k8s-namespace) och inte vill
    behöva cacha/slå upp UUID:t separat innan varje snapshot."""
    environment = await environments_repo.get_by_name_and_source_type(conn, name, source_type)
    if environment is None:
        raise ApiError(
            status_code=404,
            error="environment_not_found",
            detail=f"ingen miljö med name='{name}' och source_type='{source_type}'",
        )

    return await _run_snapshot(conn, environment=environment, body=body, api_key=api_key)


async def _list_installations(
    conn: asyncpg.Connection,
    *,
    environment_id: UUID,
    include_removed: bool,
    artifact_name: str | None,
    limit: int,
    offset: int,
) -> InstallationListResponse:
    rows, total = await installations_repo.list_for_environment(
        conn,
        environment_id=environment_id,
        include_removed=include_removed,
        artifact_name=artifact_name,
        limit=limit,
        offset=offset,
    )
    items = [
        InstallationOut(
            id=row["id"],
            environment_id=row["environment_id"],
            artifact_id=row["artifact_id"],
            artifact_name=row["artifact_name"],
            artifact_version=row["artifact_version"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            removed_at=row["removed_at"],
            status=row["status"],
            source_of_removal=row["source_of_removal"],
        )
        for row in rows
    ]
    return InstallationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/environments/{environment_id}/installations", response_model=InstallationListResponse
)
async def list_environment_installations(
    environment_id: UUID,
    include_removed: bool = False,
    artifact_name: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_connection),
) -> InstallationListResponse:
    environment = await environments_repo.get_by_id(conn, environment_id)
    if environment is None:
        raise ApiError(status_code=404, error="environment_not_found", detail=str(environment_id))

    return await _list_installations(
        conn,
        environment_id=environment_id,
        include_removed=include_removed,
        artifact_name=artifact_name,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/environments/by-name/{name}/installations", response_model=InstallationListResponse
)
async def list_environment_installations_by_name(
    name: str,
    source_type: str,
    include_removed: bool = False,
    artifact_name: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_connection),
) -> InstallationListResponse:
    """Genväg symmetrisk med snapshot-by-name: sök ut installationer via
    (environment name, source_type) + valfritt artifact_name, utan att
    behöva känna till eller slå upp miljöns UUID separat."""
    environment = await environments_repo.get_by_name_and_source_type(conn, name, source_type)
    if environment is None:
        raise ApiError(
            status_code=404,
            error="environment_not_found",
            detail=f"ingen miljö med name='{name}' och source_type='{source_type}'",
        )

    return await _list_installations(
        conn,
        environment_id=environment["id"],
        include_removed=include_removed,
        artifact_name=artifact_name,
        limit=limit,
        offset=offset,
    )


@router.get("/environments/diff", response_model=EnvironmentDiffResponse)
async def diff_environments(
    left: str,
    right: str,
    source_type: str,
    conn: asyncpg.Connection = Depends(get_connection),
) -> EnvironmentDiffResponse:
    """Ställer två miljöer (eller projektprefix-grupper, se `environment`-
    filtret på `GET /installations`) sida vid sida och visar skillnader:
    vilka artefakter finns bara på ena sidan, vilka finns på båda men i olika
    version, och vilka är identiska."""
    left_names, left_installations = (
        await installations_repo.get_active_installations_for_environment_group(
            conn, environment=left, source_type=source_type
        )
    )
    right_names, right_installations = (
        await installations_repo.get_active_installations_for_environment_group(
            conn, environment=right, source_type=source_type
        )
    )

    items = compute_environment_diff(left_installations, right_installations)
    summary = {"same": 0, "different": 0, "left_only": 0, "right_only": 0}
    for item in items:
        summary[item["status"]] += 1

    return EnvironmentDiffResponse(
        left=EnvironmentDiffSide(
            query=left, source_type=source_type, matched_environments=left_names
        ),
        right=EnvironmentDiffSide(
            query=right, source_type=source_type, matched_environments=right_names
        ),
        items=[EnvironmentDiffItem(**item) for item in items],
        summary=summary,
    )
