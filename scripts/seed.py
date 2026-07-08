"""Fyll den lokala databasen med exempeldata för manuell test av endpoints.

Förutsätter att Postgres redan kör och att migrationerna är körda — startar
inget själv:
  docker compose up -d postgres
  uv run alembic upgrade head
  uv run python -m scripts.seed

Idempotent — kan köras flera gånger utan att skapa dubbletter.

Går via samma parsers och repositories som det riktiga ingestion-API:et,
så exempeldatan garanterat följer samma konventioner (t.ex. att RPM-artefakter
namnges "version.arch").

Tre RPM-miljöer (proj1, proj2, prod) med egna applikationer (inte
OS-paket som openssl/curl), och fyra Kubernetes-projektgrupper
(proj1-*, proj2-*, proj3-*, prod-*) med flera namespaces vardera — bra
underlag för att testa både miljö-prefix-bläddring och diff mellan miljöer.
prod körs dessutom på två kluster (k821.prod, k822.prod) med samma app+version
speglad på båda, för att visa att en artefakt kan vara installerad i flera
kluster samtidigt.
"""
import asyncio
import sys

import asyncpg

from app.config import settings
from app.db import init_connection
from app.parsers.base import ArtifactInstallation, BaseSourceParser
from app.parsers.kubernetes import KubernetesSourceParser
from app.parsers.rpm import RpmSourceParser
from app.repositories import artifacts as artifacts_repo
from app.repositories import environments as environments_repo
from app.repositories import installations as installations_repo

RPM_PAYLOADS = [
    {
        "host": "proj1.example.com",
        "environment_name": "proj1",
        "metadata": {"team": "proj1"},
        "packages": [
            {"name": "applikation1", "version": "1.2.0-1.el9", "arch": "x86_64"},
            {"name": "applikation2", "version": "3.0.1-1.el9", "arch": "x86_64"},
        ],
    },
    {
        "host": "proj2.example.com",
        "environment_name": "proj2",
        "metadata": {"team": "proj2"},
        "packages": [
            # äldre version av applikation1 än proj1/prod — bra för diff-demo
            {"name": "applikation1", "version": "1.1.0-1.el9", "arch": "x86_64"},
            {"name": "applikation2", "version": "3.0.1-1.el9", "arch": "x86_64"},
        ],
    },
    {
        "host": "prod.example.com",
        "environment_name": "prod",
        "metadata": {"team": "platform"},
        "packages": [
            {"name": "applikation1", "version": "1.2.0-1.el9", "arch": "x86_64"},
            # nyare version av applikation2 än proj1/proj2 — bra för diff-demo
            {"name": "applikation2", "version": "3.1.0-1.el9", "arch": "x86_64"},
        ],
    },
]

def _pod(
    name: str,
    image: str,
    *,
    container_name: str = "app",
    sidecars: list[dict] | None = None,
    init_containers: list[dict] | None = None,
    node: str | None = None,
) -> dict:
    """Bygger ett Pod-objekt i samma form som `kubectl get pods -o json`
    ger. Om `sidecars` anges sätts `kubectl.kubernetes.io/default-container`
    till huvudcontainerns namn, så parserns sidecar-filtrering har något att
    filtrera bort — precis som en Istio-injicerad pod i verkligheten."""
    containers = [{"name": container_name, "image": image}]
    annotations = {}
    if sidecars:
        containers.extend(sidecars)
        annotations["kubectl.kubernetes.io/default-container"] = container_name

    spec: dict = {"containers": containers}
    if init_containers:
        spec["initContainers"] = init_containers
    if node:
        spec["nodeName"] = node

    return {"metadata": {"name": name, "annotations": annotations}, "spec": spec}


# backend-poddarna bär en istio-proxy-sidecar + en wait-for-db-initcontainer
# för att visa att bara "api" (huvudcontainern, pekad ut via
# default-container-annotationen) landar som artefakt — sidecar och
# initcontainer ska aldrig dyka upp i installationer eller diff.
KUBERNETES_PAYLOADS = [
    {
        "namespace": "proj1-frontend",
        "cluster": "k811.system",
        "metadata": {"team": "proj1"},
        # 2 repliker på olika noder i samma kluster — ska landa som EN aktiv
        # installation, inte två, och diffa normalt mot andra miljöer.
        "pods": {
            "items": [
                _pod(
                    "proj1-frontend-7f8b6-x1",
                    "registry.example.com/shared/frontend:2.0.0",
                    node="node-1",
                ),
                _pod(
                    "proj1-frontend-7f8b6-x2",
                    "registry.example.com/shared/frontend:2.0.0",
                    node="node-2",
                ),
            ]
        },
    },
    {
        "namespace": "proj1-backend",
        "cluster": "k811.system",
        "metadata": {"team": "proj1"},
        "pods": {
            "items": [
                _pod(
                    "proj1-backend-6c9d5-k2p",
                    "registry.example.com/shared/api:1.5.0",
                    container_name="api",
                    sidecars=[{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/shared/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    },
    {
        "namespace": "proj1-worker",
        "cluster": "k811.system",
        "metadata": {"team": "proj1"},
        "pods": {
            "items": [_pod("proj1-worker-5d7f8-m3q", "registry.example.com/shared/worker:1.0.0")]
        },
    },
    {
        "namespace": "proj2-frontend",
        "cluster": "k811.system",
        "metadata": {"team": "proj2"},
        # äldre version av frontend än proj1/prod — bra för diff-demo
        "pods": {
            "items": [_pod("proj2-frontend-9a1c2-p7r", "registry.example.com/shared/frontend:1.9.0")]
        },
    },
    {
        "namespace": "proj2-backend",
        "cluster": "k811.system",
        "metadata": {"team": "proj2"},
        "pods": {
            "items": [
                _pod(
                    "proj2-backend-3e4f5-t8w",
                    "registry.example.com/shared/api:1.5.0",
                    container_name="api",
                    sidecars=[{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/shared/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    },
    {
        "namespace": "proj3-frontend",
        "cluster": "k811.system",
        "metadata": {"team": "proj3"},
        # samma version som proj1/prod — bra för "same"-status i diff-demon
        "pods": {
            "items": [_pod("proj3-frontend-6b2d9-w4k", "registry.example.com/shared/frontend:2.0.0")]
        },
    },
    {
        "namespace": "proj3-backend",
        "cluster": "k811.system",
        "metadata": {"team": "proj3"},
        # samma version som proj1/proj2 — "same" mot dem, "different" mot prod (1.6.0)
        "pods": {
            "items": [
                _pod(
                    "proj3-backend-7c1f0-r2m",
                    "registry.example.com/shared/api:1.5.0",
                    container_name="api",
                    sidecars=[{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/shared/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    },
    {
        "namespace": "prod-frontend",
        "cluster": "k821.prod",
        "metadata": {"team": "platform"},
        "pods": {
            "items": [_pod("prod-frontend-2b3c4-v9x", "registry.example.com/shared/frontend:2.0.0")]
        },
    },
    {
        "namespace": "prod-backend",
        "cluster": "k821.prod",
        "metadata": {"team": "platform"},
        # nyare version av api än proj1/proj2 — bra för diff-demo
        "pods": {
            "items": [
                _pod(
                    "prod-backend-8f1a2-z4y",
                    "registry.example.com/shared/api:1.6.0",
                    container_name="api",
                    sidecars=[{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/shared/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    },
    {
        "namespace": "prod-worker",
        "cluster": "k821.prod",
        "metadata": {"team": "platform"},
        "pods": {
            "items": [_pod("prod-worker-4d5e6-q1w", "registry.example.com/shared/worker:1.0.0")]
        },
    },
    {
        # prod körs på två kluster (k821.prod huvud, k822.prod sekundär) —
        # samma app+version speglad på båda för att visa att EN artefakt kan
        # vara installerad i flera kluster samtidigt (syns som separata
        # rader i installationstabellen, en per (miljö, artefakt)).
        "namespace": "prod-backend-k822",
        "cluster": "k822.prod",
        "metadata": {"team": "platform"},
        "pods": {
            "items": [
                _pod(
                    "prod-backend-k822-3d7e1-h5n",
                    "registry.example.com/shared/api:1.6.0",
                    container_name="api",
                    sidecars=[{"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}],
                    init_containers=[
                        {"name": "wait-for-db", "image": "registry.example.com/shared/wait-for-db:1.0.0"}
                    ],
                )
            ]
        },
    },
]


async def seed_payload(
    conn: asyncpg.Connection, parser: BaseSourceParser, payload: dict
) -> list[ArtifactInstallation]:
    installations = parser.parse(payload)
    if not installations:
        return []

    first = installations[0]
    environment = await environments_repo.get_or_create(
        conn,
        name=first.environment_name,
        source_type=first.source_type,
        host_or_cluster=first.host_or_cluster,
        metadata=first.environment_metadata,
    )
    for item in installations:
        artifact = await artifacts_repo.upsert(
            conn,
            name=item.artifact_name,
            version=item.artifact_version,
            source_type=item.source_type,
            raw_data=item.raw_data,
        )
        await installations_repo.upsert_active(
            conn,
            environment_id=environment["id"],
            artifact_id=artifact["id"],
            raw_data=item.raw_data,
        )
    return installations


async def seed() -> None:
    try:
        pool = await asyncpg.create_pool(
            settings.database_url, min_size=1, max_size=1, init=init_connection
        )
    except OSError as exc:
        print(
            f"Kunde inte nå databasen på {settings.database_url}: {exc}\n\n"
            "Detta script startar ingen databas — det förutsätter att en redan kör.\n"
            "Starta den först:\n"
            "  docker compose up -d postgres\n",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        async with pool.acquire() as conn:
            rpm_parser = RpmSourceParser()
            k8s_parser = KubernetesSourceParser()

            rpm_count = 0
            for payload in RPM_PAYLOADS:
                installations = await seed_payload(conn, rpm_parser, payload)
                rpm_count += len(installations)

            k8s_count = 0
            for payload in KUBERNETES_PAYLOADS:
                installations = await seed_payload(conn, k8s_parser, payload)
                k8s_count += len(installations)

        print(
            f"Seedade {len(RPM_PAYLOADS)} rpm-miljöer ({rpm_count} artefakter totalt) och "
            f"{len(KUBERNETES_PAYLOADS)} kubernetes-namespaces ({k8s_count} artefakter totalt)."
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(seed())
