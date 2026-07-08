from typing import Any
from uuid import UUID

import asyncpg


async def get_by_id(conn: asyncpg.Connection, environment_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM environments WHERE id = $1", environment_id)


async def get_by_name_and_source_type(
    conn: asyncpg.Connection, name: str, source_type: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT * FROM environments WHERE name = $1 AND source_type = $2", name, source_type
    )


async def get_or_create(
    conn: asyncpg.Connection,
    *,
    name: str,
    source_type: str,
    host_or_cluster: str | None,
    metadata: dict[str, Any] | None,
) -> asyncpg.Record:
    # Atomic upsert via the (name, source_type) unique constraint — concurrent
    # requests for a brand new environment name resolve to a single row
    # instead of racing on a select-then-insert.
    return await conn.fetchrow(
        """
        INSERT INTO environments (name, source_type, host_or_cluster, metadata)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name, source_type) DO UPDATE SET
            host_or_cluster = COALESCE(EXCLUDED.host_or_cluster, environments.host_or_cluster),
            metadata = COALESCE(EXCLUDED.metadata, environments.metadata)
        RETURNING *
        """,
        name,
        source_type,
        host_or_cluster,
        metadata,
    )


async def try_acquire_snapshot_lock(conn: asyncpg.Connection, environment_id: UUID) -> bool:
    """Flips snapshot_in_progress false -> true atomically. Returns False if a
    snapshot for this environment is already in progress."""
    row = await conn.fetchrow(
        """
        UPDATE environments
        SET snapshot_in_progress = true
        WHERE id = $1 AND snapshot_in_progress = false
        RETURNING id
        """,
        environment_id,
    )
    return row is not None


async def release_snapshot_lock(conn: asyncpg.Connection, environment_id: UUID) -> None:
    await conn.execute(
        "UPDATE environments SET snapshot_in_progress = false WHERE id = $1", environment_id
    )


async def list_environments(
    conn: asyncpg.Connection,
    *,
    source_type: str | None,
    host_or_cluster: str | None,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    conditions: list[str] = []
    params: list[Any] = []
    if source_type is not None:
        params.append(source_type)
        conditions.append(f"source_type = ${len(params)}")
    if host_or_cluster is not None:
        params.append(host_or_cluster)
        conditions.append(f"host_or_cluster = ${len(params)}")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = await conn.fetchval(f"SELECT count(*) FROM environments {where_clause}", *params)

    rows = await conn.fetch(
        f"""
        SELECT * FROM environments
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params,
        limit,
        offset,
    )
    return rows, total
