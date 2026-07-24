"""
Turning "I want this world running" into the files, processes and checks that make
it so.

This is the one orchestration layer. Both front ends sit on top of it: the ``miney``
command (:mod:`miney.cli`) and :class:`~miney.luanti.Luanti`'s autostart. The modules
around it stay what they are - :mod:`~miney.env.paths` derives paths,
:mod:`~miney.env.state` stores state, :mod:`~miney.env.discover` finds Luanti,
:mod:`~miney.env.world` writes files, :mod:`~miney.env.process` makes syscalls - and
every decision about *when* to do those things lives here.

Two rules make it usable from a library:

* **Nothing here prints.** Callers pass a ``report`` callback and decide where the
  words go: the command line prints them, the library logs them.
* **Failure is an exception**, always :class:`~miney.exceptions.MineyRunError`, never
  an exit code. Its message names the problem and a command that fixes it.

The front door is small. :func:`find_environment` locates the ``.miney`` directory and
:func:`create_environment` makes one; :func:`ensure_world` brings a world's files up to
date; :func:`is_server_up` is the single definition of "reachable"; and :func:`start`,
:func:`stop` and :func:`remove` do what their names say. :func:`describe` is the
read-only view behind ``miney status``, and :func:`record_foreground_server` /
:func:`clear_foreground_server` / :func:`open_client_when_up` exist for the one case a
front end has to run the server itself, ``miney start --foreground``. Everything else
here is a piece those compose from, public only so that tests can reach it and so that
Stage 2 can grow it without reopening the front ends.

:func:`find_environment` is a thin alias for :func:`~miney.env.paths.find_env`, kept
around (and used by :mod:`miney.cli`) rather than deleted as redundant: it is the
documented front door for this module, the counterpart to
:func:`~miney.env.paths.find_env` that :mod:`~miney.luanti` calls directly. Both bind
the same underlying function; the split exists so each front end reads its own import,
not two names for two different behaviours.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..exceptions import MineyRunError
from . import acquire, contentdb, upstream
from ..luanticlient.probe import probe_server
from .discover import MIN_VERSION, LuantiInstall, discover, outdated_version
from .paths import ENV_DIR_NAME, EnvPaths, find_env
from .process import (
    DEFAULT_PORT,
    client_command,
    find_free_port,
    game_env,
    is_pid_alive,
    is_port_free,
    server_command,
    spawn_detached,
    stop_pid,
)
from .state import WorldState, list_states, load_state, save_state
from .world import (
    DEFAULT_GAME,
    current_player_name,
    ensure_client_password,
    install_mod,
    mod_fingerprint,
    read_world_gameid,
    write_config,
    write_world_mt,
)

logger = logging.getLogger(__name__)

#: The server always listens on the loopback interface, and the learner's client always
#: connects to it there, so the readiness probe asks the same address.
SERVER_HOST = "127.0.0.1"

#: How long to wait for a freshly started server to accept connections, in seconds.
#: A cold start loads the game, compiles the mods and generates the first chunks of a
#: brand-new map, which is minutes of work on a slow disk. Waiting too long costs
#: nothing in practice: a server that dies while starting is noticed the moment its
#: process is gone, so this timeout is only ever reached by a server that is genuinely
#: still busy.
DEFAULT_READY_TIMEOUT = 120.0

#: Seconds between two readiness checks. Not shorter, because every check asks the
#: operating system whether a process is alive, which on Windows means running
#: ``tasklist``; a second of extra latency is invisible next to a boot that takes many.
READY_POLL_INTERVAL = 1.0

#: Games installed up front so switching a world with ``--game`` costs no download later.
#: They land in the shared Luanti install, so this is one download per machine, not per
#: project. minetest_game stays the default every doc example is written against;
#: VoxeLibre (mineclone2) is fetched alongside it and is there the moment someone wants
#: it. Fetching these is best-effort: a world only needs its own game, so a preload that
#: fails is a warning, never a reason to stop a start.
PRELOAD_GAMES = ("minetest_game", "mineclone2")


@dataclass(frozen=True)
class Progress:
    """
    One thing that happened while managing the environment.

    :param message: A complete, human-readable sentence, ready to be shown to a
        beginner as it is.
    :param warning: True when something did not go as intended but was survivable.
        The command line prints those on stderr; the library logs them as warnings.
        The flag is the whole mechanism, so the message itself never opens with
        "Warning:" - the library path would render that as ``WARNING Warning: ...``.
    """

    message: str
    warning: bool = False


#: Where progress goes. ``None`` means "nobody is listening".
Reporter = Callable[[Progress], None]


@dataclass
class StartResult:
    """
    What :func:`start` did.

    :param state: The world's state as it was saved, with the port actually used.
    :param foreground_command: The server command the caller still has to run itself,
        set only when ``foreground`` was asked for. Blocking the terminal and handling
        Ctrl+C belong to the front end, so :func:`start` prepares that command instead
        of running it.
    :param pending_client: True when the learner's client still has to be opened,
        which is the case for a foreground start: the client can only connect once the
        front end has actually started the server, so :func:`open_client_when_up` does
        it afterwards instead.
    :param foreground_env: The environment the foreground server command needs, or None
        to inherit this process's. The front end runs that command itself, so it needs
        the same environment the detached path gets.
    """

    state: WorldState
    foreground_command: list[str] | None = None
    pending_client: bool = False
    foreground_env: dict[str, str] | None = None


#: Reported for a world that exists on disk - its directory and ``world.mt`` are
#: there - but has no runtime state at all: it was never started, so there is no port
#: and no pids to report, unlike ``"stopped"`` which implies a server that once ran and
#: has since exited. Keeping this distinct from ``"stopped"`` is what lets a front end
#: tell the two apart without guessing, and stops it from inventing a port for a world
#: that has never had one.
NEVER_STARTED = "never started"


@dataclass(frozen=True)
class WorldStatus:
    """
    What one world is doing right now, as ``miney status`` shows it.

    :param name: The world name.
    :param gameid: The game this world uses, read from its own ``world.mt``.
    :param state: The world's recorded runtime state - port and pids - or None for a
        world that exists on disk but has never been started, and therefore has no
        runtime state to report at all. Do not fake one up: a made-up port or pid in a
        status display is worse than an absent one.
    :param server: ``"running"`` when the server accepts connections, ``"starting"``
        while its process is alive but has not bound its port yet, ``"stopped"`` when
        it was running before and is not now, or :data:`NEVER_STARTED` when the world
        has no runtime state at all. The middle one matters: a world that is
        generating its map for the first time is neither up nor down for minutes at a
        time.
    :param client: ``"running"`` or ``"stopped"``, from the recorded client process, or
        None when there is no runtime state to report a client from.
    """

    name: str
    gameid: str
    state: WorldState | None
    server: str
    client: str | None


@dataclass(frozen=True)
class EnvironmentStatus:
    """
    Everything :func:`describe` found, ready to be printed.

    :param root: The ``.miney`` directory this describes.
    :param install: The Luanti that would be used, or None if none was found.
    :param worlds: One entry per world found on disk, in name order - whether it has
        ever been started or not.
    :param upstream: The current Luanti release, or None if the lookup failed or was
        skipped. Never a reason to fail - it only ever adds a line to the output.
    """

    root: Path
    install: LuantiInstall | None
    worlds: list[WorldStatus]
    upstream: upstream.Release | None = None


def _say(report: Reporter | None, message: str, warning: bool = False) -> None:
    """
    Hand one progress message to the caller, if it wants any.

    :param report: The caller's reporter, or None.
    :param message: The message.
    :param warning: Whether this is a warning.
    """
    logger.debug(message)
    if report is not None:
        report(Progress(message=message, warning=warning))


def find_environment(start: Path | None = None) -> EnvPaths | None:
    """
    Locate the project's ``.miney`` directory without creating anything.

    :param start: Directory to search from. Defaults to the current directory.
    :return: The environment, or None when this project has none.
    """
    return find_env(start)


def create_environment(start: Path | None = None) -> EnvPaths:
    """
    The project's ``.miney`` directory, created if it does not exist yet.

    Separate from :func:`find_environment` so that callers who need an environment get
    one back rather than "an environment or None": ``miney init`` and ``miney start``
    would otherwise have to narrow the type by hand, which is how an ``assert`` ends up
    in production code.

    :param start: Directory to create in, if nothing was found. Defaults to the current
        directory.
    :return: The environment, always.
    :raises MineyRunError: If the directory could not be created.
    """
    found = find_env(start)
    if found is not None:
        return found
    root = (start or Path.cwd()) / ENV_DIR_NAME
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MineyRunError(
            f"Could not create {root}: {error}\n"
            "Change into a directory you can write to and try again: uv run miney init"
        ) from error
    return EnvPaths(root=root)


def missing_world_message(
    paths: EnvPaths, world: str, requested_game: str, when_exists: str
) -> str:
    """
    Compose a message for a world that is not currently up, with a command that works.

    Reads the world's own recorded game id from ``world.mt`` rather than trusting the
    caller's game, so a beginner who copies the suggested command back does not walk
    into a second, confusing failure: :func:`ensure_world` refusing a game id that does
    not match what the world was actually created with.

    :param paths: The environment.
    :param world: World name.
    :param requested_game: The game asked for in this invocation. Used only when the
        world was never created at all and so has no game id of its own to read.
    :param when_exists: Clause describing the problem when the world exists but is
        idle, e.g. ``"was never started"`` or ``"has no log yet"``.
    :return: A message stating the problem and a command that will actually work.
    """
    gameid = read_world_gameid(paths.world_dir(world))
    if gameid is None:
        game_part = f" --game {requested_game}" if requested_game != DEFAULT_GAME else ""
        return (
            f"World '{world}' does not exist yet. "
            f"Create it with: uv run miney init --world {world}{game_part}"
        )
    game_part = f" --game {gameid}" if gameid != DEFAULT_GAME else ""
    return (
        f"World '{world}' {when_exists}. "
        f"Start it with: uv run miney start --world {world}{game_part}"
    )


def is_server_up(state: WorldState) -> bool:
    """
    Whether a world's server is ready to be connected to.

    This is the only definition of "up" in Miney, deliberately: the command line and
    :class:`~miney.luanti.Luanti` once had one each, they disagreed about a server that
    had a process but was not yet answering, and connecting to that server failed with
    an unrelated timeout.

    "Answering" is a protocol probe, not a bind test. Verified against Luanti 5.16.1: a
    running server leaves its UDP port bindable - it sets ``SO_REUSEADDR``, and on
    Windows its IPv6 wildcard bind does not reserve the IPv4 port at all - so a bind
    test reports a live server's port as free and every first ``miney start`` would time
    out waiting for a server that was in fact already up. Sending the handshake and
    waiting for the reply is the one signal that works on every platform.

    :param state: The world's recorded state.
    :return: True if the recorded server process is alive *and* answers the handshake.
    """
    return is_pid_alive(state.server_pid) and probe_server(SERVER_HOST, state.port)


def server_status(state: WorldState) -> str:
    """
    The three states a world's server can be in, for reporting.

    :param state: The world's recorded state.
    :return: ``"running"`` when it answers, ``"starting"`` while its process is alive
        but has not bound its port, ``"stopped"`` otherwise.
    """
    if is_server_up(state):
        return "running"
    if is_pid_alive(state.server_pid):
        return "starting"
    return "stopped"


def _worlds_without_state(paths: EnvPaths, known: set[str]) -> dict[str, str]:
    """
    Worlds that exist on disk but are not among the names already known from state.

    A world's existence does not depend on runtime state at all: ``miney init`` writes
    ``world.mt`` and never touches ``run/``, so a world that was created but never
    started has a directory and no state file. Reading ``worlds_dir`` directly is how
    :func:`describe` sees that world anyway, instead of reporting only the ones
    ``miney start`` has touched.

    :param paths: The environment.
    :param known: Names already accounted for, so they are not listed twice.
    :return: Game id by world name, for every other directory under ``worlds_dir``
        whose ``world.mt`` could actually be read. A subdirectory with no readable
        ``world.mt`` - for instance one left behind by a half-finished
        :func:`remove` - is not a world and is silently left out, never a crash.
    """
    if not paths.worlds_dir.is_dir():
        return {}
    try:
        entries = sorted(paths.worlds_dir.iterdir())
    except OSError:
        return {}
    found: dict[str, str] = {}
    for entry in entries:
        if entry.name in known or not entry.is_dir():
            continue
        gameid = read_world_gameid(entry)
        if gameid is not None:
            found[entry.name] = gameid
    return found


def describe(paths: EnvPaths, check_upstream: bool = True) -> EnvironmentStatus:
    """
    Everything ``miney status`` shows, gathered in one place.

    Read-only by contract, and the reason ``status`` has no business calling anything
    else: a front end must not have to know which steps in here have side effects. This
    one has none that reach outside the environment itself - it asks
    :func:`~miney.env.discover.discover` rather than :func:`find_luanti`, so a missing
    Luanti is something to report instead of something to raise about or, in Stage 2, to
    go and download; and it reads ``world.mt`` rather than creating or downloading
    anything for a world it has not seen state for yet. The one exception is the
    upstream version lookup: it is cached for a day and never fatal, but it can make a
    network request the very first time it runs, which is why ``check_upstream`` exists
    to turn it off.

    :param paths: The environment to look at.
    :param check_upstream: Whether to look up the current Luanti release. Cached for a
        day, and a failed lookup is silently ignored.
    :return: The install, and one :class:`WorldStatus` per world found on disk, whether
        or not it has ever been started.
    """
    states = {state.name: state for state in list_states(paths)}
    worlds = [
        WorldStatus(
            name=state.name,
            gameid=state.gameid,
            state=state,
            server=server_status(state),
            client="running" if is_pid_alive(state.client_pid) else "stopped",
        )
        for state in states.values()
    ]
    worlds.extend(
        WorldStatus(name=name, gameid=gameid, state=None, server=NEVER_STARTED, client=None)
        for name, gameid in _worlds_without_state(paths, set(states)).items()
    )
    worlds.sort(key=lambda world: world.name)
    return EnvironmentStatus(
        root=paths.root,
        install=discover(paths),
        worlds=worlds,
        upstream=upstream.latest_release(paths) if check_upstream else None,
    )


def wait_until_up(
    paths: EnvPaths,
    state: WorldState,
    *,
    timeout: float = DEFAULT_READY_TIMEOUT,
    interval: float = READY_POLL_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    report: Reporter | None = None,
) -> None:
    """
    Wait until a freshly started server accepts connections.

    Without this, connecting right after starting a server is a race a cold start
    loses: loading the game, compiling mods and generating a new map take far longer
    than the client's handshake timeout, and the beginner sees a connection error
    instead of "it is still starting".

    :param paths: The environment, used to name the log file in error messages.
    :param state: The world's state. Its ``server_pid`` must be the server we started.
    :param timeout: Seconds to wait before giving up.
    :param interval: Seconds between two checks.
    :param sleep: Substitutable sleep, so tests never really wait.
    :param clock: Substitutable monotonic clock, paired with ``sleep``.
    :param report: Where to send the "this can take a while" notice.
    :raises MineyRunError: If the server stopped while starting, or is still not up
        when the timeout expires. Both messages name the world and its log file.
    """
    deadline = clock() + timeout
    announced = False
    while True:
        if is_server_up(state):
            return
        if not is_pid_alive(state.server_pid):
            raise MineyRunError(
                f"The Luanti server for world '{state.name}' stopped while starting up.\n"
                f"Its log says why: {paths.log_file(state.name)}\n"
                f"Read the end of it with: uv run miney logs --world {state.name}"
            )
        if clock() >= deadline:
            raise MineyRunError(
                f"The Luanti server for world '{state.name}' did not finish starting "
                f"within {timeout:g} seconds.\n"
                f"Its log shows what it is busy with: {paths.log_file(state.name)}\n"
                f"Read the end of it with: uv run miney logs --world {state.name}"
            )
        if not announced:
            _say(
                report,
                f"Waiting up to {timeout:g} seconds for the Luanti server for "
                f"'{state.name}' to finish starting. The first start of a world "
                "generates the map and can take a while.",
            )
            announced = True
        sleep(interval)


def find_luanti(
    paths: EnvPaths, report: Reporter | None = None, *, check_upstream: bool = True
) -> LuantiInstall:
    """
    The Luanti to use for this environment, downloading one if there is none.

    On Windows and macOS a missing Luanti is fetched into ``paths.luanti_dir``. On
    Linux there is no official release asset and installing Luanti is one
    package-manager command, so the user is told which one - Miney never runs a
    privileged command.

    :param paths: The environment.
    :param report: Where to send progress.
    :param check_upstream: Whether to look up and report a newer release. A foreground
        ``start`` calls this twice in one run - once from :func:`start` itself, again
        from :func:`open_client_when_up` once the server is up - and the notice must
        only be printed once, so the second call passes ``False``.
    :return: The install to launch.
    :raises MineyRunError: If no Luanti could be found or downloaded.
    """
    install = discover(paths)
    if install is not None:
        if check_upstream:
            release = upstream.latest_release(paths)
            if release is not None and release.version > install.version:
                _say(report, f"A newer Luanti is available: {release.tag}")
        return install

    release = upstream.latest_release(paths)
    if not acquire.can_acquire():
        outdated = outdated_version(paths)
        if outdated is not None:
            found = ".".join(str(part) for part in outdated)
            required = ".".join(str(part) for part in MIN_VERSION)
            raise MineyRunError(
                f"Found Luanti {found}, but the Miney mod needs at least {required}.\n"
                "Please upgrade the Luanti you already have, for example:\n"
                "\n"
                "  flatpak install flathub org.luanti.luanti   # always current\n"
                "  sudo apt install luanti     # Debian, Ubuntu (your package manager)\n"
                "\n"
                "Then run this again:\n"
                "  uv run miney start"
            )
        raise MineyRunError(acquire.install_instructions(release))

    tag = release.tag if release is not None else "the current version"
    _say(report, f"No Luanti found. Downloading {tag} into {paths.luanti_dir}...")
    _acquire_and_rediscover(paths, release)

    install = _discover_after_acquire(paths)
    if install is None:
        raise MineyRunError(
            f"Luanti was downloaded into {paths.luanti_dir}, but it could not be "
            "started afterwards.\n"
            "Delete that directory and try again, or install Luanti yourself from "
            "https://www.luanti.org/downloads/"
        )
    _say(report, f"Luanti {'.'.join(str(p) for p in install.version)} is ready.")
    return install


def _acquire_and_rediscover(paths: EnvPaths, release: upstream.Release | None) -> Path:
    """
    Download Luanti into the environment.

    A named seam so tests can replace the download without stubbing the network.

    :param paths: The environment.
    :param release: The release to install, or None if the lookup failed.
    :return: The directory Luanti was unpacked into.
    :raises MineyRunError: If the download or extraction failed.
    """
    return acquire.acquire_luanti(paths, release)


def _discover_after_acquire(paths: EnvPaths) -> LuantiInstall | None:
    """
    Look for Luanti again once one has been downloaded.

    :param paths: The environment.
    :return: The install, or None if the freshly downloaded one does not run.
    """
    return discover(paths)


def ensure_game(
    paths: EnvPaths,
    gameid: str,
    report: Reporter | None = None,
    search: list[Path] | None = None,
) -> None:
    """
    Make sure a game is installed somewhere Luanti will find it.

    Luanti ships with no game at all, so this is what stands between a fresh download
    and a world that cannot be created. A game the Luanti installation already carries
    is left alone rather than downloaded a second time.

    :param paths: The environment.
    :param gameid: The game id, which is also its directory name.
    :param report: Where to send progress.
    :param search: Extra directories that may already hold games. Defaults to none.
    :raises MineyRunError: If the game is unknown to Miney, or the download failed.
    """
    for directory in [paths.games_dir, *(search or [])]:
        if (directory / gameid / "game.conf").is_file():
            return

    label = contentdb.game_label(gameid)
    _say(report, f"Downloading {label} from ContentDB...")
    contentdb.install_game(gameid, paths.games_dir)
    _say(report, f"{label} installed.")


def _preload_games(
    paths: EnvPaths, *, exclude: str, report: Reporter | None = None
) -> None:
    """
    Install the games Miney keeps ready, best-effort.

    The world's own game is already ensured by the caller and must succeed; these extras
    only make ``--game`` instant later, so a failure to fetch one is reported and shrugged
    off rather than allowed to stop a start. ``exclude`` skips the game just ensured, so
    it is not looked at twice.

    :param paths: The environment.
    :param exclude: A game id already handled, skipped here.
    :param report: Where to send progress.
    """
    for gameid in PRELOAD_GAMES:
        if gameid == exclude:
            continue
        try:
            ensure_game(paths, gameid, report=report)
        except MineyRunError as error:
            _say(
                report,
                f"Could not preinstall {contentdb.game_label(gameid)}: {error}\n"
                f"It is optional - {contentdb.game_label(exclude)} is ready. Miney will "
                "try again next time.",
                warning=True,
            )


def mod_source() -> Path | None:
    """
    Where to copy the Miney mod from.

    The mod ships as package data inside Miney rather than being downloaded, so that a
    pip-installed Miney has it, no first start needs the network, and the Lua half can
    never be a different version from the Python half that talks to it.

    :return: The mod directory, or None if the package data is missing.
    """
    candidate = Path(__file__).resolve().parent.parent / "mod_data" / "miney"
    return candidate if (candidate / "mod.conf").is_file() else None


def _refresh_mod(paths: EnvPaths, world: str, report: Reporter | None = None) -> None:
    """
    Put the Miney mod into a world, but only when that changes anything.

    Copying on every start was wrong twice over: it threw away a mod directory that a
    running server had open, and it did so even when the installed copy was already
    identical. So the copy happens only when the contents actually differ, and never
    while the world's own server is running - that world gets told to restart instead.
    A copy that does happen is reported, because it replaces ``worldmods/miney`` whole
    and nobody should have to guess that their changes in there are gone.

    :param paths: The environment.
    :param world: World name.
    :param report: Where to send warnings.
    :raises MineyRunError: If the mod cannot be found at all, or cannot be copied.
    """
    world_dir = paths.world_dir(world)
    target = world_dir / "worldmods" / "miney"
    source = mod_source()

    if source is None:
        if (target / "mod.conf").is_file():
            _say(
                report,
                f"Could not find the Miney mod to refresh for '{world}'; "
                "using the version already installed there instead.",
                warning=True,
            )
            return
        raise MineyRunError(
            "Could not find the Miney mod that ships inside this Miney install.\n"
            "That normally means the install is incomplete. Reinstalling Miney gets it "
            "back:\n"
            "  uv pip install --force-reinstall miney\n"
            "Or fetch the mod yourself and copy it into the world by hand:\n"
            "  ContentDB: https://content.luanti.org/packages/Miney/miney/\n"
            "  Source:    https://github.com/miney-py/miney (the 'miney/mod_data/miney' "
            "directory)\n"
            f"and copy it into {target}."
        )

    if mod_fingerprint(target) == mod_fingerprint(source):
        return

    state = load_state(paths.state_file(world))
    if state is not None and is_pid_alive(state.server_pid):
        _say(
            report,
            f"The Miney mod for world '{world}' is newer than the copy in the "
            "world, but that world's server is running, so it was left alone.\n"
            "Restart the world to pick up the new mod:\n"
            f"  uv run miney stop --world {world}\n"
            f"  uv run miney start --world {world}",
            warning=True,
        )
        return

    replaced = (target / "mod.conf").is_file()
    try:
        install_mod(world_dir, source)
        _say(
            report,
            f"{'Refreshed' if replaced else 'Installed'} the Miney mod "
            f"in world '{world}'.",
        )
    except OSError as error:
        raise MineyRunError(
            f"Could not install the Miney mod into world '{world}': {error}\n"
            "If Luanti is running against this world, stop it first: "
            f"uv run miney stop --world {world}\n"
            f"Then try again: uv run miney init --world {world}"
        ) from error


def ensure_world(
    paths: EnvPaths, world: str, game: str, *, report: Reporter | None = None
) -> LuantiInstall:
    """
    Make sure a world exists and is complete: Luanti, files, configuration and the mod.

    Downloading a missing Luanti belongs here, not in ``start``: it is part of
    completing the environment, so ``miney init`` sets it up in full and a later
    ``miney start`` finds nothing left to fetch. Safe to call again on a world that is
    already there; that is what every ``miney start`` does. A missing game is fetched
    from ContentDB here too.

    :param paths: The environment.
    :param world: World name.
    :param game: The game a *new* world is created with.
    :param report: Where to send progress.
    :return: The Luanti install to launch this world with.
    :raises MineyRunError: If Luanti could not be found or downloaded, the world was
        created with a different game, or the Miney mod could not be installed.
    """
    world_dir = paths.world_dir(world)
    existing = read_world_gameid(world_dir)
    if existing is not None and existing != game:
        raise MineyRunError(
            f"World '{world}' was created with game '{existing}', not '{game}'.\n"
            f"A world's game cannot be changed. Use a separate world instead:\n"
            f"  uv run miney start --world <newname> --game {game}"
        )
    # Luanti before the game: ensure_game() installs a downloaded game under
    # paths.games_dir, which lives inside paths.luanti_dir (see EnvPaths.games_dir), and
    # acquire_luanti() replaces paths.luanti_dir wholesale - shutil.rmtree() then a
    # rename() over it - so a game installed before a fresh Luanti download would be
    # deleted the moment that download lands. Nothing here talks to a real Luanti or a
    # real ContentDB, so no automated test downloads both in sequence; the order is
    # pinned by test_ensure_world_finds_luanti_before_the_game instead.
    install = find_luanti(paths, report=report)
    ensure_game(paths, game, report=report)
    _preload_games(paths, exclude=game, report=report)
    if existing is None:
        write_world_mt(world_dir, game)
    write_config(paths.config_file)
    ensure_client_password(paths.client_pw)
    _refresh_mod(paths, world, report=report)

    _say(report, f"Environment ready in {paths.root}.")
    _say(report, f"World '{world}' uses {contentdb.game_label(game)}.")
    return install


def resolve_port(
    paths: EnvPaths, world: str, requested: int | None, state: WorldState | None
) -> int:
    """
    Decide which port a world should use.

    A world keeps the port it was given. A new one never reuses a port already recorded
    by another world in the same environment, so several worlds can run side by side.

    :param paths: The environment.
    :param world: World name.
    :param requested: An explicitly asked-for port, or None.
    :param state: The world's recorded state, or None if it has none yet.
    :return: The port to use.
    :raises MineyRunError: If an explicitly requested port is held by something other
        than this world's own server, or if no free port could be found at all.
    """
    if requested is not None:
        held_by_us = (
            state is not None
            and state.port == requested
            and is_pid_alive(state.server_pid)
        )
        if not held_by_us and not is_port_free(requested):
            raise MineyRunError(
                f"Port {requested} is already in use by something else.\n"
                f"Choose another one with: uv run miney start --port {requested + 1}"
            )
        return requested
    if state is not None:
        return state.port

    taken = {other.port for other in list_states(paths) if other.name != world}
    port = DEFAULT_PORT
    while True:
        try:
            candidate = find_free_port(port)
        except OSError as error:
            raise MineyRunError(str(error)) from error
        if candidate not in taken:
            return candidate
        port = candidate + 1


def _spawn(
    command: list[str], cwd: Path, what: str, env: dict[str, str] | None = None
) -> int:
    """
    Start a detached process, turning a failed launch into a readable error.

    :param command: The command to run.
    :param cwd: Working directory for the child.
    :param what: What is being started, for the error message.
    :param env: Complete environment for the child, or None to inherit this process's.
    :return: The child's process id.
    :raises MineyRunError: If the process could not be started at all.
    """
    try:
        return spawn_detached(command, cwd, env)
    except OSError as error:
        raise MineyRunError(
            f"Could not start {what}: {error}\n"
            f"The command was: {' '.join(command)}\n"
            "Check that Luanti is still installed where Miney found it, then try "
            "again: uv run miney start"
        ) from error


def open_client(
    paths: EnvPaths,
    install: LuantiInstall,
    state: WorldState,
    *,
    report: Reporter | None = None,
) -> None:
    """
    Open the learner's Luanti window against a world, unless one is already open.

    A client that will not start is a warning and not a failure, as the design's error
    table requires: the server is up, so the learner's script runs either way - there is
    just nobody watching it. Failing here instead used to abort :func:`start` before it
    had written the server's pid anywhere, leaving that server running and invisible.

    :param paths: The environment.
    :param install: The Luanti to launch.
    :param state: The world's state. ``client_pid`` is updated in place on success.
    :param report: Where to send progress and the warning.
    """
    if is_pid_alive(state.client_pid):
        _say(report, "Your client is already running.")
        return
    player = current_player_name()
    try:
        state.client_pid = _spawn(
            client_command(install, paths, state.port, player),
            paths.root,
            "your Luanti client",
        )
    except MineyRunError as error:
        _say(
            report,
            f"{error}\n"
            f"The server for '{state.name}' is running, so your scripts still work - "
            "you just have no Luanti window watching them.",
            warning=True,
        )
        return
    _say(report, f"Opened your client as '{player}'.")


def record_foreground_server(paths: EnvPaths, world: str, pid: int) -> WorldState:
    """
    Record the process id of a server the front end is running in its own terminal.

    ``miney start --foreground`` runs the server itself, so :func:`start` has no pid to
    write. Leaving the field empty made the rest of Miney believe the world was down:
    ``miney status`` said stopped, :class:`~miney.luanti.Luanti` autostart started a
    second server on the same port, :func:`ensure_world` would have replaced
    ``worldmods/miney`` under the live one, and ``miney remove --yes`` deleted a world
    that was open. A foreground server is a server; it belongs in the state file like
    any other.

    :param paths: The environment.
    :param world: World name.
    :param pid: Process id of the server the front end just started.
    :return: The world's state, with the pid recorded and saved.
    :raises MineyRunError: If the world has no recorded state to write the pid into.
    """
    state = load_state(paths.state_file(world))
    if state is None:
        raise MineyRunError(
            f"World '{world}' has no recorded state, so the running server's process "
            f"id cannot be stored and nothing else would see it.\n"
            f"Start it again: uv run miney start --world {world}"
        )
    state.server_pid = pid
    save_state(paths.state_file(world), state)
    return state


def clear_foreground_server(paths: EnvPaths, world: str, pid: int) -> None:
    """
    Forget a foreground server's process id once that process has ended.

    Meant to be called from a ``finally``, so that Ctrl+C or a crash cannot leave a dead
    pid on disk for the next ``miney status`` to report as a running world.

    Two situations are deliberately no-ops rather than errors, because in both the
    recorded fact is still true and clearing it would destroy it: the world's state is
    gone (``miney remove`` ran while the server was up), or it records a different pid
    (another start took the world over in the meantime).

    :param paths: The environment.
    :param world: World name.
    :param pid: The pid that was recorded by :func:`record_foreground_server`.
    """
    state = load_state(paths.state_file(world))
    if state is None or state.server_pid != pid:
        logger.debug("Not clearing the server pid of '%s': it is not %s", world, pid)
        return
    state.server_pid = None
    save_state(paths.state_file(world), state)


def open_client_when_up(
    paths: EnvPaths,
    world: str,
    *,
    report: Reporter | None = None,
    ready_timeout: float = DEFAULT_READY_TIMEOUT,
    interval: float = READY_POLL_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """
    Wait for a world's server to answer, then open the learner's client against it.

    This is the foreground half of :func:`start`. There the server process is started by
    the front end, so the client cannot be spawned inside :func:`start` at all - it would
    be pointed at a server that does not exist yet, and a ``--go`` client that cannot
    connect gives up and drops the learner at the main menu.

    Nothing in here is fatal. The server is running in the user's own terminal with its
    output in front of them, so a client that will not open is reported as a warning and
    the terminal keeps doing its job.

    :param paths: The environment.
    :param world: World name.
    :param report: Where to send progress and warnings.
    :param ready_timeout: Seconds to wait for the server to accept connections.
    :param interval: Seconds between two readiness checks.
    :param sleep: Substitutable sleep, so tests never really wait.
    :param clock: Substitutable monotonic clock, paired with ``sleep``.
    """
    state = load_state(paths.state_file(world))
    if state is None:
        _say(
            report,
            f"World '{world}' has no recorded state, so no client was opened for it.\n"
            f"Open one yourself once the server is up: uv run miney start "
            f"--world {world} --no-client",
            warning=True,
        )
        return
    try:
        wait_until_up(
            paths,
            state,
            timeout=ready_timeout,
            interval=interval,
            sleep=sleep,
            clock=clock,
            report=report,
        )
        install = find_luanti(paths, report=report, check_upstream=False)
        open_client(paths, install, state, report=report)
    except MineyRunError as error:
        _say(report, str(error), warning=True)
        return

    # Read-modify-write, not a save of the snapshot loaded before the wait: the wait is
    # up to 120 seconds wide, and anything another process wrote to state.json during
    # it - a "miney stop" clearing server_pid, another start taking the world over -
    # would otherwise be silently overwritten with the stale values this call started
    # with. Only the field this call actually owns, client_pid, is carried across.
    fresh = load_state(paths.state_file(world))
    if fresh is None:
        return
    fresh.client_pid = state.client_pid
    save_state(paths.state_file(world), fresh)


def start(
    paths: EnvPaths,
    world: str,
    game: str,
    *,
    port: int | None = None,
    with_client: bool = True,
    foreground: bool = False,
    report: Reporter | None = None,
    ready_timeout: float = DEFAULT_READY_TIMEOUT,
    ready_interval: float = READY_POLL_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> StartResult:
    """
    Bring a world up: create what is missing, start what is not running, wait for it.

    Calling this on a world that is already running does nothing but confirm it, so it
    is safe to call before every connection.

    :param paths: The environment.
    :param world: World name.
    :param game: The game a *new* world is created with.
    :param port: An explicitly asked-for port. Defaults to the world's own port, or a
        free one for a new world.
    :param with_client: Also open the learner's Luanti window. With ``foreground`` this
        only sets :attr:`StartResult.pending_client`; the front end opens it through
        :func:`open_client_when_up` once its server process is up.
    :param foreground: Do not spawn a detached server; return its command in
        :attr:`StartResult.foreground_command` for the caller to run instead.
    :param report: Where to send progress.
    :param ready_timeout: Seconds to wait for the server to accept connections.
    :param ready_interval: Seconds between two readiness checks.
    :param sleep: Substitutable sleep, so tests never really wait.
    :param clock: Substitutable monotonic clock, paired with ``sleep``.
    :return: What was started, including the world's saved state.
    :raises MineyRunError: If the world, Luanti, the port or the processes could not be
        made ready. Every message names a command that gets the user further.
    """
    # ensure_world() completes the environment - downloading a missing Luanti first,
    # then a missing game - and hands back the install to launch.
    install = ensure_world(paths, world, game, report=report)

    state = load_state(paths.state_file(world))
    chosen = resolve_port(paths, world, port, state)
    if state is None:
        state = WorldState(name=world, gameid=game, port=chosen)
    state.port = chosen

    if foreground and is_pid_alive(state.server_pid):
        game_part = f" --game {state.gameid}" if state.gameid != DEFAULT_GAME else ""
        raise MineyRunError(
            f"Luanti server for '{world}' is already running on port {chosen} "
            f"(pid {state.server_pid}); a foreground copy would fight it for the port "
            f"and the world's save file.\n"
            f"Stop it first: uv run miney stop --world {world}{game_part}\n"
            f"Then run again: uv run miney start --world {world}{game_part} --foreground"
        )

    paths.log_file(world).parent.mkdir(parents=True, exist_ok=True)

    if foreground:
        # The terminal itself hosts the server for this run, so its pid only exists once
        # the front end has started it; record_foreground_server writes it then. The
        # state is saved here anyway, so that there is a file to write it into.
        state.server_pid = None
        save_state(paths.state_file(world), state)
        return StartResult(
            state=state,
            foreground_command=server_command(install, paths, world, chosen),
            pending_client=with_client,
            foreground_env=game_env(paths),
        )

    if not is_pid_alive(state.server_pid):
        state.server_pid = _spawn(
            server_command(install, paths, world, chosen),
            paths.root,
            f"the Luanti server for '{world}'",
            env=game_env(paths),
        )
        _say(report, f"Started Luanti server for '{world}' on port {chosen}.")
    else:
        _say(report, f"Luanti server for '{world}' is already running on port {chosen}.")

    # Saved before anything else can go wrong. A server whose pid is not on disk is
    # invisible to "miney status", unreachable by "miney stop", and fights the next
    # start for its own port.
    save_state(paths.state_file(world), state)

    # The client is spawned after this, not before: a --go client whose server is not
    # accepting connections yet times out its handshake, and a cold start outlasts that
    # handshake by minutes.
    wait_until_up(
        paths,
        state,
        timeout=ready_timeout,
        interval=ready_interval,
        sleep=sleep,
        clock=clock,
        report=report,
    )

    if with_client:
        open_client(paths, install, state, report=report)
        # Read-modify-write, not a save of the snapshot loaded before the wait above:
        # see the identical comment in open_client_when_up for why. Only client_pid,
        # the field this branch owns, is carried across; everything else comes fresh
        # from disk.
        fresh = load_state(paths.state_file(world))
        if fresh is not None:
            fresh.client_pid = state.client_pid
            save_state(paths.state_file(world), fresh)
            state = fresh
    return StartResult(state=state)


def stop(
    paths: EnvPaths,
    world: str,
    game: str = DEFAULT_GAME,
    *,
    server: bool = True,
    client: bool = True,
    report: Reporter | None = None,
) -> WorldState:
    """
    Stop a world's server, its client, or both.

    :param paths: The environment.
    :param world: World name.
    :param game: The game asked for, used only to suggest a working command when the
        world turns out not to exist.
    :param server: Stop the server.
    :param client: Stop the learner's client.
    :param report: Where to send progress.
    :return: The world's state with the stopped pids cleared.
    :raises MineyRunError: If the world has no recorded state at all.
    """
    state = load_state(paths.state_file(world))
    if state is None:
        raise MineyRunError(missing_world_message(paths, world, game, "was never started"))

    stopped_anything = False
    if server and stop_pid(state.server_pid):
        _say(report, f"Stopped the server for '{world}'.")
        stopped_anything = True
    if client and stop_pid(state.client_pid):
        _say(report, "Closed your client.")
        stopped_anything = True

    if not stopped_anything:
        if not server:
            _say(report, f"Nothing to stop for '{world}': the client is not running.")
        elif not client:
            _say(report, f"Nothing to stop for '{world}': the server is not running.")
        else:
            _say(
                report,
                f"Nothing to stop for '{world}': the server and client are not running.",
            )

    if server:
        state.server_pid = None
    if client:
        state.client_pid = None
    save_state(paths.state_file(world), state)
    return state


def removal_target(paths: EnvPaths, world: str | None) -> Path:
    """
    What :func:`remove` would delete.

    :param paths: The environment.
    :param world: World name, or None for the whole environment.
    :return: The directory that would go away, for a confirmation prompt.
    """
    return paths.world_dir(world) if world else paths.root


def remove(
    paths: EnvPaths, world: str | None, *, report: Reporter | None = None
) -> Path:
    """
    Delete a world, or the whole environment.

    Anything still running for the affected world(s) is stopped first. Deleting a
    world's state file out from under a running server would otherwise leave it
    orphaned: still running, but invisible to ``miney status`` and unreachable by
    ``miney stop``.

    :param paths: The environment.
    :param world: World name, or None for the whole environment.
    :param report: Where to send progress.
    :return: The directory that was deleted.
    """
    affected: list[WorldState]
    if world:
        state = load_state(paths.state_file(world))
        affected = [state] if state is not None else []
    else:
        affected = list_states(paths)

    for state in affected:
        if stop_pid(state.server_pid):
            _say(report, f"Stopped the server for '{state.name}'.")
        if stop_pid(state.client_pid):
            _say(report, f"Closed the client for '{state.name}'.")

    target = removal_target(paths, world)
    existed = target.exists()
    shutil.rmtree(target, ignore_errors=True)
    if world:
        shutil.rmtree(paths.world_run_dir(world), ignore_errors=True)
    if existed:
        _say(report, f"Removed {target}")
    else:
        _say(report, f"'{target}' did not exist; nothing to remove there.")
    return target
