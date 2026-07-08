from typing import Any
from uuid import UUID

import asyncpg


async def get_by_id(conn: asyncpg.Connection, artifact_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM artifacts WHERE id = $1", artifact_id)


async def upsert(
    conn: asyncpg.Connection,
    *,
    name: str,
    version: str,
    source_type: str,
    raw_data: dict[str, Any] | None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO artifacts (name, version, source_type, raw_data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name, version, source_type)
        DO UPDATE SET raw_data = EXCLUDED.raw_data
        RETURNING *
        """,
        name,
        version,
        source_type,
        raw_data or {},
    )
