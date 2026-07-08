from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload, rpm_payload


def test_rpm_event_ingest_creates_environment_and_installations(client: TestClient) -> None:
    host = f"ingest-rpm-{uuid4()}.example.com"
    payload = rpm_payload(
        host,
        [
            {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
            {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
        ],
        environment_name="ingest-rpm-project",
    )

    response = client.post("/api/v1/installations", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["upserted"] == 2
    environment_id = body["environment_id"]

    listing = client.get(f"/api/v1/environments/{environment_id}/installations")
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["total"] == 2
    names = {item["artifact_name"] for item in listing_body["items"]}
    assert names == {"openssl", "curl"}
    assert all(item["status"] == "active" for item in listing_body["items"])


def test_kubernetes_event_ingest_creates_environment_and_installation(
    client: TestClient,
) -> None:
    namespace = f"ingest-k8s-{uuid4()}"
    payload = kubernetes_payload(
        namespace,
        [{"image": "registry.example.com/team/api:2.1.0", "pod": "api-abc123"}],
        cluster="test-cluster",
    )

    response = client.post("/api/v1/installations", json=payload)

    assert response.status_code == 201
    environment_id = response.json()["environment_id"]

    envs = client.get("/api/v1/environments", params={"source_type": "kubernetes"})
    matching = [e for e in envs.json()["items"] if e["id"] == environment_id]
    assert len(matching) == 1
    assert matching[0]["host_or_cluster"] == "test-cluster"


def test_repeated_event_ingest_is_idempotent(client: TestClient) -> None:
    host = f"ingest-idempotent-{uuid4()}.example.com"
    payload = rpm_payload(host, [{"name": "curl", "version": "1.0", "arch": "x86_64"}])

    first = client.post("/api/v1/installations", json=payload)
    second = client.post("/api/v1/installations", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["environment_id"] == second.json()["environment_id"]

    environment_id = first.json()["environment_id"]
    listing = client.get(f"/api/v1/environments/{environment_id}/installations")
    assert listing.json()["total"] == 1


def test_manual_removal_happy_path(client: TestClient) -> None:
    host = f"removal-{uuid4()}.example.com"
    created = client.post(
        "/api/v1/installations",
        json=rpm_payload(host, [{"name": "curl", "version": "1.0", "arch": "x86_64"}]),
    )
    environment_id = created.json()["environment_id"]
    installation_id = client.get(
        f"/api/v1/environments/{environment_id}/installations"
    ).json()["items"][0]["id"]

    response = client.delete(f"/api/v1/installations/{installation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "removed"
    assert body["source_of_removal"] == "manual"
    assert body["removed_at"] is not None

    active_listing = client.get(f"/api/v1/environments/{environment_id}/installations")
    assert active_listing.json()["total"] == 0

    full_listing = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"include_removed": True},
    )
    assert full_listing.json()["total"] == 1
