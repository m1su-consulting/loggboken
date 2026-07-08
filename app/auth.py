from typing import Annotated

from fastapi import Depends, Header

from app.config import ApiKeyConfig, settings
from app.errors import ApiError


def check_source_type_access(key: ApiKeyConfig, source_type: str) -> None:
    if key.source_types is not None and source_type not in key.source_types:
        raise ApiError(
            status_code=403,
            error="source_type_forbidden",
            detail=(
                f"nyckeln för '{key.client}' har inte skrivbehörighet "
                f"till source_type '{source_type}'"
            ),
        )


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> ApiKeyConfig:
    if not x_api_key:
        raise ApiError(
            status_code=401, error="missing_api_key", detail="X-API-Key-header saknas"
        )

    key = settings.api_keys.get(x_api_key)
    if key is None:
        raise ApiError(status_code=401, error="invalid_api_key", detail="ogiltig API-nyckel")

    return key


ApiKey = Annotated[ApiKeyConfig, Depends(require_api_key)]
