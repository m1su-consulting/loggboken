from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload, rpm_payload


def _create_environment(client: TestClient, host: str, packages: list[dict]) -> str:
    created = client.post("/api/v1/installations", json=rpm_payload(host, packages))
    assert created.status_code == 201
    return created.json()["environment_id"]


def test_snapshot_marks_missing_artifacts_removed_and_keeps_present_ones_active(
    client: TestClient,
) -> None:
    host = f"snapshot-diff-{uuid4()}.example.com"
    environment_id = _create_environment(
        client,
        host,
        [
            {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
            {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
        ],
    )

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json=rpm_payload(host, [{"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}]),
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 1, "removed": 1}

    active = client.get(f"/api/v1/environments/{environment_id}/installations").json()
    assert active["total"] == 1
    assert active["items"][0]["artifact_name"] == "openssl"

    full = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"include_removed": True},
    ).json()
    assert full["total"] == 2
    curl_entry = next(i for i in full["items"] if i["artifact_name"] == "curl")
    assert curl_entry["status"] == "removed"
    assert curl_entry["source_of_removal"] == "snapshot_diff"
    assert curl_entry["removed_at"] is not None


def test_snapshot_adds_new_artifacts_not_previously_installed(client: TestClient) -> None:
    host = f"snapshot-add-{uuid4()}.example.com"
    environment_id = _create_environment(
        client, host, [{"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}]
    )

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json=rpm_payload(
            host,
            [
                {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
                {"name": "vim", "version": "9.0-1.el9", "arch": "x86_64"},
            ],
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 2, "removed": 0}

    active = client.get(f"/api/v1/environments/{environment_id}/installations").json()
    assert {i["artifact_name"] for i in active["items"]} == {"openssl", "vim"}


def test_snapshot_disjoint_set_replaces_everything(client: TestClient) -> None:
    host = f"snapshot-disjoint-{uuid4()}.example.com"
    environment_id = _create_environment(
        client, host, [{"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}]
    )

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json=rpm_payload(host, [{"name": "vim", "version": "9.0-1.el9", "arch": "x86_64"}]),
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 1, "removed": 1}

    active = client.get(f"/api/v1/environments/{environment_id}/installations").json()
    assert active["total"] == 1
    assert active["items"][0]["artifact_name"] == "vim"


def test_second_identical_snapshot_is_a_no_op_diff(client: TestClient) -> None:
    host = f"snapshot-noop-{uuid4()}.example.com"
    packages = [{"name": "curl", "version": "1.0", "arch": "x86_64"}]
    environment_id = _create_environment(client, host, packages)

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot", json=rpm_payload(host, packages)
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 1, "removed": 0}


def test_snapshot_by_name_is_equivalent_to_snapshot_by_id(client: TestClient) -> None:
    name = f"snapshot-by-name-{uuid4()}"
    packages = [{"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}]
    created = client.post(
        "/api/v1/installations",
        json=rpm_payload(f"{name}.example.com", packages, environment_name=name),
    )
    environment_id = created.json()["environment_id"]

    response = client.post(
        f"/api/v1/environments/by-name/{name}/snapshot",
        params={"source_type": "rpm"},
        json=rpm_payload(
            f"{name}.example.com",
            [{"name": "vim", "version": "9.0-1.el9", "arch": "x86_64"}],
            environment_name=name,
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 1, "removed": 1}

    active = client.get(f"/api/v1/environments/{environment_id}/installations").json()
    assert active["items"][0]["artifact_name"] == "vim"


def test_snapshot_by_name_unknown_name_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/environments/by-name/{uuid4()}/snapshot",
        params={"source_type": "rpm"},
        json=rpm_payload("x", []),
    )

    assert response.status_code == 404
    assert response.json()["error"] == "environment_not_found"


def test_snapshot_by_name_requires_source_type_query_param(client: TestClient) -> None:
    response = client.post(
        "/api/v1/environments/by-name/proj1/snapshot", json=rpm_payload("x", [])
    )

    assert response.status_code == 422


def test_kubernetes_snapshot_diff(client: TestClient) -> None:
    namespace = f"snapshot-k8s-{uuid4()}"
    created = client.post(
        "/api/v1/installations",
        json=kubernetes_payload(
            namespace,
            [
                {"image": "registry.example.com/team/api:1.0.0"},
                {"image": "registry.example.com/team/worker:1.0.0"},
            ],
        ),
    )
    environment_id = created.json()["environment_id"]

    response = client.post(
        f"/api/v1/environments/{environment_id}/snapshot",
        json=kubernetes_payload(
            namespace, [{"image": "registry.example.com/team/api:2.0.0"}]
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"environment_id": environment_id, "active": 1, "removed": 2}

    full = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"include_removed": True},
    ).json()
    assert full["total"] == 3
    active_names = {
        i["artifact_name"] for i in full["items"] if i["status"] == "active"
    }
    assert active_names == {"registry.example.com/team/api"}
