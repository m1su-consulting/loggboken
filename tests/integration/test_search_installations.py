from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload, rpm_payload


def test_search_finds_by_environment_name(client: TestClient) -> None:
    unique = f"search-env-{uuid4()}"
    client.post(
        "/api/v1/installations",
        json=rpm_payload(
            f"{unique}.example.com",
            [{"name": "curl", "version": "1.0", "arch": "x86_64"}],
            environment_name=unique,
        ),
    )

    response = client.get("/api/v1/installations", params={"q": unique})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["environment_name"] == unique


def test_search_finds_by_artifact_name(client: TestClient) -> None:
    unique_artifact = f"search-artifact-{uuid4()}"
    host = f"search-host-{uuid4()}.example.com"
    client.post(
        "/api/v1/installations",
        json=rpm_payload(host, [{"name": unique_artifact, "version": "1.0", "arch": "x86_64"}]),
    )

    response = client.get("/api/v1/installations", params={"q": unique_artifact})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["artifact_name"] == unique_artifact


def test_search_finds_by_host_or_cluster(client: TestClient) -> None:
    unique_host = f"search-hostmatch-{uuid4()}.example.com"
    client.post(
        "/api/v1/installations",
        json=rpm_payload(unique_host, [{"name": "curl", "version": "1.0", "arch": "x86_64"}]),
    )

    response = client.get("/api/v1/installations", params={"q": "search-hostmatch"})

    assert response.status_code == 200
    body = response.json()
    assert any(item["host_or_cluster"] == unique_host for item in body["items"])


def test_search_filters_by_source_type(client: TestClient) -> None:
    unique = f"search-source-{uuid4()}"
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(unique, [{"image": "nginx:1.25"}]),
    )

    response = client.get(
        "/api/v1/installations", params={"q": unique, "source_type": "rpm"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0

    response = client.get(
        "/api/v1/installations", params={"q": unique, "source_type": "kubernetes"}
    )
    assert response.json()["total"] == 1


def test_search_excludes_removed_by_default_and_include_removed_shows_them(
    client: TestClient,
) -> None:
    unique_artifact = f"search-removed-{uuid4()}"
    host = f"search-removed-host-{uuid4()}.example.com"
    created = client.post(
        "/api/v1/installations",
        json=rpm_payload(host, [{"name": unique_artifact, "version": "1.0", "arch": "x86_64"}]),
    )
    environment_id = created.json()["environment_id"]
    installation_id = client.get(
        f"/api/v1/environments/{environment_id}/installations"
    ).json()["items"][0]["id"]
    client.delete(f"/api/v1/installations/{installation_id}")

    active_only = client.get("/api/v1/installations", params={"q": unique_artifact})
    assert active_only.json()["total"] == 0

    with_removed = client.get(
        "/api/v1/installations", params={"q": unique_artifact, "include_removed": True}
    )
    body = with_removed.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "removed"


def test_search_sorts_by_artifact_name(client: TestClient) -> None:
    host = f"search-sort-{uuid4()}.example.com"
    prefix = f"sorttest-{uuid4()}"
    client.post(
        "/api/v1/installations",
        json=rpm_payload(
            host,
            [
                {"name": f"{prefix}-zeta", "version": "1.0", "arch": "x86_64"},
                {"name": f"{prefix}-alpha", "version": "1.0", "arch": "x86_64"},
            ],
        ),
    )

    ascending = client.get(
        "/api/v1/installations",
        params={"q": prefix, "sort_by": "artifact_name", "sort_dir": "asc"},
    ).json()
    names_asc = [item["artifact_name"] for item in ascending["items"]]
    assert names_asc == sorted(names_asc)

    descending = client.get(
        "/api/v1/installations",
        params={"q": prefix, "sort_by": "artifact_name", "sort_dir": "desc"},
    ).json()
    names_desc = [item["artifact_name"] for item in descending["items"]]
    assert names_desc == sorted(names_desc, reverse=True)


def test_search_pagination(client: TestClient) -> None:
    host = f"search-page-{uuid4()}.example.com"
    prefix = f"pagetest-{uuid4()}"
    packages = [
        {"name": f"{prefix}-{i}", "version": "1.0", "arch": "x86_64"} for i in range(5)
    ]
    client.post("/api/v1/installations", json=rpm_payload(host, packages))

    page = client.get(
        "/api/v1/installations", params={"q": prefix, "limit": 2, "offset": 0}
    ).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0
