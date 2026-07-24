"""
Reading bytes and ZIP archives over HTTP.

The only module in :mod:`miney.env` that calls :mod:`urllib`. Everything above it takes
a fetcher argument instead, so no test needs the network.
"""
from __future__ import annotations

import http.client
import io
import logging
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from ..exceptions import MineyRunError

logger = logging.getLogger(__name__)

#: "Give me the bytes at this URL." Substitutable so tests never reach the network.
Fetcher = Callable[[str], bytes]

#: Sent on every request. GitHub rejects requests without one.
USER_AGENT = "miney"


def read_url(url: str, timeout: float = 30.0) -> bytes:
    """
    Read a URL into memory.

    :param url: The URL to read.
    :param timeout: Seconds to wait before giving up.
    :return: The response body.
    :raises MineyRunError: If the request failed for any reason.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    logger.debug("Fetching %s", url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise MineyRunError(f"{url} returned HTTP {error.code}.") from error
    except http.client.IncompleteRead as error:
        # The server closed the connection mid-transfer, or Content-Length did not match
        # the bytes delivered - a truncated download on a flaky connection. IncompleteRead
        # is an HTTPException, not an OSError or URLError, so it needs catching on its own.
        raise MineyRunError(
            f"The download from {url} was cut short before it finished.\n"
            "This usually means a flaky connection - please try again."
        ) from error
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        raise MineyRunError(f"Could not reach {url}: {error}") from error


def _open(data: bytes) -> zipfile.ZipFile:
    """
    Open an in-memory ZIP.

    :param data: The archive.
    :return: The opened archive.
    :raises MineyRunError: If the bytes are not a ZIP archive.
    """
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise MineyRunError(
            f"The download is not a ZIP archive ({len(data)} bytes). "
            "It may have been an error page rather than a file."
        ) from error


def _disk_error(target: Path, error: OSError) -> MineyRunError:
    """
    Turn a filesystem failure during extraction into a message a beginner can act on.

    Extracting ~17 MB of Luanti plus a game through a staging copy needs roughly twice
    that in free space, so running out mid-extract is a realistic beginner failure. Left
    raw, an ``ENOSPC`` ``OSError`` reaches the CLI's catch-all and is reported as a bug in
    Miney; named here, it tells the user what to do.

    :param target: Where the extraction was writing.
    :param error: The filesystem error that stopped it.
    :return: A :class:`~miney.exceptions.MineyRunError` describing the likely cause.
    """
    return MineyRunError(
        f"Could not write to {target} while unpacking the download: {error}\n"
        "This usually means the disk is full - free up some space and try again."
    )


def _check_safe(archive: zipfile.ZipFile, target: Path) -> None:
    """
    Refuse an archive whose entries would write outside the target.

    A downloaded ZIP is untrusted input, and ``extractall`` on its own will happily
    follow ``../`` out of the directory it was given.

    :param archive: The opened archive.
    :param target: Where it is about to be extracted.
    :raises MineyRunError: If any entry escapes the target.
    """
    root = target.resolve()
    for name in archive.namelist():
        destination = (root / name).resolve()
        if destination != root and root not in destination.parents:
            raise MineyRunError(f"Archive entry '{name}' has an unsafe path.")


def extract_all(data: bytes, target: Path) -> Path:
    """
    Extract a whole archive into a directory.

    :param data: The archive.
    :param target: Directory to extract into. Created if it does not exist.
    :return: The target directory.
    :raises MineyRunError: If the bytes are not a ZIP, an entry escapes the target, or
        the archive could not be written to disk.
    """
    with _open(data) as archive:
        _check_safe(archive, target)
        try:
            target.mkdir(parents=True, exist_ok=True)
            archive.extractall(target)
        except OSError as error:
            raise _disk_error(target, error) from error
    return target


def _top_level_roots(archive: zipfile.ZipFile) -> set[str]:
    """
    The distinct top-level path components of an archive's entries.

    Entry names are normalized first: an archive built with ``zip -r out.zip .`` run
    from inside the directory it packs stores every entry with a leading ``./``
    (``./game.conf``, ``./textures/foo.png``). Without stripping that prefix, splitting
    on ``/`` would report a single root of ``'.'`` -- which is not a directory the
    archive actually has, it is the archive's own root -- and callers that expect a
    real subdirectory there would then operate on ``target`` itself.

    :param archive: The opened archive.
    :return: The set of top-level components, once entries are normalized.
    """
    roots = set()
    for entry in archive.namelist():
        normalized = entry
        while normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = normalized.strip("/")
        if not normalized or normalized == ".":
            continue
        roots.add(normalized.split("/")[0])
    return roots


def extract_single_dir(data: bytes, target: Path, name: str) -> Path:
    """
    Extract an archive that holds one top-level directory, under a chosen name.

    ContentDB packages are shaped this way. The directory inside the archive is not
    guaranteed to be named after the game id the caller recorded, and for Luanti the
    directory name *is* the game id, so the caller's name wins.

    :param data: The archive.
    :param target: Directory to extract into. Created if it does not exist.
    :param name: Name the extracted directory gets.
    :return: The extracted directory, ``target / name``.
    :raises MineyRunError: If the bytes are not a ZIP, the archive does not have
        exactly one top-level directory, an entry escapes the target, or the archive
        could not be written to disk.
    """
    with _open(data) as archive:
        roots = _top_level_roots(archive)
        if len(roots) != 1:
            raise MineyRunError(
                f"Expected the archive to hold one directory, found {len(roots)}: "
                f"{', '.join(sorted(roots))}"
            )
        _check_safe(archive, target)
        root = roots.pop()
        destination = target / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            # Both the archive's own directory and the destination are removed first.
            # extractall merges into whatever is already there, so a reinstall over an
            # existing game would otherwise leave that game's deleted files behind.
            for stale in {target / root, destination}:
                if stale.is_dir():
                    shutil.rmtree(stale)
            archive.extractall(target)
            extracted = target / root
            if extracted != destination:
                extracted.rename(destination)
        except OSError as error:
            raise _disk_error(target, error) from error
    return destination
