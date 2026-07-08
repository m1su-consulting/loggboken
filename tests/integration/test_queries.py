from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload, rpm_payload


def test_list_environments_filters_by_source_type(client: TestClient) -> None:
    rpm_host = f"query-rpm-{uuid4()}.example.com"
    k8s_namespace = f"query-k8s-{uuid4()}"
    rpm_env = client.post(
        "/api/v1/installations",
        json=rpm_payload(rpm_host, [{"name": "curl", "version": "1.0", "arch": "x86_64"}]),
    ).json()["environment_id"]
    k8s_env = client.post(
        "/api/v1/installations",
        json=kubernetes_payload(k8s_namespace, [{"image": "nginx:1.25"}]),
    ).json()["environment_id"]

    rpm_only = client.get("/api/v1/environments", params={"source_type": "rpm"}).json()
    rpm_ids = {e["id"] for e in rpm_only["items"]}
    assert rpm_env in rpm_ids
    assert k8s_env not in rpm_ids

    k8s_only = client.get("/api/v1/environments", params={"source_type": "kubernetes"}).json()
    k8s_ids = {e["id"] for e in k8s_only["items"]}
    assert k8s_env in k8s_ids
    assert rpm_env not in k8s_ids


def test_list_environments_filters_by_host_or_cluster(client: TestClient) -> None:
    host = f"query-host-{uuid4()}.example.com"
    environment_id = client.post(
        "/api/v1/installations",
        json=rpm_payload(host, [{"name": "curl", "version": "1.0", "arch": "x86_64"}]),
    ).json()["environment_id"]

    matching = client.get(
        "/api/v1/environments", params={"host_or_cluster": host}
    ).json()
    assert {e["id"] for e in matching["items"]} == {environment_id}

    non_matching = client.get(
        "/api/v1/environments", params={"host_or_cluster": f"nonexistent-{uuid4()}"}
    ).json()
    assert non_matching["items"] == []
    assert non_matching["total"] == 0


def test_list_environments_pagination(client: TestClient) -> None:
    prefix = f"query-page-{uuid4()}"
    for i in range(5):
        client.post(
            "/api/v1/installations",
            json=rpm_payload(
                f"{prefix}-{i}.example.com",
                [{"name": "curl", "version": "1.0", "arch": "x86_64"}],
            ),
        )

    # environments aren't filterable by name prefix, so pagination is verified
    # over the full collection: two non-overlapping pages of the same size
    # must return disjoint items and echo back the requested limit/offset.
    page_a = client.get("/api/v1/environments", params={"limit": 3, "offset": 0}).json()
    page_b = client.get("/api/v1/environments", params={"limit": 3, "offset": 3}).json()
    assert page_a["limit"] == 3
    assert page_a["offset"] == 0
    assert page_b["offset"] == 3
    ids_a = {e["id"] for e in page_a["items"]}
    ids_b = {e["id"] for e in page_b["items"]}
    assert ids_a.isdisjoint(ids_b)


def test_list_environment_installations_include_removed(client: TestClient) -> None:
    host = f"query-installations-{uuid4()}.example.com"
    created = client.post(
        "/api/v1/installations",
        json=rpm_payload(
            host,
            [
                {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
                {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
            ],
        ),
    )
    environment_id = created.json()["environment_id"]
    installation_id = next(
        i["id"]
        for i in client.get(f"/api/v1/environments/{environment_id}/installations").json()[
            "items"
        ]
        if i["artifact_name"] == "curl"
    )
    client.delete(f"/api/v1/installations/{installation_id}")

    active_only = client.get(f"/api/v1/environments/{environment_id}/installations").json()
    assert active_only["total"] == 1
    assert active_only["items"][0]["artifact_name"] == "openssl"

    with_removed = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"include_removed": True},
    ).json()
    assert with_removed["total"] == 2


def test_list_environment_installations_filters_by_artifact_name(client: TestClient) -> None:
    host = f"query-installations-artifact-{uuid4()}.example.com"
    environment_id = client.post(
        "/api/v1/installations",
        json=rpm_payload(
            host,
            [
                {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
                {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
            ],
        ),
    ).json()["environment_id"]

    matching = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"artifact_name": "openssl"},
    ).json()
    assert matching["total"] == 1
    assert matching["items"][0]["artifact_name"] == "openssl"

    non_matching = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"artifact_name": "does-not-exist"},
    ).json()
    assert non_matching["total"] == 0
    assert non_matching["items"] == []


def test_list_environment_installations_by_name_with_artifact_filter(
    client: TestClient,
) -> None:
    name = f"query-by-name-{uuid4()}"
    client.post(
        "/api/v1/installations",
        json=rpm_payload(
            f"{name}.example.com",
            [
                {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
                {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
            ],
            environment_name=name,
        ),
    )

    response = client.get(
        f"/api/v1/environments/by-name/{name}/installations",
        params={"source_type": "rpm", "artifact_name": "openssl"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["artifact_name"] == "openssl"

    full = client.get(
        f"/api/v1/environments/by-name/{name}/installations", params={"source_type": "rpm"}
    ).json()
    assert full["total"] == 2


def test_list_environment_installations_by_name_unknown_name_returns_404(
    client: TestClient,
) -> None:
    response = client.get(
        f"/api/v1/environments/by-name/{uuid4()}/installations",
        params={"source_type": "rpm"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "environment_not_found"


def test_list_environment_installations_by_name_requires_source_type(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/environments/by-name/proj1/installations")

    assert response.status_code == 422


def test_list_environment_installations_pagination(client: TestClient) -> None:
    host = f"query-installations-page-{uuid4()}.example.com"
    packages = [
        {"name": f"pkg{i}", "version": "1.0", "arch": "x86_64"} for i in range(5)
    ]
    environment_id = client.post(
        "/api/v1/installations", json=rpm_payload(host, packages)
    ).json()["environment_id"]

    page = client.get(
        f"/api/v1/environments/{environment_id}/installations",
        params={"limit": 2, "offset": 0},
    ).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0


def test_list_environment_installations_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/environments/{uuid4()}/installations")

    assert response.status_code == 404
    assert response.json()["error"] == "environment_not_found"


def test_list_artifact_environments_include_removed(client: TestClient) -> None:
    host_a = f"query-artifact-a-{uuid4()}.example.com"
    host_b = f"query-artifact-b-{uuid4()}.example.com"
    # unique package name so this artifact isn't shared with other tests'
    # environments via the (name, version, source_type) identity
    unique_name = f"test-artifact-{uuid4()}"
    shared_package = [{"name": unique_name, "version": "1.0", "arch": "x86_64"}]

    env_a = client.post(
        "/api/v1/installations", json=rpm_payload(host_a, shared_package)
    ).json()["environment_id"]
    env_b = client.post(
        "/api/v1/installations", json=rpm_payload(host_b, shared_package)
    ).json()["environment_id"]

    artifact_id = client.get(f"/api/v1/environments/{env_a}/installations").json()["items"][
        0
    ]["artifact_id"]

    both_active = client.get(f"/api/v1/artifacts/{artifact_id}/environments").json()
    assert both_active["total"] == 2
    assert {e["environment_id"] for e in both_active["items"]} == {env_a, env_b}

    installation_a = client.get(f"/api/v1/environments/{env_a}/installations").json()[
        "items"
    ][0]["id"]
    client.delete(f"/api/v1/installations/{installation_a}")

    active_only = client.get(f"/api/v1/artifacts/{artifact_id}/environments").json()
    assert active_only["total"] == 1
    assert active_only["items"][0]["environment_id"] == env_b

    with_removed = client.get(
        f"/api/v1/artifacts/{artifact_id}/environments", params={"include_removed": True}
    ).json()
    assert with_removed["total"] == 2


def test_list_artifact_environments_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/artifacts/{uuid4()}/environments")

    assert response.status_code == 404
    assert response.json()["error"] == "artifact_not_found"
