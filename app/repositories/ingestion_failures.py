from typing import Any
from uuid import UUID

import asyncpg


async def record_failure(
    conn: asyncpg.Connection,
    *,
    endpoint: str,
    source_type: str,
    raw_payload: dict[str, Any],
    error: str,
    detail: str,
    environment_id: UUID | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO ingestion_failures (endpoint, source_type, environment_id, raw_payload, error, detail)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        endpoint,
        source_type,
        environment_id,
        raw_payload,
        error,
        detail,
    )
