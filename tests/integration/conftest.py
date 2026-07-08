import os
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.parsers.kubernetes import DEFAULT_CONTAINER_ANNOTATION

_PERSISTENT_LOCAL_DB_PORT = 5432
_TEST_DB_PORT = 5433


def _guard_against_persistent_local_database() -> None:
    # In CI there is no persistent local instance to protect — every job runs
    # against a fresh, disposable Postgres service — so the guard only applies
    # to local runs.
    if os.environ.get("CI"):
        return

    port = urlparse(settings.database_url).port
    if port != _TEST_DB_PORT:
        pytest.exit(
            "Tester ska köra mot engångsdatabasen (tmpfs, port "
            f"{_TEST_DB_PORT}), inte mot den persistenta lokala instansen "
            f"(port {_PERSISTENT_LOCAL_DB_PORT} — den produktionslika "
            "standardinstansen eller dev-instansen). APP_DATABASE_URL pekar "
            f"just nu mot port {port}.\n\n"
            "Kör istället:\n"
            "  docker compose --profile test up -d postgres-test\n"
            "  export APP_DATABASE_URL=postgresql://postgres:postgres@localhost:"
            f"{_TEST_DB_PORT}/environment_inventory\n"
            "  uv run pytest\n",
            returncode=1,
        )


_guard_against_persistent_local_database()


@pytest.fixture
def client():
    with TestClient(app, headers={"X-API-Key": "dev-admin-key"}) as c:
        yield c


def rpm_payload(host: str, packages: list[dict], environment_name: str | None = None) -> dict:
    data = {"host": host, "packages": packages}
    if environment_name is not None:
        data["environment_name"] = environment_name
    return {"source_type": "rpm", "data": data}


def kubernetes_payload(
    namespace: str, containers: list[dict], cluster: str | None = None
) -> dict:
    """Bygger en kubectl-get-pods-o-json-formad payload. Varje dict i
    `containers` blir en egen enkontainer-pod, vilket bevarar den gamla
    "en rad = en installation"-semantiken de flesta tester förlitar sig på.
    Ett dict kan också ange `name` (containerns namn), `pod` (poddens namn)
    och `default_container` (annotationsvärde, för sidecar-filtreringstester)
    utöver det obligatoriska `image`. För tester som behöver flerkontainer-
    poddar (sidecars, initContainers) rakt av, bygg pods direkt och använd
    `kubernetes_payload_from_pods`.
    """
    items = []
    for index, container in enumerate(containers):
        image = container["image"]
        container_name = (
            container.get("name") or image.rsplit("/", 1)[-1].split(":")[0].split("@")[0]
        )
        pod_name = container.get("pod") or f"{namespace}-pod-{index}"
        annotations = {}
        if "default_container" in container:
            annotations[DEFAULT_CONTAINER_ANNOTATION] = container["default_container"]

        items.append(
            {
                "metadata": {"name": pod_name, "annotations": annotations},
                "spec": {"containers": [{"name": container_name, "image": image}]},
            }
        )

    return kubernetes_payload_from_pods(namespace, items, cluster=cluster)


def kubernetes_payload_from_pods(
    namespace: str, pods: list[dict], cluster: str | None = None
) -> dict:
    data: dict = {"namespace": namespace, "pods": {"items": pods}}
    if cluster is not None:
        data["cluster"] = cluster
    return {"source_type": "kubernetes", "data": data}
