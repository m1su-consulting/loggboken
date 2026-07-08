from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas import ArtifactEnvironmentListResponse, ArtifactEnvironmentOut
from app.deps import get_connection
from app.errors import ApiError
from app.repositories import artifacts as artifacts_repo
from app.repositories import installations as installations_repo

router = APIRouter(tags=["artifacts"])


@router.get(
    "/artifacts/{artifact_id}/environments", response_model=ArtifactEnvironmentListResponse
)
async def list_artifact_environments(
    artifact_id: UUID,
    include_removed: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_connection),
) -> ArtifactEnvironmentListResponse:
    artifact = await artifacts_repo.get_by_id(conn, artifact_id)
    if artifact is None:
        raise ApiError(status_code=404, error="artifact_not_found", detail=str(artifact_id))

    rows, total = await installations_repo.list_environments_for_artifact(
        conn,
        artifact_id=artifact_id,
        include_removed=include_removed,
        limit=limit,
        offset=offset,
    )
    items = [
        ArtifactEnvironmentOut(
            installation_id=row["id"],
            environment_id=row["environment_id"],
            environment_name=row["environment_name"],
            host_or_cluster=row["environment_host_or_cluster"],
            status=row["status"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            removed_at=row["removed_at"],
        )
        for row in rows
    ]
    return ArtifactEnvironmentListResponse(items=items, total=total, limit=limit, offset=offset)
