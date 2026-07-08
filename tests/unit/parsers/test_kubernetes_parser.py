import pytest

from app.parsers.base import ParserError
from app.parsers.kubernetes import DEFAULT_CONTAINER_ANNOTATION, KubernetesSourceParser, split_image_ref


def _pod(
    name: str,
    containers: list[dict],
    init_containers: list[dict] | None = None,
    annotations: dict | None = None,
    node: str | None = None,
) -> dict:
    spec = {"containers": containers}
    if init_containers is not None:
        spec["initContainers"] = init_containers
    if node is not None:
        spec["nodeName"] = node
    return {"metadata": {"name": name, "annotations": annotations or {}}, "spec": spec}


def test_parses_valid_payload() -> None:
    payload = {
        "namespace": "payments",
        "cluster": "prod-cluster-eu-west",
        "metadata": {"team": "payments"},
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d",
                    [{"name": "api", "image": "registry.example.com/payments/api:1.4.2"}],
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    first = installations[0]
    assert first.environment_name == "payments"
    assert first.source_type == "kubernetes"
    assert first.host_or_cluster == "prod-cluster-eu-west"
    assert first.environment_metadata == {"team": "payments"}
    assert first.artifact_name == "registry.example.com/payments/api"
    assert first.artifact_version == "1.4.2"
    assert first.raw_data == {
        "name": "api",
        "image": "registry.example.com/payments/api:1.4.2",
        "pod": "api-7f9c9d",
    }


def test_replicas_on_different_nodes_produce_one_installation_per_pod_with_node_in_raw_data() -> None:
    # Två repliker av samma Deployment, schemalagda på olika noder i samma
    # namespace/kluster — parsern dedupar inte själv (det gör upsert-lagret
    # via UNIQUE(environment_id, artifact_id)); den ska bara ge en korrekt
    # ArtifactInstallation per pod, med rätt nod spårbar i raw_data.
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d-aaa",
                    [{"name": "api", "image": "registry.example.com/payments/api:1.4.2"}],
                    node="node-1",
                ),
                _pod(
                    "api-7f9c9d-bbb",
                    [{"name": "api", "image": "registry.example.com/payments/api:1.4.2"}],
                    node="node-2",
                ),
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 2
    assert {i.artifact_name for i in installations} == {"registry.example.com/payments/api"}
    assert {i.artifact_version for i in installations} == {"1.4.2"}
    assert {i.raw_data["node"] for i in installations} == {"node-1", "node-2"}
    assert {i.raw_data["pod"] for i in installations} == {"api-7f9c9d-aaa", "api-7f9c9d-bbb"}


def test_missing_namespace_raises_parser_error() -> None:
    payload = {"pods": {"items": []}}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_pods_raises_parser_error() -> None:
    payload = {"namespace": "payments"}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_pods_items_raises_parser_error() -> None:
    payload = {"namespace": "payments", "pods": {}}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_cluster_is_optional() -> None:
    payload = {
        "namespace": "payments",
        "pods": {"items": [_pod("p", [{"name": "nginx", "image": "nginx:1.25"}])]},
    }

    installations = KubernetesSourceParser().parse(payload)

    assert installations[0].host_or_cluster is None


def test_init_containers_are_never_included() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d",
                    [{"name": "api", "image": "registry.example.com/payments/api:1.4.2"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/payments/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    assert installations[0].artifact_name == "registry.example.com/payments/api"


def test_default_container_annotation_excludes_sidecars() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d",
                    [
                        {"name": "api", "image": "registry.example.com/payments/api:1.4.2"},
                        {"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"},
                    ],
                    annotations={DEFAULT_CONTAINER_ANNOTATION: "api"},
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    assert installations[0].artifact_name == "registry.example.com/payments/api"


def test_without_default_container_annotation_all_containers_are_kept() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d",
                    [
                        {"name": "api", "image": "registry.example.com/payments/api:1.4.2"},
                        {"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"},
                    ],
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert {i.artifact_name for i in installations} == {
        "registry.example.com/payments/api",
        "istio/proxyv2",
    }


def test_default_container_annotation_pointing_to_missing_container_yields_nothing_for_that_pod() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "api-7f9c9d",
                    [{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    annotations={DEFAULT_CONTAINER_ANNOTATION: "api"},
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert installations == []


def test_malformed_pod_entries_are_skipped_not_crashing() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod("ok", [{"name": "nginx", "image": "nginx:1.25"}]),
                {"metadata": {"name": "no-spec"}},
                {"metadata": {"name": "bad-containers"}, "spec": {"containers": "not-a-list"}},
                "not-a-dict",
                None,
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    assert installations[0].artifact_name == "nginx"


def test_malformed_container_entries_are_skipped_not_crashing() -> None:
    payload = {
        "namespace": "payments",
        "pods": {
            "items": [
                _pod(
                    "p",
                    [
                        {"name": "nginx", "image": "nginx:1.25"},
                        {"name": "empty-image", "image": ""},
                        {"name": "no-image-field"},
                        "not-a-dict",
                        None,
                    ],
                )
            ]
        },
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    assert installations[0].artifact_name == "nginx"


@pytest.mark.parametrize(
    ("image", "expected_name", "expected_version"),
    [
        ("nginx:1.25", "nginx", "1.25"),
        ("nginx", "nginx", "latest"),
        ("registry.example.com/payments/api:1.4.2", "registry.example.com/payments/api", "1.4.2"),
        ("registry.example.com:5000/payments/api", "registry.example.com:5000/payments/api", "latest"),
        ("registry.example.com:5000/payments/api:2.0", "registry.example.com:5000/payments/api", "2.0"),
        (
            "nginx@sha256:abcd1234",
            "nginx",
            "sha256:abcd1234",
        ),
    ],
)
def test_split_image_ref(image: str, expected_name: str, expected_version: str) -> None:
    name, version = split_image_ref(image)

    assert name == expected_name
    assert version == expected_version


DESCRIBE_OUTPUT_WITH_SIDECAR_AND_INIT_CONTAINER = """\
Name:             api-7f9c9d-abc12
Namespace:        payments
Annotations:      kubectl.kubernetes.io/default-container: api
Status:           Running
Init Containers:
  wait-for-db:
    Image:         registry.example.com/payments/wait-for-db:1.0.0
Containers:
  api:
    Image:          registry.example.com/payments/api:1.4.2
  istio-proxy:
    Image:          istio/proxyv2:1.20.0
QoS Class:       Burstable
"""


def test_describe_output_is_accepted_as_an_alternative_to_pods() -> None:
    payload = {
        "namespace": "payments",
        "cluster": "prod-cluster-eu-west",
        "describe_output": DESCRIBE_OUTPUT_WITH_SIDECAR_AND_INIT_CONTAINER,
    }

    installations = KubernetesSourceParser().parse(payload)

    assert len(installations) == 1
    first = installations[0]
    assert first.environment_name == "payments"
    assert first.host_or_cluster == "prod-cluster-eu-west"
    assert first.artifact_name == "registry.example.com/payments/api"
    assert first.artifact_version == "1.4.2"
    assert first.raw_data["pod"] == "api-7f9c9d-abc12"


def test_describe_output_and_pods_are_mutually_exclusive() -> None:
    payload = {
        "namespace": "payments",
        "pods": {"items": []},
        "describe_output": DESCRIBE_OUTPUT_WITH_SIDECAR_AND_INIT_CONTAINER,
    }

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_both_pods_and_describe_output_raises_parser_error() -> None:
    payload = {"namespace": "payments"}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_blank_describe_output_raises_parser_error() -> None:
    payload = {"namespace": "payments", "describe_output": "   "}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)
