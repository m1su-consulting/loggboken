import pytest

from app.parsers.base import ParserError
from app.parsers.kubernetes import KubernetesSourceParser, split_image_ref


def test_parses_valid_payload() -> None:
    payload = {
        "namespace": "payments",
        "cluster": "prod-cluster-eu-west",
        "metadata": {"team": "payments"},
        "containers": [
            {"image": "registry.example.com/payments/api:1.4.2", "pod": "api-7f9c9d"},
        ],
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
    assert first.raw_data == {"image": "registry.example.com/payments/api:1.4.2", "pod": "api-7f9c9d"}


def test_missing_namespace_raises_parser_error() -> None:
    payload = {"containers": [{"image": "nginx:1.25"}]}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_containers_raises_parser_error() -> None:
    payload = {"namespace": "payments"}

    with pytest.raises(ParserError):
        KubernetesSourceParser().parse(payload)


def test_missing_cluster_is_optional() -> None:
    payload = {"namespace": "payments", "containers": [{"image": "nginx:1.25"}]}

    installations = KubernetesSourceParser().parse(payload)

    assert installations[0].host_or_cluster is None


def test_malformed_container_entries_are_skipped_not_crashing() -> None:
    payload = {
        "namespace": "payments",
        "containers": [
            {"image": "nginx:1.25"},
            {"image": ""},
            {"pod": "no-image-field"},
            "not-a-dict",
            None,
        ],
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
