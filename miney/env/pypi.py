"""
Which Miney release is on PyPI.

The counterpart to :mod:`~miney.env.upstream`, which answers the same question for
Luanti. Nothing in here is allowed to raise: a version check that breaks a beginner's
first command is worse than no version check.

Two deliberate differences from ``upstream``. There is no cache, because the one there
exists only for GitHub's 60 requests per hour per IP - a limit a classroom behind one
NAT really does hit - and PyPI has no such limit. And the timeout is short, because
``miney status`` must not sit for half a minute on a machine that is offline.
"""
from __future__ import annotations

import json
import logging
import re

from .fetch import Fetcher, read_url

logger = logging.getLogger(__name__)

#: PyPI's JSON API for the package. ``info.version`` is the newest non-yanked release.
RELEASE_URL = "https://pypi.org/pypi/miney/json"

#: Seconds to wait for PyPI. Short on purpose: this runs inside ``miney status``.
TIMEOUT_SECONDS = 5.0

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """
    Read a version string into a comparable tuple.

    Only plain releases are understood. A pre-release or a development version
    (``0.7.0rc1``, ``0.7.0.dev3``) yields None rather than a guessed comparison, so
    nobody is told to upgrade to something the regex merely half-read.

    :param text: A version as PyPI or ``miney.__version__`` spells it.
    :return: ``(major, minor, patch)``, or None if it is not a plain release.
    """
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def latest_version(fetch: Fetcher | None = None) -> tuple[int, int, int] | None:
    """
    The newest Miney release on PyPI.

    Never raises. No network, PyPI down, an unreadable response, a version string that
    is not a plain release - every one of those is None, and every caller treats None
    as "skip the version check".

    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :return: The version, or None if it could not be determined.
    """
    reader = fetch or (lambda url: read_url(url, timeout=TIMEOUT_SECONDS))
    try:
        payload = reader(RELEASE_URL)
    except Exception as error:  # noqa: BLE001 - a version check is never fatal
        logger.debug("Could not reach PyPI for the current version: %s", error)
        return None

    try:
        version = json.loads(payload)["info"]["version"]
    except (ValueError, KeyError, TypeError) as error:
        logger.debug("Could not read PyPI's answer: %s", error)
        return None
    if not isinstance(version, str):
        return None
    return parse_version(version)
