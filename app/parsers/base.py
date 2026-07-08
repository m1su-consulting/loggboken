from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel


class ArtifactInstallation(BaseModel):
    """Normaliserad representation av en artefakt installerad i en miljö,
    oavsett vilket källsystem den kom ifrån."""

    environment_name: str
    source_type: str
    host_or_cluster: str | None = None
    environment_metadata: dict[str, Any] | None = None
    artifact_name: str
    artifact_version: str
    raw_data: dict[str, Any] = {}


class ParserError(Exception):
    """Payloaden saknar den grundstruktur som krävs för att kunna tolkas alls
    (t.ex. saknat toppnivåfält). Skiljs från enskilda trasiga poster i en
    i övrigt giltig lista, vilka hoppas över istället för att krascha hela requesten."""


class BaseSourceParser(ABC):
    source_type: ClassVar[str]

    @abstractmethod
    def parse(self, raw_json: dict[str, Any]) -> list[ArtifactInstallation]:
        """Tolkar en källsystem-specifik payload till en lista av ArtifactInstallation.

        Höjer ParserError om toppnivåstrukturen är trasig. Enskilda poster i en
        i övrigt giltig lista som inte går att tolka hoppas över tyst i listan
        (loggas som warning) snarare än att hela anropet kraschar.
        """
        raise NotImplementedError
