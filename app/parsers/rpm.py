import logging
from typing import Any

from app.parsers.base import ArtifactInstallation, BaseSourceParser, ParserError

logger = logging.getLogger(__name__)


class RpmSourceParser(BaseSourceParser):
    """Tolkar payloads från RPM-baserade källsystem.

    Förväntat payload-format (antaget i brist på exempel från källsystemet,
    se `CLAUDE.md` under "Kvarstående öppna frågor"):

        {
          "host": "web-01.prod.example.com",
          "environment_name": "web-01.prod",   # valfritt, annars = host
          "metadata": {"os": "rhel9"},          # valfritt
          "packages": [
            {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
            ...
          ]
        }
    """

    source_type = "rpm"

    def parse(self, raw_json: dict[str, Any]) -> list[ArtifactInstallation]:
        host = raw_json.get("host")
        if not isinstance(host, str) or not host.strip():
            raise ParserError("saknar giltigt fält 'host'")

        packages = raw_json.get("packages")
        if not isinstance(packages, list):
            raise ParserError("saknar giltigt fält 'packages' (förväntad lista)")

        environment_name = raw_json.get("environment_name") or host
        environment_metadata = raw_json.get("metadata")
        if environment_metadata is not None and not isinstance(environment_metadata, dict):
            environment_metadata = None

        installations: list[ArtifactInstallation] = []
        for package in packages:
            if not isinstance(package, dict):
                logger.warning("hoppar över icke-dict paketpost: %r", package)
                continue

            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not name.strip():
                logger.warning("hoppar över paket utan giltigt namn: %r", package)
                continue
            if not isinstance(version, str) or not version.strip():
                logger.warning("hoppar över paket utan giltig version: %r", package)
                continue

            arch = package.get("arch")
            artifact_version = f"{version}.{arch}" if isinstance(arch, str) and arch.strip() else version

            installations.append(
                ArtifactInstallation(
                    environment_name=environment_name,
                    source_type=self.source_type,
                    host_or_cluster=host,
                    environment_metadata=environment_metadata,
                    artifact_name=name,
                    artifact_version=artifact_version,
                    raw_data=package,
                )
            )

        return installations
