import os
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

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
    data = {"namespace": namespace, "containers": containers}
    if cluster is not None:
        data["cluster"] = cluster
    return {"source_type": "kubernetes", "data": data}
