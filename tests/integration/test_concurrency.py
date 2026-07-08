import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import connect_pool, disconnect_pool
from app.main import app


@pytest.fixture
async def client():
    await connect_pool()
    transport = ASGITransport(app=app)
    headers = {"X-API-Key": "dev-admin-key"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac
    await disconnect_pool()


def rpm_payload(host: str, packages: list[dict]) -> dict:
    return {"source_type": "rpm", "data": {"host": host, "packages": packages}}


async def test_concurrent_event_ingest_same_environment_no_duplicates(client: AsyncClient) -> None:
    host = f"concurrency-event-{uuid4()}.example.com"
    payload = rpm_payload(host, [{"name": "openssl", "version": "1.0.0", "arch": "x86_64"}])

    responses = await asyncio.gather(
        *[client.post("/api/v1/installations", json=payload) for _ in range(10)]
    )

    assert all(r.status_code == 201 for r in responses)
    environment_id = responses[0].json()["environment_id"]
    assert all(r.json()["environment_id"] == environment_id for r in responses)

    listing = await client.get(f"/api/v1/environments/{environment_id}/installations")
    assert listing.json()["total"] == 1


async def test_concurrent_snapshot_same_environment_only_one_succeeds(
    client: AsyncClient,
) -> None:
    host = f"concurrency-snapshot-{uuid4()}.example.com"
    packages = [{"name": "curl", "version": "1.0", "arch": "x86_64"}]

    created = await client.post("/api/v1/installations", json=rpm_payload(host, packages))
    environment_id = created.json()["environment_id"]

    snapshot_body = rpm_payload(host, packages)
    responses = await asyncio.gather(
        *[
            client.post(f"/api/v1/environments/{environment_id}/snapshot", json=snapshot_body)
            for _ in range(5)
        ]
    )

    status_codes = sorted(r.status_code for r in responses)
    assert status_codes.count(200) == 1
    assert status_codes.count(409) == 4


async def test_concurrent_snapshots_different_environments_all_succeed(
    client: AsyncClient,
) -> None:
    packages = [{"name": "curl", "version": "1.0", "arch": "x86_64"}]
    hosts = [f"concurrency-diff-{uuid4()}.example.com" for _ in range(5)]

    created = await asyncio.gather(
        *[client.post("/api/v1/installations", json=rpm_payload(h, packages)) for h in hosts]
    )
    environment_ids = [r.json()["environment_id"] for r in created]

    responses = await asyncio.gather(
        *[
            client.post(f"/api/v1/environments/{env_id}/snapshot", json=rpm_payload(h, packages))
            for env_id, h in zip(environment_ids, hosts)
        ]
    )

    assert all(r.status_code == 200 for r in responses)
