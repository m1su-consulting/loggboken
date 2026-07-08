from uuid import UUID

import asyncpg

from app.api.v1.schemas import IngestRequest
from app.errors import ApiError
from app.parsers.base import ArtifactInstallation, ParserError
from app.parsers.registry import get_parser
from app.repositories import ingestion_failures as ingestion_failures_repo


async def parse_or_record_failure(
    conn: asyncpg.Connection,
    *,
    endpoint: str,
    body: IngestRequest,
    environment_id: UUID | None = None,
    allow_empty: bool = False,
) -> list[ArtifactInstallation]:
    """Parses the ingestion payload. On any domain-level failure (unknown
    source_type, malformed payload, or an empty result when one isn't
    allowed), the raw payload is persisted to ingestion_failures before the
    error is raised, so the failed request is never silently dropped."""
    try:
        parser = get_parser(body.source_type)
        parsed = parser.parse(body.data)
        if not parsed and not allow_empty:
            raise ApiError(
                status_code=400,
                error="empty_payload",
                detail="inga giltiga installationer kunde tolkas ur payloaden",
            )
        return parsed
    except ParserError as exc:
        api_error = ApiError(status_code=400, error="invalid_payload", detail=str(exc))
        await _record(conn, endpoint, body, api_error, environment_id)
        raise api_error from exc
    except ApiError as exc:
        await _record(conn, endpoint, body, exc, environment_id)
        raise


async def record_and_raise(
    conn: asyncpg.Connection,
    *,
    endpoint: str,
    body: IngestRequest,
    api_error: ApiError,
    environment_id: UUID | None = None,
) -> None:
    await _record(conn, endpoint, body, api_error, environment_id)
    raise api_error


async def _record(
    conn: asyncpg.Connection,
    endpoint: str,
    body: IngestRequest,
    api_error: ApiError,
    environment_id: UUID | None,
) -> None:
    await ingestion_failures_repo.record_failure(
        conn,
        endpoint=endpoint,
        source_type=body.source_type,
        raw_payload=body.data,
        error=api_error.error,
        detail=api_error.detail,
        environment_id=environment_id,
    )
