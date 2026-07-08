from typing import Any
from uuid import UUID

import asyncpg


async def get_by_id(conn: asyncpg.Connection, installation_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM installations WHERE id = $1", installation_id)


async def upsert_active(
    conn: asyncpg.Connection,
    *,
    environment_id: UUID,
    artifact_id: UUID,
    raw_data: dict[str, Any] | None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO installations (environment_id, artifact_id, raw_data)
        VALUES ($1, $2, $3)
        ON CONFLICT (environment_id, artifact_id)
        DO UPDATE SET
            last_seen_at = now(),
            status = 'active',
            removed_at = NULL,
            source_of_removal = NULL,
            raw_data = EXCLUDED.raw_data
        RETURNING *
        """,
        environment_id,
        artifact_id,
        raw_data or {},
    )


async def mark_removed_by_snapshot_diff(
    conn: asyncpg.Connection, *, environment_id: UUID, active_artifact_ids: list[UUID]
) -> int:
    if active_artifact_ids:
        result = await conn.execute(
            """
            UPDATE installations
            SET status = 'removed', removed_at = now(), source_of_removal = 'snapshot_diff'
            WHERE environment_id = $1 AND status = 'active' AND artifact_id != ALL($2::uuid[])
            """,
            environment_id,
            active_artifact_ids,
        )
    else:
        result = await conn.execute(
            """
            UPDATE installations
            SET status = 'removed', removed_at = now(), source_of_removal = 'snapshot_diff'
            WHERE environment_id = $1 AND status = 'active'
            """,
            environment_id,
        )
    return int(result.split()[-1])


async def mark_removed_manual(
    conn: asyncpg.Connection, installation_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE installations
        SET status = 'removed', removed_at = now(), source_of_removal = 'manual'
        WHERE id = $1
        RETURNING *
        """,
        installation_id,
    )


async def list_for_environment(
    conn: asyncpg.Connection,
    *,
    environment_id: UUID,
    include_removed: bool,
    artifact_name: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    status_clause = "" if include_removed else "AND i.status = 'active'"

    params: list[Any] = [environment_id]
    name_clause = ""
    if artifact_name is not None:
        params.append(artifact_name)
        name_clause = f"AND a.name = ${len(params)}"

    total = await conn.fetchval(
        f"""
        SELECT count(*)
        FROM installations i
        JOIN artifacts a ON a.id = i.artifact_id
        WHERE i.environment_id = $1 {status_clause} {name_clause}
        """,
        *params,
    )
    rows = await conn.fetch(
        f"""
        SELECT i.*, a.name AS artifact_name, a.version AS artifact_version
        FROM installations i
        JOIN artifacts a ON a.id = i.artifact_id
        WHERE i.environment_id = $1 {status_clause} {name_clause}
        ORDER BY i.first_seen_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params,
        limit,
        offset,
    )
    return rows, total


async def list_environments_for_artifact(
    conn: asyncpg.Connection,
    *,
    artifact_id: UUID,
    include_removed: bool,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    status_clause = "" if include_removed else "AND i.status = 'active'"

    total = await conn.fetchval(
        f"SELECT count(*) FROM installations i WHERE i.artifact_id = $1 {status_clause}",
        artifact_id,
    )
    rows = await conn.fetch(
        f"""
        SELECT i.*, e.name AS environment_name, e.host_or_cluster AS environment_host_or_cluster
        FROM installations i
        JOIN environments e ON e.id = i.environment_id
        WHERE i.artifact_id = $1 {status_clause}
        ORDER BY i.first_seen_at DESC
        LIMIT $2 OFFSET $3
        """,
        artifact_id,
        limit,
        offset,
    )
    return rows, total


# whitelist mapping sort_by -> actual SQL expression, so the value is never
# interpolated directly into the query string
SEARCH_SORT_COLUMNS = {
    "environment_name": "e.name",
    "host_or_cluster": "e.host_or_cluster",
    "source_type": "e.source_type",
    "artifact_name": "a.name",
    "artifact_version": "a.version",
    "status": "i.status",
    "first_seen_at": "i.first_seen_at",
    "last_seen_at": "i.last_seen_at",
}


async def search_installations(
    conn: asyncpg.Connection,
    *,
    q: str | None,
    environment: str | None = None,
    source_type: str | None,
    include_removed: bool,
    sort_by: str,
    sort_dir: str,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    conditions: list[str] = []
    params: list[Any] = []

    if not include_removed:
        conditions.append("i.status = 'active'")

    if source_type is not None:
        params.append(source_type)
        conditions.append(f"e.source_type = ${len(params)}")

    if q:
        params.append(f"%{q}%")
        idx = len(params)
        conditions.append(
            f"(e.name ILIKE ${idx} OR e.host_or_cluster ILIKE ${idx} OR a.name ILIKE ${idx})"
        )

    if environment:
        # exact match or "prefix-" boundary (e.g. "proj1" matches "proj1" and
        # "proj1-anything", but not "proj10-anything") — used to browse a
        # whole group of Kubernetes namespaces that share a project prefix
        params.append(environment)
        exact_idx = len(params)
        params.append(f"{environment}-%")
        prefix_idx = len(params)
        conditions.append(f"(e.name = ${exact_idx} OR e.name LIKE ${prefix_idx})")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order_column = SEARCH_SORT_COLUMNS.get(sort_by, "i.last_seen_at")
    order_dir = "ASC" if sort_dir == "asc" else "DESC"

    total = await conn.fetchval(
        f"""
        SELECT count(*)
        FROM installations i
        JOIN artifacts a ON a.id = i.artifact_id
        JOIN environments e ON e.id = i.environment_id
        {where_clause}
        """,
        *params,
    )
    rows = await conn.fetch(
        f"""
        SELECT i.*, a.name AS artifact_name, a.version AS artifact_version,
               e.name AS environment_name, e.host_or_cluster AS environment_host_or_cluster,
               e.source_type AS environment_source_type
        FROM installations i
        JOIN artifacts a ON a.id = i.artifact_id
        JOIN environments e ON e.id = i.environment_id
        {where_clause}
        ORDER BY {order_column} {order_dir}, i.id
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params,
        limit,
        offset,
    )
    return rows, total


async def get_active_installations_for_environment_group(
    conn: asyncpg.Connection, *, environment: str, source_type: str
) -> tuple[list[str], list[tuple[str, str, str, str | None]]]:
    """Resolves `environment` the same way search_installations' `environment`
    filter does (exact name or "environment-" prefix group) and returns the
    matching environment names plus every active (artifact_name, version,
    environment_name, host_or_cluster) tuple across all of them — the raw
    material for a two-sided diff that can still show which specific
    namespace/host an artifact came from."""
    env_rows = await conn.fetch(
        """
        SELECT name FROM environments
        WHERE source_type = $1 AND (name = $2 OR name LIKE $3)
        ORDER BY name
        """,
        source_type,
        environment,
        f"{environment}-%",
    )
    matching_names = [row["name"] for row in env_rows]

    rows = await conn.fetch(
        """
        SELECT a.name AS artifact_name, a.version AS artifact_version,
               e.name AS environment_name, e.host_or_cluster AS host_or_cluster
        FROM installations i
        JOIN artifacts a ON a.id = i.artifact_id
        JOIN environments e ON e.id = i.environment_id
        WHERE e.source_type = $1 AND (e.name = $2 OR e.name LIKE $3) AND i.status = 'active'
        """,
        source_type,
        environment,
        f"{environment}-%",
    )
    installations = [
        (row["artifact_name"], row["artifact_version"], row["environment_name"], row["host_or_cluster"])
        for row in rows
    ]
    return matching_names, installations
