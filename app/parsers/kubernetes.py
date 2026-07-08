import logging
from typing import Any

from app.parsers.base import ArtifactInstallation, BaseSourceParser, ParserError

logger = logging.getLogger(__name__)


def split_image_ref(image: str) -> tuple[str, str]:
    """Delar en container-image-referens i (namn, version).

    Hanterar digest-referenser (`name@sha256:...`), taggade referenser
    (`name:tag`) och undviker att förväxla ett registry-portnummer
    (`host:5000/namn`) med en tagg genom att bara leta efter ':' i den
    sista path-segmentet.
    """
    if "@" in image:
        name, digest = image.split("@", 1)
        return name, digest

    last_segment = image.rsplit("/", 1)[-1]
    if ":" in last_segment:
        name, tag = image.rsplit(":", 1)
        return name, tag

    return image, "latest"


class KubernetesSourceParser(BaseSourceParser):
    """Tolkar payloads från Kubernetes-baserade källsystem.

    Förväntat payload-format (antaget i brist på exempel från källsystemet,
    se `CLAUDE.md` under "Kvarstående öppna frågor"):

        {
          "namespace": "payments",
          "cluster": "prod-cluster-eu-west",   # valfritt -> host_or_cluster
          "metadata": {"team": "payments"},     # valfritt
          "containers": [
            {"image": "registry.example.com/payments/api:1.4.2", "pod": "api-7f9c9d"},
            ...
          ]
        }
    """

    source_type = "kubernetes"

    def parse(self, raw_json: dict[str, Any]) -> list[ArtifactInstallation]:
        namespace = raw_json.get("namespace")
        if not isinstance(namespace, str) or not namespace.strip():
            raise ParserError("saknar giltigt fält 'namespace'")

        containers = raw_json.get("containers")
        if not isinstance(containers, list):
            raise ParserError("saknar giltigt fält 'containers' (förväntad lista)")

        cluster = raw_json.get("cluster")
        if not isinstance(cluster, str) or not cluster.strip():
            cluster = None

        environment_metadata = raw_json.get("metadata")
        if environment_metadata is not None and not isinstance(environment_metadata, dict):
            environment_metadata = None

        installations: list[ArtifactInstallation] = []
        for container in containers:
            if not isinstance(container, dict):
                logger.warning("hoppar över icke-dict container-post: %r", container)
                continue

            image = container.get("image")
            if not isinstance(image, str) or not image.strip():
                logger.warning("hoppar över container utan giltig image: %r", container)
                continue

            name, version = split_image_ref(image)
            if not name.strip():
                logger.warning("hoppar över container med tomt image-namn: %r", container)
                continue

            installations.append(
                ArtifactInstallation(
                    environment_name=namespace,
                    source_type=self.source_type,
                    host_or_cluster=cluster,
                    environment_metadata=environment_metadata,
                    artifact_name=name,
                    artifact_version=version,
                    raw_data=container,
                )
            )

        return installations
