from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_connection
from app.main import app


@pytest.fixture
def client():
    with TestClient(app, headers={"X-API-Key": "dev-admin-key"}) as c:
        yield c


async def _fetch_failure(source_type: str, error: str) -> asyncpg.Record | None:
    conn = await asyncpg.connect(settings.database_url)
    await init_connection(conn)
    try:
        return await conn.fetchrow(
            """
            SELECT * FROM ingestion_failures
            WHERE source_type = $1 AND error = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            source_type,
            error,
        )
    finally:
        await conn.close()


def test_oversized_body_is_rejected_before_parsing(client: TestClient) -> None:
    huge_packages = [{"name": f"p{i}", "version": "1.0", "arch": "x86_64"} for i in range(50_000)]
    body = {"source_type": "rpm", "data": {"host": "x", "packages": huge_packages}}

    response = client.post("/api/v1/installations", json=body)

    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_empty_data_dict_is_rejected_by_schema(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations", json={"source_type": "rpm", "data": {}}
    )

    assert response.status_code == 422


async def test_unsupported_source_is_recorded_as_failure(client: TestClient) -> None:
    host = f"error-test-{uuid4()}"
    response = client.post(
        "/api/v1/installations",
        json={"source_type": "windows", "data": {"host": host}},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "unsupported_source",
        "detail": "okänd source_type 'windows', förväntade en av ['kubernetes', 'rpm']",
    }

    failure = await _fetch_failure("windows", "unsupported_source")
    assert failure is not None
    assert failure["raw_payload"] == {"host": host}
    assert failure["endpoint"] == "installations"


async def test_invalid_payload_is_recorded_as_failure(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations",
        json={"source_type": "rpm", "data": {"packages": [{"name": "curl", "version": "1.0"}]}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_payload"

    failure = await _fetch_failure("rpm", "invalid_payload")
    assert failure is not None
    assert failure["detail"] == "saknar giltigt fält 'host'"


async def test_snapshot_source_type_mismatch_is_recorded_with_environment_id(
    client: TestClient,
) -> None:
    host = f"mismatch-test-{uuid4()}.example.com"
    created = client.post(
        "/api/v1/installations",
        json={
            "source_type": "rpm",
            "data": {"host": host, "packages": [{"name": "curl", "version": "1.0"}]},
        },
    )
    environment_id = created.json()["environment_id"]

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json={"source_type": "kubernetes", "data": {"namespace": "x", "containers": []}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "source_type_mismatch"

    failure = await _fetch_failure("kubernetes", "source_type_mismatch")
    assert failure is not None
    assert str(failure["environment_id"]) == environment_id


def test_snapshot_with_zero_valid_entries_is_not_treated_as_failure(client: TestClient) -> None:
    host = f"empty-snapshot-{uuid4()}.example.com"
    created = client.post(
        "/api/v1/installations",
        json={
            "source_type": "rpm",
            "data": {"host": host, "packages": [{"name": "curl", "version": "1.0"}]},
        },
    )
    environment_id = created.json()["environment_id"]

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json={"source_type": "rpm", "data": {"host": host, "packages": []}},
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 0, "removed": 1}
