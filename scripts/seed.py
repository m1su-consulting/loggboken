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
OS-paket som openssl/curl), och tre Kubernetes-projektgrupper
(proj1-*, proj2-*, prod-*) med flera namespaces vardera — bra underlag
för att testa både miljö-prefix-bläddring och diff mellan miljöer.
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

KUBERNETES_PAYLOADS = [
    {
        "namespace": "proj1-frontend",
        "cluster": "eu-west-cluster",
        "metadata": {"team": "proj1"},
        "containers": [{"image": "registry.example.com/shared/frontend:2.0.0"}],
    },
    {
        "namespace": "proj1-backend",
        "cluster": "eu-west-cluster",
        "metadata": {"team": "proj1"},
        "containers": [{"image": "registry.example.com/shared/api:1.5.0"}],
    },
    {
        "namespace": "proj1-worker",
        "cluster": "eu-west-cluster",
        "metadata": {"team": "proj1"},
        "containers": [{"image": "registry.example.com/shared/worker:1.0.0"}],
    },
    {
        "namespace": "proj2-frontend",
        "cluster": "eu-west-cluster",
        "metadata": {"team": "proj2"},
        # äldre version av frontend än proj1/prod — bra för diff-demo
        "containers": [{"image": "registry.example.com/shared/frontend:1.9.0"}],
    },
    {
        "namespace": "proj2-backend",
        "cluster": "eu-west-cluster",
        "metadata": {"team": "proj2"},
        "containers": [{"image": "registry.example.com/shared/api:1.5.0"}],
    },
    {
        "namespace": "prod-frontend",
        "cluster": "prod-cluster-eu-west",
        "metadata": {"team": "platform"},
        "containers": [{"image": "registry.example.com/shared/frontend:2.0.0"}],
    },
    {
        "namespace": "prod-backend",
        "cluster": "prod-cluster-eu-west",
        "metadata": {"team": "platform"},
        # nyare version av api än proj1/proj2 — bra för diff-demo
        "containers": [{"image": "registry.example.com/shared/api:1.6.0"}],
    },
    {
        "namespace": "prod-worker",
        "cluster": "prod-cluster-eu-west",
        "metadata": {"team": "platform"},
        "containers": [{"image": "registry.example.com/shared/worker:1.0.0"}],
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
