import re

_POD_START_RE = re.compile(r"^Name:\s+(\S+)\s*$", re.MULTILINE)
_NODE_RE = re.compile(r"^Node:\s+(\S+)\s*$", re.MULTILINE)
_CONTAINER_NAME_RE = re.compile(r"^  (\S(?:.*\S)?):\s*$")
_IMAGE_RE = re.compile(r"^\s+Image:\s+(\S+)\s*$")
_DEFAULT_CONTAINER_ANNOTATION_RE = re.compile(
    r"kubectl\.kubernetes\.io/default-container:\s*(\S+)"
)


def _extract_containers(lines: list[str], start_index: int) -> list[dict]:
    """Samlar ihop containernamn + image under en 'Containers:'/'Init
    Containers:'-rubrik. Containernamn känns igen på exakt två blanksteg
    indentering ('  api:'), fälten under (Image, Port, State, ...) på fyra
    eller fler. Sektionen tar slut vid första rad utan indentering (nästa
    toppnivå-fält, t.ex. 'Conditions:') eller vid textens slut."""
    containers: list[dict] = []
    current: dict | None = None
    for line in lines[start_index:]:
        if line.strip() and not line.startswith(" "):
            break

        match = _CONTAINER_NAME_RE.match(line)
        if match:
            current = {"name": match.group(1)}
            containers.append(current)
            continue

        if current is not None and "image" not in current:
            image_match = _IMAGE_RE.match(line)
            if image_match:
                current["image"] = image_match.group(1)

    return containers


def parse_describe_pods_text(text: str) -> list[dict]:
    """Konverterar rå textutdata från `kubectl describe pods -n <namespace>`
    (en eller flera poddar i följd) till samma Pod-liknande dict-form som
    `kubectl get pods -o json` ger (`metadata.name`, `metadata.annotations`,
    `spec.containers`, `spec.initContainers`) — så att
    `KubernetesSourceParser`s befintliga filtreringslogik (default-container-
    annotation, initContainers-uteslutning) kan återanvändas oavsett vilket
    av de två indataformaten som skickades in.

    Formatet är kubectls egna, människoläsbara layout och inte en versionerad
    kontrakt-yta — den här parsern bygger därför på ett fåtal robusta,
    indenteringsbaserade mönster (containernamn = exakt två blanksteg
    indentering + kolon, fält därunder = fyra eller fler) snarare än att anta
    exakt kolumnbredd eller radordning.
    """
    starts = [match.start() for match in _POD_START_RE.finditer(text)]
    if not starts:
        return []

    boundaries = [*starts, len(text)]
    blocks = [text[start:end] for start, end in zip(boundaries, boundaries[1:])]

    pods: list[dict] = []
    for block in blocks:
        name_match = _POD_START_RE.match(block)
        pod_name = name_match.group(1) if name_match else None

        annotation_match = _DEFAULT_CONTAINER_ANNOTATION_RE.search(block)
        annotations = (
            {"kubectl.kubernetes.io/default-container": annotation_match.group(1)}
            if annotation_match
            else {}
        )

        node_match = _NODE_RE.search(block)
        node_name = None
        if node_match:
            # "Node:  node-1/10.0.0.5" -> "node-1" ("<none>" om ej schemalagd)
            candidate = node_match.group(1).split("/", 1)[0]
            if candidate != "<none>":
                node_name = candidate

        lines = block.splitlines()
        containers: list[dict] = []
        init_containers: list[dict] = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "Containers:":
                containers = _extract_containers(lines, index + 1)
            elif stripped == "Init Containers:":
                init_containers = _extract_containers(lines, index + 1)

        spec: dict = {"containers": containers, "initContainers": init_containers}
        if node_name:
            spec["nodeName"] = node_name

        pods.append(
            {
                "metadata": {"name": pod_name, "annotations": annotations},
                "spec": spec,
            }
        )

    return pods
