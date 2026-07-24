"""
Getting a Luanti onto the machine.

Every desktop platform downloads its own Luanti, so that ``miney init`` is the whole
installation on all three and a beginner never picks a file out of a release page.
Windows and macOS take the official release ZIPs. Luanti publishes no Linux build at
all, so Linux takes the AppImage from `pkgforge-dev/Luanti-AppImage
<https://github.com/pkgforge-dev/Luanti-AppImage>`_ - a second source, looked up
separately from Luanti's own releases and always at its newest build.

That AppImage is **unpacked once and then never used as an AppImage again**, which is
not an implementation detail but the reason the Linux path works at all. Launched as an
image it re-unpacks itself into ``/tmp`` on every single start: measured at 6.4 seconds
per ``luanti --version`` against 0.017 seconds for the unpacked tree, which is slow
enough that a cold first check overran the 20-second timeout in
:func:`~miney.env.discover._run_version` and the freshly downloaded Luanti was skipped
as unusable. Unpacking also leaves the image's own ``self-updater.hook`` behind, which
otherwise asks the learner mid-session whether Luanti may update itself and rewrites the
downloaded file in place if they agree. The unpacked tree is an ordinary Luanti: its
``bin/luanti`` is relocatable (sharun) and runs directly, so
:func:`~miney.env.discover.candidate_commands` finds it exactly like a Windows one.

Architectures pkgforge does not build for - anything that is not x86-64 or 64-bit ARM -
still get :func:`install_instructions`, because Miney never runs a privileged command.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from pathlib import Path

from ..exceptions import MineyRunError
from .fetch import Fetcher, extract_all, read_url
from .paths import EnvPaths
from .upstream import Release, parse_release

logger = logging.getLogger(__name__)

#: Where the Linux AppImage builds are published. Deliberately not
#: :data:`~miney.env.upstream.RELEASES_URL`: Luanti's own releases carry no Linux asset,
#: so "the newest Luanti available for Linux" is whatever this repository built last.
APPIMAGE_RELEASES_URL = (
    "https://api.github.com/repos/pkgforge-dev/Luanti-AppImage/releases/latest"
)

#: Asset name patterns, by system and by whether the machine is 64-bit. Matched rather
#: than spelled out because the names carry both the version and, on macOS, the build's
#: minimum OS version ("macos12.3"), neither of which we can hardcode.
_PATTERNS = {
    ("Windows", True): r"win64\.zip$",
    ("Windows", False): r"win32\.zip$",
    ("Darwin", True): r"macos[\d.]*_arm64\.zip$",
    ("Darwin", False): r"macos[\d.]*_x86_64\.zip$",
}

#: Asset name patterns for Linux, by architecture. Anchored on ``.AppImage`` because
#: every image is published next to a ``.AppImage.zsync`` of the same name that sorts
#: first and holds update metadata rather than a program.
_LINUX_PATTERNS = {
    "x86_64": r"anylinux-x86_64\.AppImage$",
    "aarch64": r"anylinux-aarch64\.AppImage$",
}

#: The AppImage tag is "5.16.1-1@2026-07-22_1784722284": the Luanti version, then a
#: build number and the build's timestamp. Only the leading version is read, so this
#: pattern deliberately does not anchor at the end the way Luanti's own tags do.
_APPIMAGE_TAG_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")

#: Machine strings that mean "64-bit ARM". platform.machine() is not standardised.
_ARM64 = ("arm64", "aarch64")

#: Machine strings that mean "64-bit Intel or AMD", for the same reason.
_X86_64 = ("x86_64", "amd64")

#: First four bytes of every Linux executable. An AppImage is one, so this separates a
#: real download from an error page that arrived with a 200 status.
_ELF_MAGIC = b"\x7fELF"


def asset_pattern(system: str, machine: str) -> str | None:
    """
    The regular expression matching this platform's release asset.

    :param system: As :func:`platform.system` reports it.
    :param machine: As :func:`platform.machine` reports it.
    :return: The pattern, or None if Miney has no download for this platform, which
        today means a Linux machine that is neither x86-64 nor 64-bit ARM.
    """
    lowered = machine.lower()
    if system == "Darwin":
        return _PATTERNS[("Darwin", lowered in _ARM64)]
    if system == "Windows":
        return _PATTERNS[("Windows", lowered in (*_X86_64, *_ARM64))]
    if system == "Linux":
        if lowered in _ARM64:
            return _LINUX_PATTERNS["aarch64"]
        if lowered in _X86_64:
            return _LINUX_PATTERNS["x86_64"]
    return None


def appimage_release(fetch: Fetcher | None = None) -> Release | None:
    """
    The newest published Linux AppImage build.

    Not cached, unlike :func:`~miney.env.upstream.latest_release`: this is only ever
    asked when there is no Luanti on the machine at all, which happens once.

    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :return: The release, or None if the response could not be understood.
    :raises MineyRunError: If the request itself failed.
    """
    payload = fetch(APPIMAGE_RELEASES_URL) if fetch else read_url(APPIMAGE_RELEASES_URL)
    return parse_release(payload, _APPIMAGE_TAG_RE)


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


def can_acquire(system: str | None = None, machine: str | None = None) -> bool:
    """
    Whether Miney can download Luanti itself on this platform.

    Architecture matters, not just the operating system: Windows and macOS have an asset
    for every machine they run on, while the Linux AppImage is built for x86-64 and
    64-bit ARM only.

    :param system: As :func:`platform.system` reports it. Defaults to this machine.
    :param machine: As :func:`platform.machine` reports it. Defaults to this machine.
    :return: True when there is a download for this platform.
    """
    return (
        asset_pattern(system or platform.system(), machine or platform.machine())
        is not None
    )


def install_instructions(release: Release | None) -> str:
    """
    What to tell a user Miney has no download for.

    Reached only on a Linux machine outside the two architectures the AppImage is built
    for, so it is genuinely rare - but it must still get that user running, and Miney
    never runs a privileged command, so they run it themselves. The message names the
    version Flathub would give, because a distribution package can be older than the 5.7
    the Miney mod needs and there is no way to tell from here.

    :param release: The current release, if it could be looked up. Without one the
        message drops the version rather than guessing at it.
    :return: A complete, printable message.
    """
    current = f" (currently {release.tag})" if release is not None else ""
    return (
        "Miney has no Luanti download for this computer's processor, so Luanti has to\n"
        "be installed with your package manager. Miney never runs a command as root -\n"
        "please run one of these:\n"
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
    :param release: The release to install. Ignored on Linux, which has its own source -
        see :func:`appimage_release`.
    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :param system: As :func:`platform.system` reports it. Defaults to this machine.
    :param machine: As :func:`platform.machine` reports it. Defaults to this machine.
    :return: The directory Luanti was unpacked into.
    :raises MineyRunError: On a platform Miney has no download for, when the release
        could not be looked up, or when the download or extraction failed.
    """
    this_system = system or platform.system()
    this_machine = machine or platform.machine()

    if not can_acquire(this_system, this_machine):
        raise MineyRunError(install_instructions(release))

    if this_system == "Linux":
        # The caller looked up Luanti's own release, which has nothing in it for Linux.
        # Whatever the AppImage repository built last *is* the newest Luanti available
        # here, so it is taken as-is and never compared against the upstream version.
        release = appimage_release(fetch)

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

    if this_system == "Linux":
        return _install_appimage(paths, data)

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

    return swap_in(paths, staging)


#: What in a Luanti install belongs to the user rather than to the engine, and is
#: therefore carried across an upgrade. Everything not named here - the executable, the
#: libraries, ``builtin``, ``locale``, ``fonts``, ``doc`` - comes fresh out of the
#: download, so no file from the old version can survive as an orphan.
#:
#: A directory on this list is merged rather than replaced: the new install keeps what
#: it brought (``games/devtest``, ``textures/base``) and only gains what it does not
#: have (``games/minetest_game``, a texture pack). Inside these paths everything is the
#: user's, so there is nothing to tell apart.
USER_PATHS = (
    "worlds",
    "games",
    "mods",
    "clientmods",
    "textures",
    "screenshots",
)

#: Files directly in the install directory that belong to the user. Luanti writes its
#: settings next to the executable in a portable install, which is what Miney sets up.
USER_FILE_SUFFIXES = (".conf",)


def _carry_over(old: Path, new: Path) -> None:
    """
    Move the user's own files from an old Luanti install into the new one.

    Only the paths in :data:`USER_PATHS` and settings files are considered, and only
    where the new install has nothing of that name - which is what keeps a stale engine
    file from creeping back in while the learner's worlds, games and mods survive the
    upgrade.

    Never raises. A file that cannot be moved is not worth failing an upgrade over, and
    the old install is kept until the swap has succeeded anyway.

    :param old: The install being replaced.
    :param new: The unpacked new install, which is what will be kept.
    """
    for name in USER_PATHS:
        source = old / name
        if source.is_dir():
            _merge_into(source, new / name)

    for item in old.iterdir():
        if item.is_file() and item.suffix in USER_FILE_SUFFIXES:
            _move(item, new / item.name)


def _merge_into(source: Path, target: Path) -> None:
    """
    Add everything from ``source`` that ``target`` does not already have.

    :param source: A directory in the old install.
    :param target: The same directory in the new install, which may not exist yet.
    """
    if not target.exists():
        _move(source, target)
        return
    if not target.is_dir():
        return
    for item in source.iterdir():
        if item.is_dir():
            _merge_into(item, target / item.name)
        else:
            _move(item, target / item.name)


def _move(source: Path, target: Path) -> None:
    """
    Move one file or directory, unless the target is already there.

    :param source: What to move.
    :param target: Where it should end up.
    """
    if target.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except OSError as error:
        logger.debug("Could not carry %s over to %s: %s", source, target, error)


def swap_in(paths: EnvPaths, unpacked: Path) -> Path:
    """
    Put a freshly unpacked Luanti in place of the installed one.

    Two renames rather than "delete the old, then rename the new": a rename fails
    outright when something in the directory is still in use, at a point where nothing
    has been touched yet, while a delete works file by file and can stop halfway,
    leaving a half-removed install that still looks startable. The old directory is
    only removed once the new one is in place.

    :param paths: The environment. Luanti ends up in ``paths.luanti_dir``.
    :param unpacked: The new install, already extracted and checked.
    :return: ``paths.luanti_dir``.
    :raises MineyRunError: If the installed Luanti could not be moved out of the way,
        which is what happens while it is running.
    """
    target = paths.luanti_dir
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        unpacked.rename(target)
        return target

    # Move the old install aside first, before anything is carried out of it. The other
    # way round, a rename that fails here would leave the still-installed Luanti robbed
    # of its games and worlds.
    previous = target.with_name(target.name + ".old")
    shutil.rmtree(previous, ignore_errors=True)
    try:
        target.rename(previous)
    except OSError as error:
        raise MineyRunError(
            f"Could not replace the Luanti in {target}: {error}\n"
            "This normally means it is still running. Close the game window and stop "
            "the server, then try again:\n"
            "  uv run miney stop\n"
            "Nothing was changed, so the Luanti you have is untouched."
        ) from error
    _carry_over(previous, unpacked)
    unpacked.rename(target)
    shutil.rmtree(previous, ignore_errors=True)
    return target


def _extract_appimage(image: Path, into: Path) -> Path:
    """
    Unpack a downloaded AppImage by running it.

    An AppImage carries its own unpacker, so this is the one place in Miney that
    executes something it just downloaded - unavoidable, and no worse than the launch
    that follows a moment later. A named function so tests can replace it without a real
    image.

    The unpacked tree is called ``AppDir`` by the runtime pkgforge uses; the ``AppImage``
    convention is ``squashfs-root``, which that runtime leaves behind as a symlink to the
    same place. Both are accepted so a change of runtime upstream cannot break this
    silently.

    :param image: The downloaded AppImage, already executable.
    :param into: Directory to unpack into, which is where the runtime writes.
    :return: The unpacked directory.
    :raises MineyRunError: If the image could not be run or refused to unpack.
    """
    try:
        subprocess.run(
            [str(image), "--appimage-extract"],
            cwd=str(into),
            capture_output=True,
            timeout=600,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MineyRunError(
            f"The Luanti download could not unpack itself: {error}\n"
            "Install Luanti yourself instead:\n"
            "  flatpak install flathub org.luanti.luanti\n"
            "Then run this again:\n"
            "  uv run miney start"
        ) from error
    unpacked = into / "AppDir"
    return unpacked if unpacked.is_dir() else (into / "squashfs-root").resolve()


def _install_appimage(paths: EnvPaths, data: bytes) -> Path:
    """
    Turn a downloaded AppImage into the shared Luanti install.

    Staged exactly like the Windows download: nothing touches an existing, working
    Luanti until the new one has been unpacked and checked. The image itself is deleted
    afterwards - it is 40 MB holding a copy of the 133 MB just written next to it.

    :param paths: The environment. Luanti lands in ``paths.luanti_dir``.
    :param data: The downloaded AppImage.
    :return: The directory Luanti was unpacked into.
    :raises MineyRunError: If the download is not a program, could not be unpacked, or
        unpacked without a ``bin/luanti`` in it.
    """
    if not data.startswith(_ELF_MAGIC):
        raise MineyRunError(
            f"The download is not a Linux program ({len(data)} bytes). "
            "It may have been an error page rather than a file."
        )

    staging = paths.luanti_dir.with_name(paths.luanti_dir.name + ".new")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        image = staging / "luanti.AppImage"
        image.write_bytes(data)
        image.chmod(0o755)
        unpacked = _extract_appimage(image, staging)
        if not (unpacked / "bin" / "luanti").is_file():
            raise MineyRunError(
                "The Luanti download unpacked without a bin/luanti in it, so there is "
                "nothing to start.\n"
                "Install Luanti yourself instead:\n"
                "  flatpak install flathub org.luanti.luanti\n"
                "Then run this again:\n"
                "  uv run miney start"
            )
        image.unlink()
        swap_in(paths, unpacked)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
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
