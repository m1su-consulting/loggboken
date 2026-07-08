from unittest.mock import AsyncMock

import pytest

import app.ingestion as ingestion_module
from app.api.v1.schemas import IngestRequest
from app.errors import ApiError
from app.parsers.base import ArtifactInstallation, ParserError


class _FakeParser:
    def __init__(self, result: list | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def parse(self, data: dict) -> list:
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture(autouse=True)
def _mock_record_failure(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.repositories.ingestion_failures.record_failure", mock)
    return mock


def _installation() -> ArtifactInstallation:
    return ArtifactInstallation(
        environment_name="env",
        source_type="rpm",
        artifact_name="curl",
        artifact_version="1.0",
        raw_data={},
    )


async def test_returns_parsed_installations_on_success(
    monkeypatch: pytest.MonkeyPatch, _mock_record_failure: AsyncMock
) -> None:
    installation = _installation()
    monkeypatch.setattr(
        ingestion_module, "get_parser", lambda source_type: _FakeParser(result=[installation])
    )
    body = IngestRequest(source_type="rpm", data={"host": "x"})

    result = await ingestion_module.parse_or_record_failure(
        AsyncMock(), endpoint="installations", body=body
    )

    assert result == [installation]
    _mock_record_failure.assert_not_called()


async def test_parser_error_is_recorded_and_raised_as_invalid_payload(
    monkeypatch: pytest.MonkeyPatch, _mock_record_failure: AsyncMock
) -> None:
    monkeypatch.setattr(
        ingestion_module,
        "get_parser",
        lambda source_type: _FakeParser(error=ParserError("saknar host")),
    )
    body = IngestRequest(source_type="rpm", data={"packages": []})

    with pytest.raises(ApiError) as exc_info:
        await ingestion_module.parse_or_record_failure(
            AsyncMock(), endpoint="installations", body=body
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.error == "invalid_payload"
    assert exc_info.value.detail == "saknar host"
    _mock_record_failure.assert_awaited_once()
    _, kwargs = _mock_record_failure.call_args
    assert kwargs["endpoint"] == "installations"
    assert kwargs["error"] == "invalid_payload"


async def test_empty_result_is_a_failure_by_default(
    monkeypatch: pytest.MonkeyPatch, _mock_record_failure: AsyncMock
) -> None:
    monkeypatch.setattr(ingestion_module, "get_parser", lambda source_type: _FakeParser(result=[]))
    body = IngestRequest(source_type="rpm", data={"host": "x"})

    with pytest.raises(ApiError) as exc_info:
        await ingestion_module.parse_or_record_failure(
            AsyncMock(), endpoint="installations", body=body
        )

    assert exc_info.value.error == "empty_payload"
    _mock_record_failure.assert_awaited_once()


async def test_empty_result_is_allowed_when_allow_empty_is_set(
    monkeypatch: pytest.MonkeyPatch, _mock_record_failure: AsyncMock
) -> None:
    monkeypatch.setattr(ingestion_module, "get_parser", lambda source_type: _FakeParser(result=[]))
    body = IngestRequest(source_type="rpm", data={"host": "x"})

    result = await ingestion_module.parse_or_record_failure(
        AsyncMock(), endpoint="snapshot", body=body, allow_empty=True
    )

    assert result == []
    _mock_record_failure.assert_not_called()


async def test_unsupported_source_type_is_recorded_and_raised(
    _mock_record_failure: AsyncMock,
) -> None:
    body = IngestRequest(source_type="windows", data={"host": "x"})

    with pytest.raises(ApiError) as exc_info:
        await ingestion_module.parse_or_record_failure(
            AsyncMock(), endpoint="installations", body=body
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.error == "unsupported_source"
    _mock_record_failure.assert_awaited_once()


async def test_record_and_raise_records_then_raises_given_error(
    _mock_record_failure: AsyncMock,
) -> None:
    body = IngestRequest(source_type="rpm", data={"host": "x"})
    api_error = ApiError(status_code=400, error="source_type_mismatch", detail="fel typ")

    with pytest.raises(ApiError) as exc_info:
        await ingestion_module.record_and_raise(
            AsyncMock(), endpoint="snapshot", body=body, api_error=api_error
        )

    assert exc_info.value is api_error
    _mock_record_failure.assert_awaited_once()
    _, kwargs = _mock_record_failure.call_args
    assert kwargs["error"] == "source_type_mismatch"
