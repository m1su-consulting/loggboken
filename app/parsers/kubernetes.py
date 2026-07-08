import logging
from typing import Any

from app.parsers.base import ArtifactInstallation, BaseSourceParser, ParserError
from app.parsers.kubectl_describe import parse_describe_pods_text

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


DEFAULT_CONTAINER_ANNOTATION = "kubectl.kubernetes.io/default-container"


class KubernetesSourceParser(BaseSourceParser):
    """Tolkar payloads från Kubernetes-baserade källsystem.

    Två inputformat stöds, valfritt via `pods` (rekommenderat) eller
    `describe_output` — exakt ett av de två måste anges:

    1. `pods` — rådatan `kubectl get pods -n <namespace> -o json` ger,
       wrappad med lite miljö-metadata som kubectl självt inte känner till
       (kluster/kontext är klientsidans vetskap, inte del av
       Kubernetes-API-resursen):

        {
          "namespace": "payments",
          "cluster": "prod-cluster-eu-west",   # valfritt -> host_or_cluster
          "metadata": {"team": "payments"},     # valfritt
          "pods": {
            "items": [
              {
                "metadata": {
                  "name": "api-7f9c9d-abc12",
                  "annotations": {"kubectl.kubernetes.io/default-container": "api"}
                },
                "spec": {
                  "containers": [
                    {"name": "api", "image": "registry.example.com/payments/api:1.4.2"},
                    {"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"}
                  ],
                  "initContainers": [
                    {"name": "wait-for-db", "image": "registry.example.com/payments/wait-for-db:1.0.0"}
                  ]
                }
              }
            ]
          }
        }

    2. `describe_output` — rå textutdata från `kubectl describe pods -n
       <namespace>` (en eller flera poddar i följd), t.ex.:

        {
          "namespace": "payments",
          "cluster": "prod-cluster-eu-west",
          "describe_output": "Name:             api-7f9c9d-abc12\\nNamespace: ...\\n..."
        }

       Konverteras internt (se `app/parsers/kubectl_describe.py`) till samma
       Pod-liknande form som (1), så filtreringslogiken nedan är identisk
       oavsett vilket format som skickades in. `describe`-textformatet är
       kubectls egna, människoläsbara layout — inte en versionerad
       kontrakt-yta som `-o json` är — så `pods` är det robustare valet när
       källsystemet självt kan producera JSON.

    Oavsett format: `spec.initContainers` läses aldrig — utesluts helt
    gratis eftersom Kubernetes redan håller isär dem från `spec.containers`.

    Sidecars (istio-proxy, linkerd-proxy m.fl.) ligger däremot i samma
    `spec.containers`-lista som appens egna container — Kubernetes har
    ingen inbyggd flagga för det. Om podden har annotationen
    `kubectl.kubernetes.io/default-container` (satt av bl.a. Istios
    auto-injection och `kubectl debug`) litar vi på den och tar bara den
    namngivna containern. Saknas annotationen tas samtliga
    `spec.containers` — vi har då inget tillförlitligt sätt att gissa vilken
    som är "huvudcontainern" utan att riskera att utesluta fel container.

    `spec.nodeName` (vilken nod podden kör på) sparas i `raw_data["node"]`
    för spårbarhet, om den finns. Flera repliker av samma Deployment landar
    ofta på olika noder inom samma kluster/namespace — det påverkar inte
    installationsraden: `(environment_id, artifact_id)` är unikt, så alla
    repliker med samma image+version slås ihop till en aktiv installation
    oavsett hur många noder/poddar de är spridda över.
    """

    source_type = "kubernetes"

    def parse(self, raw_json: dict[str, Any]) -> list[ArtifactInstallation]:
        namespace = raw_json.get("namespace")
        if not isinstance(namespace, str) or not namespace.strip():
            raise ParserError("saknar giltigt fält 'namespace'")

        pods_root = raw_json.get("pods")
        describe_output = raw_json.get("describe_output")

        if pods_root is not None and describe_output is not None:
            raise ParserError("ange antingen 'pods' eller 'describe_output', inte båda")

        if isinstance(pods_root, dict):
            items = pods_root.get("items")
            if not isinstance(items, list):
                raise ParserError("'pods.items' saknas eller är inte en lista")
        elif isinstance(describe_output, str):
            if not describe_output.strip():
                raise ParserError("'describe_output' är tomt")
            items = parse_describe_pods_text(describe_output)
        else:
            raise ParserError(
                "saknar giltigt fält 'pods' (kubectl get pods -o json) eller "
                "'describe_output' (kubectl describe pods -n <namespace>)"
            )

        cluster = raw_json.get("cluster")
        if not isinstance(cluster, str) or not cluster.strip():
            cluster = None

        environment_metadata = raw_json.get("metadata")
        if environment_metadata is not None and not isinstance(environment_metadata, dict):
            environment_metadata = None

        installations: list[ArtifactInstallation] = []
        for pod in items:
            if not isinstance(pod, dict):
                logger.warning("hoppar över icke-dict pod-post: %r", pod)
                continue

            spec = pod.get("spec")
            if not isinstance(spec, dict):
                logger.warning("hoppar över pod utan giltig 'spec': %r", pod)
                continue

            containers = spec.get("containers")
            if not isinstance(containers, list):
                logger.warning("hoppar över pod utan giltig 'spec.containers': %r", pod)
                continue

            pod_metadata = pod.get("metadata")
            pod_metadata = pod_metadata if isinstance(pod_metadata, dict) else {}
            pod_name = pod_metadata.get("name")

            node_name = spec.get("nodeName")
            node_name = node_name if isinstance(node_name, str) and node_name.strip() else None

            default_container = None
            annotations = pod_metadata.get("annotations")
            if isinstance(annotations, dict):
                value = annotations.get(DEFAULT_CONTAINER_ANNOTATION)
                if isinstance(value, str) and value.strip():
                    default_container = value

            matched_default_container = False
            for container in containers:
                if not isinstance(container, dict):
                    logger.warning("hoppar över icke-dict container-post: %r", container)
                    continue

                container_name = container.get("name")
                if default_container is not None:
                    if container_name != default_container:
                        continue
                    matched_default_container = True

                image = container.get("image")
                if not isinstance(image, str) or not image.strip():
                    logger.warning("hoppar över container utan giltig image: %r", container)
                    continue

                name, version = split_image_ref(image)
                if not name.strip():
                    logger.warning("hoppar över container med tomt image-namn: %r", container)
                    continue

                raw_data = dict(container)
                if pod_name:
                    raw_data["pod"] = pod_name
                if node_name:
                    raw_data["node"] = node_name

                installations.append(
                    ArtifactInstallation(
                        environment_name=namespace,
                        source_type=self.source_type,
                        host_or_cluster=cluster,
                        environment_metadata=environment_metadata,
                        artifact_name=name,
                        artifact_version=version,
                        raw_data=raw_data,
                    )
                )

            if default_container is not None and not matched_default_container:
                logger.warning(
                    "podden %r angav default-container %r via annotation, "
                    "men ingen container med det namnet hittades bland spec.containers",
                    pod_name,
                    default_container,
                )

        return installations
