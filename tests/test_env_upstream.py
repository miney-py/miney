"""Tests for miney.env.upstream."""
import json
from pathlib import Path

from miney.env.paths import EnvPaths
from miney.env.upstream import Release, latest_release, parse_release
from miney.exceptions import MineyRunError

PAYLOAD = json.dumps(
    {
        "tag_name": "5.16.1",
        "assets": [
            {
                "name": "luanti-5.16.1-win64.zip",
                "browser_download_url": "https://example.invalid/win64.zip",
                "size": 17408000,
            },
            {
                "name": "luanti_5.16.1-macos12.3_arm64.zip",
                "browser_download_url": "https://example.invalid/mac-arm.zip",
                "size": 13400000,
            },
        ],
    }
).encode()


def test_parse_release_reads_the_version_and_the_assets():
    release = parse_release(PAYLOAD)
    assert release is not None
    assert release.version == (5, 16, 1)
    assert release.tag == "5.16.1"
    assert release.assets["luanti-5.16.1-win64.zip"] == "https://example.invalid/win64.zip"


def test_parse_release_accepts_a_v_prefixed_tag():
    payload = json.dumps({"tag_name": "v5.9.0", "assets": []}).encode()
    release = parse_release(payload)
    assert release is not None
    assert release.version == (5, 9, 0)


def test_parse_release_returns_none_for_an_unparsable_tag():
    # A guessed comparison is worse than no comparison: no warning is the safe answer.
    payload = json.dumps({"tag_name": "nightly", "assets": []}).encode()
    assert parse_release(payload) is None


def test_parse_release_returns_none_for_junk():
    assert parse_release(b"<html>rate limited</html>") is None


def test_latest_release_caches_the_answer(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return PAYLOAD

    first = latest_release(paths, fetch=fetch, now=1000.0)
    second = latest_release(paths, fetch=fetch, now=1000.0 + 3600)
    assert first == second
    assert len(calls) == 1, "the second call inside a day must come from the cache"


def test_latest_release_refetches_once_the_cache_is_a_day_old(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return PAYLOAD

    latest_release(paths, fetch=fetch, now=1000.0)
    latest_release(paths, fetch=fetch, now=1000.0 + 86401)
    assert len(calls) == 2


def test_latest_release_survives_a_network_failure(tmp_path: Path):
    # A version check must never be the thing that breaks someone's first script.
    paths = EnvPaths(root=tmp_path / ".miney")

    def fetch(url: str) -> bytes:
        raise MineyRunError("no network")

    assert latest_release(paths, fetch=fetch, now=1000.0) is None


def test_latest_release_survives_a_corrupt_cache(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    paths.upstream_cache.write_text("{not json", encoding="utf-8")

    release = latest_release(paths, fetch=lambda url: PAYLOAD, now=1000.0)
    assert release is not None
    assert release.version == (5, 16, 1)


def test_latest_release_works_without_an_environment():
    # miney status outside a project still wants the check; it just cannot cache.
    release = latest_release(None, fetch=lambda url: PAYLOAD, now=1000.0)
    assert release is not None
    assert release.version == (5, 16, 1)
