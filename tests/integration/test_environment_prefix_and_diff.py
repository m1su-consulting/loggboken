from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.conftest import kubernetes_payload, kubernetes_payload_from_pods


def _pod(name: str, node: str, image: str) -> dict:
    return {
        "metadata": {"name": name},
        "spec": {"containers": [{"name": "app", "image": image}], "nodeName": node},
    }


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
    assert nginx["left"] == [
        {"environment_name": f"{left}-a", "version": "1.25", "host_or_cluster": None}
    ]
    assert nginx["right"] == [
        {"environment_name": f"{right}-a", "version": "1.24", "host_or_cluster": None}
    ]

    redis = items_by_name["redis"]
    assert redis["status"] == "same"
    # redis is active in both proj1-a and proj1-b on the left, same version
    assert sorted(e["environment_name"] for e in redis["left"]) == [f"{left}-a", f"{left}-b"]

    postgres_client = items_by_name["postgres-client"]
    assert postgres_client["status"] == "left_only"
    assert postgres_client["left"] == [
        {"environment_name": f"{left}-b", "version": "14", "host_or_cluster": None}
    ]
    assert postgres_client["right"] == []

    assert body["summary"] == {"same": 1, "different": 1, "left_only": 1, "right_only": 0}


def test_replicas_on_different_nodes_collapse_into_one_installation(
    client: TestClient,
) -> None:
    # Två repliker av samma Deployment, schemalagda på olika noder i samma
    # namespace/kluster — ska visas som EN aktiv installation, inte två.
    namespace = f"multinode-{uuid4().hex[:8]}"
    payload = kubernetes_payload_from_pods(
        namespace,
        [
            _pod("api-aaa", "node-1", "registry.example.com/team/api:1.0.0"),
            _pod("api-bbb", "node-2", "registry.example.com/team/api:1.0.0"),
        ],
    )

    response = client.post("/api/v1/installations", json=payload)

    assert response.status_code == 201
    # "upserted" räknar antal parsade poster (en per pod/replika) — inte
    # antal resulterande rader, så den blir 2 här. Det verkliga beviset är
    # att GET nedan bara visar EN installation trots två repliker.
    assert response.json()["upserted"] == 2

    environment_id = response.json()["environment_id"]
    installations = client.get(
        f"/api/v1/environments/{environment_id}/installations"
    ).json()
    assert installations["total"] == 1
    assert installations["items"][0]["artifact_name"] == "registry.example.com/team/api"


def test_diff_is_unaffected_by_replica_count_across_nodes(client: TestClient) -> None:
    # Vänster har artefakten på 2 noder, höger på 1 nod — ska ändå diffa som
    # "same" (samma version), inte dyka upp fördubblat eller förvirrat.
    left = f"diffnodesleft-{uuid4().hex[:8]}"
    right = f"diffnodesright-{uuid4().hex[:8]}"
    image = "registry.example.com/team/api:1.0.0"

    client.post(
        "/api/v1/installations",
        json=kubernetes_payload_from_pods(
            left,
            [
                _pod("api-aaa", "node-1", image),
                _pod("api-bbb", "node-2", image),
            ],
            cluster="cluster-a",
        ),
    )
    client.post(
        "/api/v1/installations",
        json=kubernetes_payload_from_pods(
            right, [_pod("api-ccc", "node-1", image)], cluster="cluster-b"
        ),
    )

    response = client.get(
        "/api/v1/environments/diff",
        params={"left": left, "right": right, "source_type": "kubernetes"},
    )

    assert response.status_code == 200
    body = response.json()
    items_by_name = {item["artifact_name"]: item for item in body["items"]}
    api = items_by_name["registry.example.com/team/api"]
    assert api["status"] == "same"
    assert api["left"] == [
        {"environment_name": left, "version": "1.0.0", "host_or_cluster": "cluster-a"}
    ]
    assert api["right"] == [
        {"environment_name": right, "version": "1.0.0", "host_or_cluster": "cluster-b"}
    ]


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
