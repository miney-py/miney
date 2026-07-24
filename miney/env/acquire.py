"""
Getting a Luanti onto the machine.

Official release assets exist for Windows and macOS but not for Linux, which is the
opposite of a problem: on Linux, installing Luanti is one package-manager command that
users type routinely, while on Windows they would have to pick the right file out of
nine release assets. So Windows and macOS download; Linux gets the exact command.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
from pathlib import Path

from ..exceptions import MineyRunError
from .fetch import Fetcher, extract_all, read_url
from .paths import EnvPaths
from .upstream import Release

logger = logging.getLogger(__name__)

#: Systems with an official portable release asset.
ACQUIRABLE_SYSTEMS = ("Windows", "Darwin")

#: Asset name patterns, by system and by whether the machine is 64-bit. Matched rather
#: than spelled out because the names carry both the version and, on macOS, the build's
#: minimum OS version ("macos12.3"), neither of which we can hardcode.
_PATTERNS = {
    ("Windows", True): r"win64\.zip$",
    ("Windows", False): r"win32\.zip$",
    ("Darwin", True): r"macos[\d.]*_arm64\.zip$",
    ("Darwin", False): r"macos[\d.]*_x86_64\.zip$",
}

#: Machine strings that mean "64-bit ARM". platform.machine() is not standardised.
_ARM64 = ("arm64", "aarch64")


def asset_pattern(system: str, machine: str) -> str | None:
    """
    The regular expression matching this platform's release asset.

    :param system: As :func:`platform.system` reports it.
    :param machine: As :func:`platform.machine` reports it.
    :return: The pattern, or None if this platform has no official asset.
    """
    if system == "Darwin":
        return _PATTERNS[("Darwin", machine.lower() in _ARM64)]
    if system == "Windows":
        sixty_four = machine.lower() in ("amd64", "x86_64", "arm64", "aarch64")
        return _PATTERNS[("Windows", sixty_four)]
    return None


def select_asset(release: Release, system: str, machine: str) -> tuple[str, str] | None:
    """
    Pick the asset to download for a platform.

    :param release: The release to choose from.
    :param system: As :func:`platform.system` reports it.
    :param machine: As :func:`platform.machine` reports it.
    :return: Asset name and download URL, or None if this platform has no asset. The
        Windows ``.exe`` installer is never selected: it installs system-wide, and
        Miney does not touch anything outside ``.miney``.
    """
    pattern = asset_pattern(system, machine)
    if pattern is None:
        return None
    matcher = re.compile(pattern)
    for name, url in sorted(release.assets.items()):
        if matcher.search(name):
            return name, url
    return None


def can_acquire(system: str | None = None) -> bool:
    """
    Whether Miney can download Luanti itself on this platform.

    :param system: As :func:`platform.system` reports it. Defaults to this machine.
    :return: True on Windows and macOS, False elsewhere.
    """
    return (system or platform.system()) in ACQUIRABLE_SYSTEMS


def install_instructions(release: Release | None) -> str:
    """
    What to tell a user who has to install Luanti themselves.

    Miney never runs a privileged command, so on Linux the user runs it. The message
    names the version Flathub would give, because a distribution package can be older
    than the 5.7 the Miney mod needs and there is no way to tell from here.

    :param release: The current release, if it could be looked up. Without one the
        message drops the version rather than guessing at it.
    :return: A complete, printable message.
    """
    current = f" (currently {release.tag})" if release is not None else ""
    return (
        "Luanti has no official Linux download, so it has to be installed with your\n"
        "package manager. Miney never runs a command as root - please run one of these:\n"
        "\n"
        f"  Flathub, always the current version{current}:\n"
        "    flatpak install flathub org.luanti.luanti\n"
        "\n"
        "  Your distribution's package, which may be older than the 5.7 the Miney mod\n"
        "  needs - check with 'luanti --version' afterwards:\n"
        "    sudo apt install luanti        # Debian, Ubuntu\n"
        "    sudo dnf install luanti        # Fedora\n"
        "    sudo pacman -S luanti          # Arch\n"
        "\n"
        "Then run this again:\n"
        "  uv run miney start"
    )


def acquire_luanti(
    paths: EnvPaths,
    release: Release | None,
    fetch: Fetcher | None = None,
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    """
    Download Luanti and unpack it into the environment.

    :param paths: The environment. Luanti lands in ``paths.luanti_dir``.
    :param release: The release to install.
    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :param system: As :func:`platform.system` reports it. Defaults to this machine.
    :param machine: As :func:`platform.machine` reports it. Defaults to this machine.
    :return: The directory Luanti was unpacked into.
    :raises MineyRunError: On a platform with no official asset, when the release could
        not be looked up, or when the download or extraction failed.
    """
    this_system = system or platform.system()
    this_machine = machine or platform.machine()

    if not can_acquire(this_system):
        raise MineyRunError(install_instructions(release))

    if release is None:
        raise MineyRunError(
            "Could not reach GitHub to find out which Luanti to download.\n"
            "Check your internet connection, or install Luanti yourself from\n"
            "https://www.luanti.org/downloads/ and run this again:\n"
            "  uv run miney start"
        )

    chosen = select_asset(release, this_system, this_machine)
    if chosen is None:
        raise MineyRunError(
            f"Luanti {release.tag} has no download for {this_system} {this_machine}.\n"
            "Install it yourself from https://www.luanti.org/downloads/ and run this\n"
            "again: uv run miney start"
        )

    name, url = chosen
    logger.debug("Downloading %s from %s", name, url)
    data = fetch(url) if fetch else read_url(url, timeout=300.0)

    # Extract into a staging directory first and only remove the existing install once
    # the download has proven to be a valid archive. Deleting paths.luanti_dir before
    # validating the download would leave a user with no Luanti at all after a
    # corrupted or truncated transfer.
    staging = paths.luanti_dir.with_name(paths.luanti_dir.name + ".new")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        extract_all(data, staging)
        _flatten(staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if paths.luanti_dir.exists():
        shutil.rmtree(paths.luanti_dir)
    staging.rename(paths.luanti_dir)
    return paths.luanti_dir


def _flatten(directory: Path) -> None:
    """
    Move a single wrapping directory's contents up one level.

    The Windows release ZIP wraps everything in ``luanti-<version>-win64/``, but
    :func:`~miney.env.discover.candidate_commands` looks for ``luanti/bin/luanti.exe``,
    one level down and not two.

    A macOS ``.app`` bundle is left alone: it *is* the payload, not a wrapper, and its
    ``Contents`` directory must stay inside it. Collapsing it would move ``Contents`` up
    a level and leave a dismantled bundle that discover cannot find.

    :param directory: The freshly extracted directory.
    """
    entries = list(directory.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        return
    wrapper = entries[0]
    if wrapper.name.endswith(".app"):
        return
    for item in list(wrapper.iterdir()):
        item.rename(directory / item.name)
    wrapper.rmdir()
