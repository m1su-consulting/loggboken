import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_environments_without_api_key_succeeds(client: TestClient) -> None:
    # read endpoints are intentionally open — internal system, teams should
    # be able to script against reads without provisioning a key
    response = client.get("/api/v1/environments")

    assert response.status_code == 200


def test_get_environments_with_garbage_api_key_still_succeeds(client: TestClient) -> None:
    # a key isn't validated at all for reads, so a bogus one is simply ignored
    response = client.get(
        "/api/v1/environments", headers={"X-API-Key": "not-a-real-key"}
    )

    assert response.status_code == 200


def test_health_does_not_require_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_missing_api_key_is_rejected_for_writes(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations",
        json={"source_type": "rpm", "data": {"host": "x", "packages": []}},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_api_key"


def test_invalid_api_key_is_rejected_for_writes(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations",
        headers={"X-API-Key": "not-a-real-key"},
        json={"source_type": "rpm", "data": {"host": "x", "packages": []}},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_api_key"


def test_key_scoped_to_rpm_cannot_write_kubernetes_data(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations",
        headers={"X-API-Key": "dev-rpm-key"},
        json={
            "source_type": "kubernetes",
            "data": {"namespace": "x", "containers": [{"image": "nginx:1.25"}]},
        },
    )

    assert response.status_code == 403
    assert response.json()["error"] == "source_type_forbidden"


def test_key_scoped_to_rpm_can_write_rpm_data(client: TestClient) -> None:
    response = client.post(
        "/api/v1/installations",
        headers={"X-API-Key": "dev-rpm-key"},
        json={
            "source_type": "rpm",
            "data": {
                "host": "auth-test.example.com",
                "packages": [{"name": "curl", "version": "1.0", "arch": "x86_64"}],
            },
        },
    )

    assert response.status_code == 201
