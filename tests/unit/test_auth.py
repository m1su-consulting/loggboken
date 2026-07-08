import pytest

from app.auth import check_source_type_access, require_api_key
from app.config import ApiKeyConfig, settings
from app.errors import ApiError


async def test_require_api_key_missing_header_raises_401() -> None:
    with pytest.raises(ApiError) as exc_info:
        await require_api_key(x_api_key=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error == "missing_api_key"


async def test_require_api_key_unknown_key_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_keys", {})

    with pytest.raises(ApiError) as exc_info:
        await require_api_key(x_api_key="does-not-exist")

    assert exc_info.value.status_code == 401
    assert exc_info.value.error == "invalid_api_key"


async def test_require_api_key_valid_key_returns_its_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_config = ApiKeyConfig(client="test-client", source_types=["rpm"])
    monkeypatch.setattr(settings, "api_keys", {"good-key": key_config})

    result = await require_api_key(x_api_key="good-key")

    assert result is key_config


def test_check_source_type_access_allows_unrestricted_key() -> None:
    key = ApiKeyConfig(client="admin", source_types=None)

    check_source_type_access(key, "rpm")
    check_source_type_access(key, "kubernetes")


def test_check_source_type_access_allows_matching_source_type() -> None:
    key = ApiKeyConfig(client="rpm-agent", source_types=["rpm"])

    check_source_type_access(key, "rpm")


def test_check_source_type_access_rejects_mismatched_source_type() -> None:
    key = ApiKeyConfig(client="rpm-agent", source_types=["rpm"])

    with pytest.raises(ApiError) as exc_info:
        check_source_type_access(key, "kubernetes")

    assert exc_info.value.status_code == 403
    assert exc_info.value.error == "source_type_forbidden"
