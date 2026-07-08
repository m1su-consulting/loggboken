import pytest

from app.parsers.base import ParserError
from app.parsers.rpm import RpmSourceParser


def test_parses_valid_payload() -> None:
    payload = {
        "host": "web-01.prod.example.com",
        "environment_name": "web-01.prod",
        "metadata": {"os": "rhel9"},
        "packages": [
            {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"},
            {"name": "curl", "version": "7.76.1-14.el9", "arch": "x86_64"},
        ],
    }

    installations = RpmSourceParser().parse(payload)

    assert len(installations) == 2
    first = installations[0]
    assert first.environment_name == "web-01.prod"
    assert first.source_type == "rpm"
    assert first.host_or_cluster == "web-01.prod.example.com"
    assert first.environment_metadata == {"os": "rhel9"}
    assert first.artifact_name == "openssl"
    assert first.artifact_version == "3.0.7-1.el9.x86_64"
    assert first.raw_data == {"name": "openssl", "version": "3.0.7-1.el9", "arch": "x86_64"}


def test_environment_name_falls_back_to_host() -> None:
    payload = {
        "host": "web-02.prod.example.com",
        "packages": [{"name": "curl", "version": "7.76.1-14.el9"}],
    }

    installations = RpmSourceParser().parse(payload)

    assert installations[0].environment_name == "web-02.prod.example.com"
    assert installations[0].artifact_version == "7.76.1-14.el9"


def test_missing_host_raises_parser_error() -> None:
    payload = {"packages": [{"name": "curl", "version": "1.0"}]}

    with pytest.raises(ParserError):
        RpmSourceParser().parse(payload)


def test_missing_packages_raises_parser_error() -> None:
    payload = {"host": "web-01.prod.example.com"}

    with pytest.raises(ParserError):
        RpmSourceParser().parse(payload)


def test_malformed_package_entries_are_skipped_not_crashing() -> None:
    payload = {
        "host": "web-01.prod.example.com",
        "packages": [
            {"name": "openssl", "version": "3.0.7-1.el9"},
            {"name": "no-version"},
            {"version": "1.2.3"},
            "not-a-dict",
            {"name": "", "version": "1.0"},
            None,
        ],
    }

    installations = RpmSourceParser().parse(payload)

    assert len(installations) == 1
    assert installations[0].artifact_name == "openssl"
