"""Tests for miney.env.pypi."""
import json

from miney.env.pypi import latest_version, parse_version
from miney.exceptions import MineyRunError


def payload(version: str) -> bytes:
    return json.dumps({"info": {"name": "miney", "version": version}}).encode()


def test_parse_version_reads_a_plain_release():
    assert parse_version("0.7.0") == (0, 7, 0)


def test_parse_version_fills_in_a_missing_patch():
    assert parse_version("1.2") == (1, 2, 0)


def test_parse_version_rejects_a_prerelease():
    # Half-reading "0.7.0rc1" as 0.7.0 would tell a user on the final 0.7.0 to upgrade
    # to what they already have. No answer is the safe answer.
    assert parse_version("0.7.0rc1") is None
    assert parse_version("0.7.0.dev3") is None


def test_latest_version_reads_the_pypi_answer():
    assert latest_version(lambda url: payload("0.7.1")) == (0, 7, 1)


def test_latest_version_returns_none_when_pypi_cannot_be_reached():
    def fail(url: str) -> bytes:
        raise MineyRunError("no network")

    assert latest_version(fail) is None


def test_latest_version_returns_none_for_garbage():
    assert latest_version(lambda url: b"<html>not json</html>") is None


def test_latest_version_returns_none_when_the_field_is_missing():
    assert latest_version(lambda url: json.dumps({"info": {}}).encode()) is None


def test_latest_version_returns_none_for_an_unparsable_version():
    assert latest_version(lambda url: payload("nightly")) is None
