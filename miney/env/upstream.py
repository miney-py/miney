"""
Which Luanti release is current.

Answers two questions from one GitHub response: what to download, and whether an
installed Luanti is behind. Nothing in here is allowed to raise - a version check that
breaks a beginner's first script is worse than no version check.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from .fetch import Fetcher, read_url
from .paths import EnvPaths

logger = logging.getLogger(__name__)

#: ``/releases/latest`` excludes drafts and prereleases, which is what we want.
RELEASES_URL = "https://api.github.com/repos/luanti-org/luanti/releases/latest"

#: How long a cached answer stays good. Unauthenticated GitHub allows 60 requests per
#: hour per IP, and a classroom behind one NAT would burn through that.
CACHE_MAX_AGE_SECONDS = 86400

_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True)
class Release:
    """
    One published Luanti release.

    :param version: The version as a comparable tuple.
    :param tag: The tag as GitHub spells it, for messages.
    :param assets: Asset file name to download URL.
    """

    version: tuple[int, int, int]
    tag: str
    assets: dict[str, str]


def parse_release(payload: bytes, tag_pattern: re.Pattern[str] | None = None) -> Release | None:
    """
    Read a GitHub release response.

    :param payload: The raw response body.
    :param tag_pattern: How to read a version out of the tag. Defaults to Luanti's own
        ``5.16.1`` form. :mod:`~miney.env.acquire` passes its own, because the Linux
        AppImage builds are tagged ``5.16.1-1@2026-07-22_1784722284`` - the same
        response shape from a different repository, with a build number and a timestamp
        trailing the version.
    :return: The release, or None if the response could not be understood. An
        unparsable tag yields None rather than a guessed version.
    """
    try:
        data = json.loads(payload)
        tag = str(data["tag_name"])
        assets = {
            str(asset["name"]): str(asset["browser_download_url"])
            for asset in data.get("assets", [])
        }
    except (ValueError, KeyError, TypeError) as error:
        logger.debug("Could not read the release response: %s", error)
        return None

    match = (tag_pattern or _TAG_RE).match(tag.strip())
    if match is None:
        logger.debug("Could not read a version from tag %r", tag)
        return None
    major, minor, patch = match.groups()
    return Release(
        version=(int(major), int(minor), int(patch or 0)), tag=tag, assets=assets
    )


def _read_cache(paths: EnvPaths | None, now: float) -> Release | None:
    """
    The cached release, if there is a fresh one.

    :param paths: The environment, or None when there is none to cache in.
    :param now: Current time as a Unix timestamp.
    :return: The cached release, or None if absent, stale or unreadable.
    """
    if paths is None:
        return None
    try:
        cached = json.loads(paths.upstream_cache.read_text(encoding="utf-8"))
        fetched_at = float(cached["fetched_at"])
        payload = cached["payload"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if now - fetched_at > CACHE_MAX_AGE_SECONDS:
        return None
    return parse_release(payload.encode("utf-8"))


def _write_cache(paths: EnvPaths | None, payload: bytes, now: float) -> None:
    """
    Store a response for reuse.

    A cache that cannot be written is not an error; the next call just asks again.

    :param paths: The environment, or None when there is none to cache in.
    :param payload: The raw response body.
    :param now: Current time as a Unix timestamp.
    """
    if paths is None:
        return
    try:
        paths.root.mkdir(parents=True, exist_ok=True)
        paths.upstream_cache.write_text(
            json.dumps(
                {"fetched_at": now, "payload": payload.decode("utf-8", errors="replace")}
            ),
            encoding="utf-8",
        )
    except OSError as error:
        logger.debug("Could not write the upstream cache: %s", error)


def latest_release(
    paths: EnvPaths | None,
    fetch: Fetcher | None = None,
    now: float | None = None,
) -> Release | None:
    """
    The current Luanti release, from cache when one is fresh enough.

    Never raises. No network, GitHub down, a rate limit, a tag nobody can parse - every
    one of those is None, and every caller treats None as "skip the version check".

    :param paths: The environment to cache in, or None to skip caching.
    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :param now: Current Unix timestamp, for testing. Defaults to the real clock.
    :return: The release, or None if it could not be determined.
    """
    moment = time.time() if now is None else now
    cached = _read_cache(paths, moment)
    if cached is not None:
        return cached

    reader = fetch or read_url
    try:
        payload = reader(RELEASES_URL)
    except Exception as error:  # noqa: BLE001 - a version check is never fatal
        logger.debug("Could not reach GitHub for the current version: %s", error)
        return None

    release = parse_release(payload)
    if release is not None:
        _write_cache(paths, payload, moment)
    return release
