from collections import defaultdict
from typing import Literal, TypedDict

DiffStatus = Literal["same", "different", "left_only", "right_only"]


class EnvironmentVersion(TypedDict):
    environment_name: str
    version: str
    host_or_cluster: str | None


class DiffItem(TypedDict):
    artifact_name: str
    left: list[EnvironmentVersion]
    right: list[EnvironmentVersion]
    status: DiffStatus


def compute_environment_diff(
    left_installations: list[tuple[str, str, str, str | None]],
    right_installations: list[tuple[str, str, str, str | None]],
) -> list[DiffItem]:
    """Diffs two sets of (artifact_name, version, environment_name,
    host_or_cluster) active installations.

    Each side may itself be an aggregate of several environments (e.g. all
    Kubernetes namespaces sharing a project prefix) — every entry keeps the
    specific environment/namespace (and its host/cluster) it came from, so
    the UI can show exactly where an artifact lives rather than just the
    aggregate query name.
    """
    left_by_artifact: dict[str, list[EnvironmentVersion]] = defaultdict(list)
    for name, version, environment_name, host_or_cluster in left_installations:
        left_by_artifact[name].append(
            {
                "environment_name": environment_name,
                "version": version,
                "host_or_cluster": host_or_cluster,
            }
        )

    right_by_artifact: dict[str, list[EnvironmentVersion]] = defaultdict(list)
    for name, version, environment_name, host_or_cluster in right_installations:
        right_by_artifact[name].append(
            {
                "environment_name": environment_name,
                "version": version,
                "host_or_cluster": host_or_cluster,
            }
        )

    items: list[DiffItem] = []
    for name in sorted(set(left_by_artifact) | set(right_by_artifact)):
        left_entries = sorted(
            left_by_artifact.get(name, []), key=lambda e: e["environment_name"]
        )
        right_entries = sorted(
            right_by_artifact.get(name, []), key=lambda e: e["environment_name"]
        )

        status: DiffStatus
        if left_entries and right_entries:
            left_versions = {e["version"] for e in left_entries}
            right_versions = {e["version"] for e in right_entries}
            status = "same" if left_versions == right_versions else "different"
        elif left_entries:
            status = "left_only"
        else:
            status = "right_only"

        items.append(
            {
                "artifact_name": name,
                "left": left_entries,
                "right": right_entries,
                "status": status,
            }
        )
    return items
