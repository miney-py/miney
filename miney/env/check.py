"""
Answering one question: can Python drive this Luanti right now?

The check is a chain, deliberately, and it is read from the bottom up. Miney, then
Luanti, then the world, the mod, the server, the connection, the privilege and finally
the world's content - each step only makes sense once the one below it holds. A single
"it does not work" tells a beginner nothing; a chain tells them *which* layer is
broken, which is the whole reason this exists as a command instead of a paragraph in
the docs.

Two rules keep it honest:

* **Nothing here repairs anything on its own.** Every step that Miney *could* fix
  carries a :class:`Remedy` describing the fix and naming the command the user would
  type themselves. Whether that fix runs is the front end's decision, after it has
  asked. So a step reads with :func:`~miney.env.discover.discover` rather than
  :func:`~miney.env.manage.find_luanti`, which would quietly download a Luanti.
* **Nothing here prints**, the same way :mod:`~miney.env.manage` does not. Both the
  command line and a script get the same :class:`CheckReport` back and decide what to
  do with it.

The chain stops at the first step that makes the rest meaningless: with no Luanti
there is nothing to say about the server, and with a stopped server there is nothing
to connect to. Steps that only ever warn - an outdated mod, a missing privilege, a
sparse world - never stop it, because none of them keeps a learner from writing code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import __version__
from ..exceptions import LuaError, LuaResultTimeout, MineyRunError
from ..luanticlient.exceptions import (
    LuantiConnectionError,
    LuantiPermissionError,
    LuantiTimeoutError,
)
from . import manage
from .discover import LuantiInstall, discover as discover_luanti
from .paths import EnvPaths
from .state import load_state
from .world import read_world_gameid

logger = logging.getLogger(__name__)

#: A step that holds.
OK = "ok"

#: A step that is not what it should be, but does not stop anyone from writing code.
WARNING = "warning"

#: A step that has to be fixed before the next one can even be tried.
FAILED = "failed"

#: The privilege the Miney mod gates code execution behind, for clients that are not
#: on a local address (see ``mod_data/miney/init.lua``).
MINEY_PRIVILEGE = "miney"

#: Below this many registered node types, a world is not carrying a real game. Ten is
#: low enough that no working game trips it and high enough to catch a game that failed
#: to load, which reports a handful of engine built-ins and nothing else.
MINIMUM_NODES = 10

#: "Give me a connected Luanti for this world." Substitutable so no test needs a server.
Connector = Callable[[str], Any]

#: Everything connecting and then asking the mod a question can fail with. Listed rather
#: than caught as a bare ``Exception`` on purpose: these are the failures a broken setup
#: produces and that the report is meant to explain, while anything else is a bug in
#: Miney and has to surface as one instead of being dressed up as "your server said no".
#: Miney's exceptions share no common base class, so the tuple is spelled out.
CONNECTION_ERRORS = (
    MineyRunError,
    LuantiConnectionError,
    LuantiPermissionError,
    LuantiTimeoutError,
    LuaError,
    LuaResultTimeout,
)


@dataclass(frozen=True)
class Remedy:
    """
    A repair Miney can carry out, and the command that does the same thing by hand.

    Both halves matter. ``command`` is what the front end shows before it asks, so the
    learner finds out how to fix this themselves next time; ``apply`` is the convenience
    that saves them retyping it. A problem Miney cannot fix has no Remedy at all rather
    than one that fails - see the privilege step for why that case is real.

    :param what: The repair in a few words, as part of a question: "Shall I ... for you?"
    :param command: The equivalent command, exactly as the user would type it.
    :param apply: Performs the repair. Takes a reporter, like everything in
        :mod:`~miney.env.manage`, and raises
        :class:`~miney.exceptions.MineyRunError` if it fails.
    """

    what: str
    command: str
    apply: Callable[[manage.Reporter | None], None]


@dataclass(frozen=True)
class CheckStep:
    """
    One layer of the setup, and what was found there.

    :param name: Short label, e.g. ``"Luanti"``. Also how a front end recognises a step.
    :param state: :data:`OK`, :data:`WARNING` or :data:`FAILED`.
    :param detail: What was found, ready to print after the name.
    :param hint: What to do about it, for a step nothing can be offered for.
    :param remedy: The repair Miney could carry out, or None.
    """

    name: str
    state: str
    detail: str
    hint: str = ""
    remedy: Remedy | None = None

    @property
    def failed(self) -> bool:
        """Whether this step stopped the chain."""
        return self.state == FAILED


@dataclass(frozen=True)
class CheckReport:
    """
    Everything :func:`run_checks` found, in the order it looked.

    :param steps: One entry per layer reached. Shorter than the full chain when a step
        failed, because the layers above a broken one were never inspected.
    """

    steps: list[CheckStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no step failed. Warnings do not make a setup broken."""
        return not any(step.failed for step in self.steps)

    @property
    def failure(self) -> CheckStep | None:
        """The step that stopped the chain, or None if nothing did."""
        for step in self.steps:
            if step.failed:
                return step
        return None


def _connect(world: str) -> Any:
    """
    Open a connection exactly the way a learner's own script does.

    Same defaults as a bare ``miney.Luanti()`` - including ``invisible``, which is what
    everybody gets - so this proves the thing that is about to happen rather than a
    tidier version of it. ``autostart`` is the one exception: a check must never bring
    a server up behind the user's back, and the caller has already established that the
    server answers.

    Imported here rather than at module level because :mod:`miney.luanti` imports
    :mod:`~miney.env.manage`, so a module-level import would close a cycle.

    :param world: The world in the local environment to connect to.
    :return: The connected :class:`~miney.luanti.Luanti`, usable as a context manager.
    """
    from ..luanti import Luanti

    return Luanti(world=world, autostart=False)


def _server_state(paths: EnvPaths, world: str) -> tuple[bool, int | None]:
    """
    Whether a world's server answers, and on which port.

    :param paths: The environment.
    :param world: World name.
    :return: Whether it is up, and the port it was recorded with - the port is worth
        reporting even when the server is down, because it is what ``miney start``
        would use.
    """
    state = load_state(paths.state_file(world))
    if state is None:
        return False, None
    return manage.is_server_up(state), state.port


def _world_command(world: str, game: str) -> str:
    """
    The ``miney init`` invocation that creates one particular world.

    :param world: World name.
    :param game: The game it should use.
    :return: The command, with ``--game`` left off when it would name the default.
    """
    game_part = f" --game {game}" if game != manage.DEFAULT_GAME else ""
    return f"uv run miney init --world {world}{game_part}"


def _miney_step() -> CheckStep:
    """
    The bottom of the chain: which Miney is running this.

    Never fails - Miney is plainly installed, or nothing would be running - but it opens
    the report with the version number, which is the first thing anybody needs when a
    beginner pastes their output into an issue.

    :return: The step.
    """
    import platform

    return CheckStep(
        name="Miney",
        state=OK,
        detail=f"{__version__} on Python {platform.python_version()}",
    )


def _luanti_step(paths: EnvPaths, install: LuantiInstall | None) -> CheckStep:
    """
    Whether there is a Luanti to run at all.

    :param paths: The environment.
    :param install: What discovery found, or None.
    :return: The step, carrying an offer to download one when there is none.
    """
    if install is not None:
        version = ".".join(str(part) for part in install.version)
        return CheckStep(name="Luanti", state=OK, detail=f"{version} ({install.source})")

    return CheckStep(
        name="Luanti",
        state=FAILED,
        detail="not found",
        hint="Miney downloads Luanti into your home folder; nothing needs root.",
        remedy=Remedy(
            what="download Luanti",
            command="uv run miney init",
            apply=lambda report: manage.find_luanti(paths, report=report),
        ),
    )


def _world_step(paths: EnvPaths, world: str, game: str) -> CheckStep:
    """
    Whether the world exists on disk.

    :param paths: The environment.
    :param world: World name.
    :param game: The game a missing world would be created with.
    :return: The step, carrying an offer to create the world when it is not there.
    """
    existing = read_world_gameid(paths.world_dir(world))
    if existing is not None:
        return CheckStep(
            name="World",
            state=OK,
            detail=f"'{world}' ({manage.contentdb.game_label(existing)})",
        )

    return CheckStep(
        name="World",
        state=FAILED,
        detail=f"'{world}' does not exist yet",
        remedy=Remedy(
            what=f"create the world '{world}'",
            command=_world_command(world, game),
            apply=lambda report: manage.ensure_world(paths, world, game, report=report),
        ),
    )


def _mod_step(paths: EnvPaths, world: str, game: str, running: bool) -> CheckStep:
    """
    Whether the world carries the Miney mod, and the same version this Miney ships.

    A mod that is merely out of date is a warning: the world still answers, it just
    answers with an older mod, and telling a beginner that their working setup is broken
    would send them fixing the wrong thing. Refreshing it under a running server is
    refused by :func:`~miney.env.manage.ensure_world`, so the offer stops and restarts
    that server itself rather than handing back an error.

    :param paths: The environment.
    :param world: World name.
    :param game: The world's game.
    :param running: Whether this world's server is up, which decides what the fix has
        to do.
    :return: The step.
    """
    installed = paths.world_dir(world) / "worldmods" / "miney"
    source = manage.mod_source()

    def refresh(report: manage.Reporter | None) -> None:
        if running:
            manage.stop(paths, world, game, client=False, report=report)
        manage.ensure_world(paths, world, game, report=report)
        if running:
            manage.start(paths, world, game, with_client=False, report=report)

    restart_note = (
        "uv run miney stop && uv run miney start" if running else _world_command(world, game)
    )

    if not (installed / "mod.conf").is_file():
        return CheckStep(
            name="Miney mod",
            state=FAILED,
            detail="not installed in this world",
            hint="Without it the server has nothing for Python to talk to.",
            remedy=Remedy(
                what="install the Miney mod into this world",
                command=restart_note,
                apply=refresh,
            ),
        )

    if source is not None and manage.mod_fingerprint(installed) != manage.mod_fingerprint(source):
        return CheckStep(
            name="Miney mod",
            state=WARNING,
            detail="installed, but older than the one this Miney ships",
            hint="It still works; refreshing it keeps both halves in step.",
            remedy=Remedy(
                what="refresh the Miney mod in this world",
                command=restart_note,
                apply=refresh,
            ),
        )

    return CheckStep(name="Miney mod", state=OK, detail="installed and up to date")


def _server_step(
    paths: EnvPaths, world: str, game: str, up: bool, port: int | None
) -> CheckStep:
    """
    Whether the world's server answers.

    :param paths: The environment.
    :param world: World name.
    :param game: The world's game.
    :param up: Whether it answers.
    :param port: The recorded port, if there is one.
    :return: The step, carrying an offer to start the server when it is down.
    """
    if up:
        return CheckStep(name="Server", state=OK, detail=f"running on port {port}")

    return CheckStep(
        name="Server",
        state=FAILED,
        detail="not running",
        remedy=Remedy(
            what="start the server",
            command="uv run miney start --no-client",
            apply=lambda report: manage.start(
                paths, world, game, with_client=False, report=report
            ),
        ),
    )


def _privilege_step(connection: Any) -> CheckStep:
    """
    Whether the Miney player holds the ``miney`` privilege.

    Only ever a warning, and that is not a softened failure: ``mod_data/miney/init.lua``
    lets a client on a local address execute code without the privilege, which is every
    world ``miney start`` creates. It matters on a server reached over the network - and
    there Miney cannot grant it either, because granting runs through the very code
    execution the privilege gates. So this step explains and names ``/grant``, and
    carries no offer.

    :param connection: The connected Luanti.
    :return: The step.
    """
    name = getattr(connection, "playername", MINEY_PRIVILEGE)
    for player in connection.players:
        if player.name != name:
            continue
        if MINEY_PRIVILEGE in player.privileges:
            return CheckStep(
                name="Privilege",
                state=OK,
                detail=f"'{name}' has the '{MINEY_PRIVILEGE}' privilege",
            )
        break

    return CheckStep(
        name="Privilege",
        state=WARNING,
        detail=f"'{name}' does not have the '{MINEY_PRIVILEGE}' privilege",
        hint=(
            "Not needed here - the Miney mod lets a client on this machine run code "
            "without it. On a Luanti server somewhere else it is required, and only "
            f"that server can grant it: /grant {name} {MINEY_PRIVILEGE}"
        ),
    )


def _content_step(connection: Any) -> CheckStep:
    """
    Whether the world actually has a game loaded, seen through Miney's own eyes.

    Counting nodes and tools reads the game's content the same way a learner's
    autocomplete does, so a number here means ``lt.nodes.names.default.dirt`` will work.

    :param connection: The connected Luanti.
    :return: The step.
    """
    nodes = len(list(connection.nodes.names))
    tools = len(list(connection.tool))
    detail = f"{nodes} node types, {tools} tool types"

    if nodes < MINIMUM_NODES or tools == 0:
        return CheckStep(
            name="Content",
            state=WARNING,
            detail=detail,
            hint=(
                "That is fewer than a loaded game has. The server log says what went "
                "wrong: uv run miney logs"
            ),
        )
    return CheckStep(name="Content", state=OK, detail=detail)


def run_checks(
    paths: EnvPaths,
    world: str,
    game: str,
    *,
    discover: Callable[[EnvPaths], LuantiInstall | None] | None = None,
    server_up: Callable[[EnvPaths, str], tuple[bool, int | None]] | None = None,
    connect: Connector | None = None,
) -> CheckReport:
    """
    Walk the chain and report what holds.

    Never raises for a broken setup - that is what the report is for. Only a genuine bug
    escapes.

    :param paths: The environment to check.
    :param world: The world to check.
    :param game: The game a missing world would be created with, used for the repair
        commands.
    :param discover: Substitutable "find a Luanti" step, for testing.
    :param server_up: Substitutable "is this world's server answering" step, for testing.
    :param connect: Substitutable "connect to this world" step, for testing.
    :return: What every reached step found.
    """
    find = discover or discover_luanti
    ask_server = server_up or _server_state
    open_connection = connect or _connect

    steps = [_miney_step()]

    install = find(paths)
    steps.append(_luanti_step(paths, install))
    if steps[-1].failed:
        return CheckReport(steps)

    steps.append(_world_step(paths, world, game))
    if steps[-1].failed:
        return CheckReport(steps)

    up, port = ask_server(paths, world)
    steps.append(_mod_step(paths, world, game, up))
    if steps[-1].failed:
        return CheckReport(steps)

    steps.append(_server_step(paths, world, game, up, port))
    if steps[-1].failed:
        return CheckReport(steps)

    try:
        with open_connection(world) as connection:
            steps.append(
                CheckStep(
                    name="Connection",
                    state=OK,
                    detail=f"talking to Luanti {connection.version}",
                )
            )
            steps.append(_privilege_step(connection))
            steps.append(_content_step(connection))
    except CONNECTION_ERRORS as error:
        # Every Miney-level failure, from a refused handshake to a mod that is installed
        # but not enabled, arrives here. There is nothing to offer: no command Miney can
        # run turns a server that rejects it into one that does not.
        logger.debug("The check could not connect: %s", error)
        steps.append(
            CheckStep(
                name="Connection",
                state=FAILED,
                detail=str(error),
                hint=(
                    "Usually one of: the Miney mod is installed but not enabled for "
                    "this world, another client is already connected under this name, "
                    "or the server is still starting up."
                ),
            )
        )

    return CheckReport(steps)
