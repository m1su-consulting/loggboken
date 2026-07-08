from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload


def test_environment_prefix_matches_all_namespaces_under_it(client: TestClient) -> None:
    prefix = f"prefixtest-{uuid4().hex[:8]}"
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(f"{prefix}-frontend", [{"image": "nginx:1.25"}]),
    )
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(f"{prefix}-backend", [{"image": "redis:7.0"}]),
    )

    response = client.get("/api/v1/installations", params={"environment": prefix})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = {item["environment_name"] for item in body["items"]}
    assert names == {f"{prefix}-frontend", f"{prefix}-backend"}


def test_environment_prefix_respects_hyphen_boundary(client: TestClient) -> None:
    prefix = f"boundarytest-{uuid4().hex[:8]}"
    # this should NOT match a search for `prefix` alone (no hyphen boundary)
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(f"{prefix}0-other", [{"image": "nginx:1.25"}]),
    )
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(f"{prefix}-real", [{"image": "redis:7.0"}]),
    )

    response = client.get("/api/v1/installations", params={"environment": prefix})

    assert response.status_code == 200
    body = response.json()
    names = {item["environment_name"] for item in body["items"]}
    assert names == {f"{prefix}-real"}
    assert f"{prefix}0-other" not in names


def test_environment_exact_match_with_no_siblings(client: TestClient) -> None:
    name = f"exacttest-{uuid4().hex[:8]}"
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(name, [{"image": "nginx:1.25"}]),
    )

    response = client.get("/api/v1/installations", params={"environment": name})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["environment_name"] == name


def test_diff_between_two_prefix_groups(client: TestClient) -> None:
    left = f"diffleft-{uuid4().hex[:8]}"
    right = f"diffright-{uuid4().hex[:8]}"

    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(
            f"{left}-a", [{"image": "nginx:1.25"}, {"image": "redis:7.0"}]
        ),
    )
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(
            f"{left}-b", [{"image": "redis:7.0"}, {"image": "postgres-client:14"}]
        ),
    )
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload(
            f"{right}-a", [{"image": "nginx:1.24"}, {"image": "redis:7.0"}]
        ),
    )

    response = client.get(
        "/api/v1/environments/diff",
        params={"left": left, "right": right, "source_type": "kubernetes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(body["left"]["matched_environments"]) == [f"{left}-a", f"{left}-b"]
    assert body["right"]["matched_environments"] == [f"{right}-a"]

    items_by_name = {item["artifact_name"]: item for item in body["items"]}

    nginx = items_by_name["nginx"]
    assert nginx["status"] == "different"
    assert nginx["left"] == [{"environment_name": f"{left}-a", "version": "1.25"}]
    assert nginx["right"] == [{"environment_name": f"{right}-a", "version": "1.24"}]

    redis = items_by_name["redis"]
    assert redis["status"] == "same"
    # redis is active in both proj1-a and proj1-b on the left, same version
    assert sorted(e["environment_name"] for e in redis["left"]) == [f"{left}-a", f"{left}-b"]

    postgres_client = items_by_name["postgres-client"]
    assert postgres_client["status"] == "left_only"
    assert postgres_client["left"] == [
        {"environment_name": f"{left}-b", "version": "14"}
    ]
    assert postgres_client["right"] == []

    assert body["summary"] == {"same": 1, "different": 1, "left_only": 1, "right_only": 0}


def test_diff_with_nonexistent_environments_returns_empty_items(client: TestClient) -> None:
    response = client.get(
        "/api/v1/environments/diff",
        params={
            "left": f"nope-left-{uuid4()}",
            "right": f"nope-right-{uuid4()}",
            "source_type": "kubernetes",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["left"]["matched_environments"] == []
    assert body["right"]["matched_environments"] == []
