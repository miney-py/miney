"""
Finding a Luanti that is new enough to run the Miney mod, and describing how to start it.

This is the only module that knows about platform differences. It returns a launch
prefix - either a plain executable path, or a ``flatpak run`` invocation - so that the
rest of the package never learns where Luanti came from.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .paths import EnvPaths

logger = logging.getLogger(__name__)

#: Lowest Luanti version the Miney mod supports, mirroring mod_data/miney/mod.conf.
#: 5.9 is where ``core.dynamic_add_media`` learned to take the file contents directly
#: instead of a path on the server's disk, which is what lets a script send an image it
#: made in Python to a player. Nothing older is worth carrying for it.
MIN_VERSION = (5, 9, 0)

#: :data:`MIN_VERSION` as it is written for people, e.g. ``"5.9"``.
MIN_VERSION_TEXT = ".".join(str(part) for part in MIN_VERSION[:2])

FLATPAK_APP_ID = "org.luanti.luanti"

_VERSION_RE = re.compile(r"^(?:Luanti|Minetest)\s+(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)


@dataclass(frozen=True)
class LuantiInstall:
    """
    A usable Luanti and how to start it.

    :param launch: Command prefix. Arguments are appended to this list.
    :param version: Version as a comparable tuple.
    :param source: Where it came from - "bundled", "path" or "flatpak". For messages only.
    """

    launch: list[str]
    version: tuple[int, int, int]
    source: str


def parse_version(text: str) -> tuple[int, int, int] | None:
    """
    Read the version out of ``luanti --version`` output.

    :param text: The captured output.
    :return: The version, or None if it could not be parsed. An unparsable version is
        never guessed at - callers treat None as "not usable".
    """
    for line in text.splitlines():
        match = _VERSION_RE.match(line.strip())
        if match:
            major, minor, patch = match.groups()
            return int(major), int(minor), int(patch or 0)
    return None


def _bundled_launch(luanti_dir: Path) -> list[str] | None:
    """
    The launch command for a Luanti unpacked into the shared install, if there is one.

    The layout differs by platform, so both are checked. Windows and Linux releases put
    the executable in ``bin/``; official macOS releases ship a ``luanti.app`` bundle with
    the executable at ``luanti.app/Contents/MacOS/luanti``. Without the macOS branch a
    Luanti downloaded on macOS would never be found again after the download.

    :param luanti_dir: The shared ``Luanti`` directory (see :func:`~miney.env.paths.default_luanti_dir`).
    :return: The launch prefix as a one-element list, or None if nothing is there.
    """
    for name in ("luanti.exe", "luanti", "minetest.exe", "minetest"):
        bundled = luanti_dir / "bin" / name
        if bundled.is_file():
            return [str(bundled)]
    for app in ("luanti.app", "minetest.app"):
        for name in ("luanti", "minetest"):
            bundled = luanti_dir / app / "Contents" / "MacOS" / name
            if bundled.is_file():
                return [str(bundled)]
    return None


def candidate_commands(paths: EnvPaths | None) -> list[tuple[list[str], str]]:
    """
    Every place a Luanti might be, best first.

    :param paths: The environment, if one exists. A Luanti in the shared install wins
        over anything installed on the system, so every Miney project runs the same one.
    :return: Pairs of launch prefix and source label.
    """
    candidates: list[tuple[list[str], str]] = []

    if paths is not None:
        bundled = _bundled_launch(paths.luanti_dir)
        if bundled is not None:
            candidates.append((bundled, "bundled"))

    for name in ("luanti", "minetest"):
        found = shutil.which(name)
        if found:
            candidates.append(([found], "path"))

    flatpak = shutil.which("flatpak")
    if flatpak and paths is not None:
        # A sandboxed Luanti has to reach both the project's world files and the shared
        # games directory, which now lives outside the project in ~/Luanti/games.
        candidates.append(
            (
                [
                    flatpak,
                    "run",
                    f"--filesystem={paths.root.resolve()}",
                    f"--filesystem={paths.luanti_dir.resolve()}",
                    FLATPAK_APP_ID,
                ],
                "flatpak",
            )
        )
    elif flatpak:
        candidates.append(([flatpak, "run", FLATPAK_APP_ID], "flatpak"))

    if platform.system() == "Darwin":
        app = Path("/Applications/luanti.app/Contents/MacOS/luanti")
        if app.is_file():
            candidates.append(([str(app)], "path"))

    return candidates


def _run_version(command: list[str]) -> str | None:
    """
    Run a candidate with ``--version`` and capture its output.

    :param command: The launch prefix to test.
    :return: The captured output, or None if the command could not be run.
    """
    try:
        result = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            # No explicit env is passed. Stage 0 verification confirmed a game-path
            # variable is needed to *run* a world (see process.game_env), but --version
            # loads no game, so this call does not need one.
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{result.stdout}\n{result.stderr}"


def discover(
    paths: EnvPaths | None = None,
    runner: Callable[[list[str]], str | None] | None = None,
    candidates: Callable[[EnvPaths | None], list[tuple[list[str], str]]] | None = None,
) -> LuantiInstall | None:
    """
    Find the first Luanti that is at least :data:`MIN_VERSION`.

    :param paths: The environment, if one exists.
    :param runner: Substitutable "run this and give me its --version output" step.
    :param candidates: Substitutable candidate list, for testing.
    :return: The install to use, or None if nothing suitable was found.
    """
    run = runner or _run_version
    build = candidates or candidate_commands

    for command, source in build(paths):
        output = run(command)
        if output is None:
            continue
        version = parse_version(output)
        if version is None:
            logger.debug("Could not read a version from %s", command)
            continue
        if version < MIN_VERSION:
            logger.debug("Ignoring Luanti %s at %s, need %s", version, command, MIN_VERSION)
            continue
        return LuantiInstall(launch=command, version=version, source=source)
    return None


def outdated_version(
    paths: EnvPaths | None = None,
    runner: Callable[[list[str]], str | None] | None = None,
    candidates: Callable[[EnvPaths | None], list[tuple[list[str], str]]] | None = None,
) -> tuple[int, int, int] | None:
    """
    The newest Luanti found that is too old to use, if any.

    :func:`discover` returns None both when no Luanti exists at all and when the only
    ones it found are below :data:`MIN_VERSION`. On a platform where Miney cannot
    download a Luanti itself, those two cases need different advice: a user who already
    has an old Luanti should be told to upgrade the one they have and by how much, not
    told to install Luanti from scratch. This reports the version that lets the caller
    say so.

    :param paths: The environment, if one exists.
    :param runner: Substitutable "run this and give me its --version output" step.
    :param candidates: Substitutable candidate list, for testing.
    :return: The highest below-:data:`MIN_VERSION` version found, or None if every
        candidate was either usable or could not be run.
    """
    run = runner or _run_version
    build = candidates or candidate_commands

    best: tuple[int, int, int] | None = None
    for command, _source in build(paths):
        output = run(command)
        if output is None:
            continue
        version = parse_version(output)
        if version is None or version >= MIN_VERSION:
            continue
        if best is None or version > best:
            best = version
    return best
