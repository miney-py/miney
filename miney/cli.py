"""
The ``miney`` command: manage the project-local Luanti environment.

This is a front end and nothing else. It parses arguments, calls
:mod:`miney.env.manage`, prints what comes back and turns a
:class:`~miney.exceptions.MineyRunError` into a message plus an exit code. Every
decision about what should happen lives in ``manage``, so that the library can take
the same route without going through argparse.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import traceback

from . import __version__
from .env import check, manage, pypi, upgrade
from .env.contentdb import default_world_name, game_label
from .env.logs import follow, read_tail
from .env.paths import ENV_DIR_NAME, syncing_service
from .env.process import is_pid_alive
from .env.state import list_states
from .env.world import DEFAULT_GAME
from .exceptions import MineyRunError

logger = logging.getLogger(__name__)

#: Environment variable that brings the traceback of an unexpected error back. It is a
#: variable rather than a flag on purpose: every subcommand would have to carry the
#: flag, and it would then sit in the ``--help`` that a beginner reads.
DEBUG_ENV_VAR = "MINEY_DEBUG"

#: Exit code for an interrupted run: 128 plus SIGINT, which is what a shell expects.
INTERRUPTED_EXIT_CODE = 130

#: Seconds to give a foreground server to exit on its own after Ctrl+C, before this
#: front end stops tracking it. A clean Luanti shutdown flushes the world's sqlite
#: database and can be mid-mapgen when the interrupt lands, which takes seconds, not
#: the 0.25 s grace CPython's own Popen.wait already gives a child once wait() is
#: actually running; this covers the much wider window before that call - the up to
#: 120 s readiness wait - where Ctrl+C would otherwise clear the recorded server pid
#: while the process is still shutting down.
FOREGROUND_INTERRUPT_GRACE_SECONDS = 10.0


def _report(progress: manage.Progress) -> None:
    """
    Print one progress message from ``manage``.

    :param progress: What happened. Warnings go to stderr, everything else to stdout.
    """
    print(progress.message, file=sys.stderr if progress.warning else sys.stdout)


def _fail(message: str) -> int:
    """
    Report an error and return a non-zero exit code.

    :param message: What went wrong and what to do about it.
    """
    print(message, file=sys.stderr)
    return 1


#: The games the first-run menu offers, in the order shown, each with the one-line
#: reason a beginner would pick it. The shown name comes from ``game_label`` so it stays
#: in one place; kept here rather than in ``manage`` because it is front-end wording, and
#: only the command line ever asks a human this question.
_GAME_CHOICES: list[tuple[str, str]] = [
    (
        "minetest_game",
        "the calm building sandbox. No monsters or hunger - just you and the blocks. "
        "Every example in the Miney docs uses its block names (default:dirt, "
        "default:stone, ...).",
    ),
    (
        "mineclone2",
        "a Minecraft-like world with mobs, hunger and crafting. More to explore, but its "
        "block names differ, so the doc examples will not match one-to-one.",
    ),
]


def _stdin_is_mintty() -> bool:
    """
    Whether standard input is a MinTTY terminal on Windows (Git Bash, MSYS2, Cygwin).

    Python's ``isatty()`` reports False for these because MinTTY connects a program
    through a named pipe rather than a Windows console, so a beginner running Miney from
    Git Bash would silently miss the game prompt. This recognises the terminal by that
    pipe's name - ``\\msys-...-ptyN-...`` or ``\\cygwin-...-ptyN-...`` - the same way
    terminal libraries do. A no-op off Windows, and returns False on any error rather
    than risk a wrong "interactive" that would block on input.

    :return: True only when stdin is a MinTTY pseudo-terminal pipe.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class _FileNameInfo(ctypes.Structure):
            _fields_ = [("FileNameLength", wintypes.DWORD),
                        ("FileName", ctypes.c_wchar * 260)]

        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        info = _FileNameInfo()
        file_name_info_class = 2  # FileNameInfo in FILE_INFO_BY_HANDLE_CLASS
        ok = ctypes.windll.kernel32.GetFileInformationByHandleEx(
            handle, file_name_info_class, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            return False
        name = info.FileName[: info.FileNameLength // 2]
        return ("-pty" in name) and ("msys-" in name or "cygwin-" in name)
    except Exception:
        return False


def _stdin_is_interactive() -> bool:
    """
    Whether there is a human at the keyboard to answer a prompt.

    False when input is piped, redirected or absent - in a script, in CI, or under the
    bootstrap one-liner's non-interactive shell - so those paths fall back to the default
    game instead of blocking on a question no one will answer. A Windows console reports
    itself through ``isatty()``; Git Bash and other MinTTY terminals do not, so they are
    recognised separately.

    :return: True when standard input is a terminal a person can type into.
    """
    if sys.stdin is None:
        return False
    try:
        if sys.stdin.isatty():
            return True
    except (ValueError, OSError):
        return False
    return _stdin_is_mintty()


def _prompt_for_game() -> str:
    """
    Ask which game a beginner's first world should use.

    A newcomer who has never opened Luanti does not know that the default world has no
    mobs, and is disappointed when nothing moves. The menu makes the choice - and its one
    real trade-off, mobs versus doc-matching block names - explicit up front.

    :return: The chosen game id. Enter with no input picks the first, documented game.
    """
    print("\nWhich game should your world use?\n")
    for number, (gameid, blurb) in enumerate(_GAME_CHOICES, start=1):
        print(f"  {number}) {game_label(gameid)} - {blurb}\n")

    by_number = {str(i): gameid for i, (gameid, _b) in enumerate(_GAME_CHOICES, start=1)}
    by_name = {gameid: gameid for gameid, _b in _GAME_CHOICES}
    default_game = _GAME_CHOICES[0][0]
    while True:
        try:
            answer = input(f"Enter 1 or 2 [{1}]: ").strip().lower()
        except EOFError:
            return default_game
        if answer == "":
            return default_game
        chosen = by_number.get(answer) or by_name.get(answer)
        if chosen is not None:
            return chosen
        print("Please type 1 or 2.")


def _worlds_on_disk(paths: manage.EnvPaths) -> list[tuple[str, str]]:
    """
    The worlds that already exist in this project, with the game each one uses.

    Read from ``world.mt`` on disk, not from runtime state, so a world created by
    ``miney init`` and never started still counts.

    :param paths: The environment.
    :return: ``(world name, game id)`` pairs, sorted by name.
    """
    worlds_dir = paths.worlds_dir
    if not worlds_dir.is_dir():
        return []
    found = []
    for child in sorted(worlds_dir.iterdir()):
        gameid = manage.read_world_gameid(child)
        if gameid is not None:
            found.append((child.name, gameid))
    return found


def _resolve_world_and_game(
    paths: manage.EnvPaths, args: argparse.Namespace
) -> tuple[str, str]:
    """
    Decide which world to act on and which game it uses.

    The world's name is not tied to the game: picking VoxeLibre at the prompt must not
    mean a bare ``miney start`` afterwards silently opens a different, minetest_game
    world. So with no ``--world`` given, an existing single world is reused as-is - name
    and its own game - and only a genuinely empty project falls through to creating one.

    A game is chosen (in order): an explicit ``--game``; the game a named or lone existing
    world already has; the prompt, when a human is creating the first world; otherwise the
    documented default. A newly created world with no ``--world`` is named after its game
    (:func:`~miney.env.contentdb.default_world_name`), so a VoxeLibre world is called
    ``VoxeLibre`` rather than ``mineclone2``.

    :param paths: The environment.
    :param args: Parsed arguments; ``game`` is None unless ``--game`` was given.
    :return: The world name and the game id to use for it.
    """
    if args.world is not None:
        existing = manage.read_world_gameid(paths.world_dir(args.world))
        if existing is not None:
            return args.world, (args.game or existing)
        if args.game is not None:
            return args.world, args.game
        game = _prompt_for_game() if _stdin_is_interactive() else DEFAULT_GAME
        return args.world, game

    worlds = _worlds_on_disk(paths)
    if args.game is None and len(worlds) == 1:
        # The one world already here, reused with its own game.
        return worlds[0]

    if args.game is None and len(worlds) > 1:
        # Several worlds and no hint: the one that is up is the one being worked in, and
        # starting it again only opens a window onto it; with none up, the one worked in
        # last. Reaching for the default-named world instead *creates a new world* beside
        # the ones already here - a first start, a full map generation, a long wait, and
        # a world nobody asked for. The game comes from the world itself rather than from
        # its recorded state, because only world.mt decides what a world is.
        by_name = dict(worlds)
        chosen = manage.pick_world(paths) or manage.last_used_world(paths)
        if chosen is not None and chosen.name in by_name:
            return chosen.name, by_name[chosen.name]

    if args.game is not None:
        game = args.game
    elif not worlds and _stdin_is_interactive():
        game = _prompt_for_game()
    else:
        game = DEFAULT_GAME
    return default_world_name(game), game


def _world_to_act_on(paths: manage.EnvPaths, args: argparse.Namespace) -> str:
    """
    The world a command that acts on an existing one (stop, logs) should target.

    Same rule as everywhere else - :func:`~miney.env.manage.pick_world` - so ``miney
    stop`` after ``miney start`` stops what was started, whatever game it uses and
    however many other worlds sit next to it on disk. Without an answer, the
    game-derived default name is kept so the command's own "does not exist" message
    still fires.

    :param paths: The environment.
    :param args: Parsed arguments.
    :return: The world name to act on.
    """
    if args.world is not None:
        return args.world
    chosen = manage.pick_world(paths)
    if chosen is not None:
        return chosen.name
    worlds = _worlds_on_disk(paths)
    if len(worlds) == 1:
        return worlds[0][0]
    return default_world_name(args.game) if args.game else args.game


def cmd_init(args: argparse.Namespace) -> int:
    """
    Create or complete the environment.

    :param args: Parsed arguments with ``world`` and ``game``.
    :return: Process exit code.
    """
    paths = manage.create_environment()
    service = syncing_service(paths.root)
    if service is not None:
        _report(
            manage.Progress(
                message=(
                    f"Warning: {paths.root} is inside a folder synced by {service}.\n"
                    "The server writes its world databases continuously, and a sync "
                    "client copying them mid-write kills the server thread. Run "
                    "'uv run miney init' in a directory that is not synced."
                ),
                warning=True,
            )
        )
    world, game = _resolve_world_and_game(paths, args)
    manage.ensure_world(paths, world, game, report=_report)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """
    Start the server, and the learner's client unless asked not to.

    With ``--foreground`` the server runs in this terminal rather than detached, so this
    is the process that owns it: it records the server's pid so the rest of Miney can
    see the world is up, opens the client once the server answers, and clears the pid
    again however the run ends.

    :param args: Parsed arguments.
    :return: Process exit code.
    """
    paths = manage.create_environment()
    world, game = _resolve_world_and_game(paths, args)

    result = manage.start(
        paths,
        world,
        game,
        port=args.port,
        with_client=not args.no_client,
        foreground=args.foreground,
        report=_report,
    )
    print(f"Log: {paths.log_file(world)}")

    if result.foreground_command is None:
        # A bare "miney stop" targets the lone world, so only name it when this project
        # has more than one world to disambiguate between.
        world_part = f" --world {world}" if len(_worlds_on_disk(paths)) > 1 else ""
        if args.no_client:
            print("The server is running in the background.")
        else:
            print(
                "Your world is open. The server keeps running in the background, so "
                "closing the game window does not stop it."
            )
        print(f"Stop it when you are done: uv run miney stop{world_part}")
        return 0

    print("Running in the foreground. Press Ctrl+C to stop the server.")
    # Popen rather than run: run discards the pid, and a server nobody can name is one
    # that "miney status" calls stopped and that autostart starts a second copy of.
    try:
        process = subprocess.Popen(
            result.foreground_command, cwd=str(paths.root), env=result.foreground_env
        )
    except OSError as error:
        raise MineyRunError(
            f"Could not start the Luanti server for '{world}' in this terminal: "
            f"{error}\n"
            f"The command was: {' '.join(result.foreground_command)}\n"
            "Check that Luanti is still installed where Miney found it, then try "
            "again: uv run miney start"
        ) from error
    interrupted = False
    exit_code = 0
    try:
        manage.record_foreground_server(paths, world, process.pid)
        if result.pending_client:
            manage.open_client_when_up(paths, world, report=_report)
        exit_code = process.wait()
    except KeyboardInterrupt:
        # Ctrl+C can land anywhere above, including inside the up-to-120-second
        # readiness wait -- well before process.wait() itself is even called. Give the
        # server the same chance to finish it would have gotten from wait() directly,
        # instead of clearing its pid while it may still be shutting down.
        interrupted = True
        try:
            process.wait(timeout=FOREGROUND_INTERRUPT_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            pass
    finally:
        manage.clear_foreground_server(paths, world, process.pid)
    # A non-zero exit is only a failure when the child chose it; a Ctrl+C makes the
    # child exit non-zero too (it was just killed by the signal), and that is success.
    if not interrupted and exit_code != 0:
        return 1
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """
    Stop the server, the client, or both.

    :param args: Parsed arguments.
    :return: Process exit code.
    """
    paths = manage.find_environment()
    if paths is None:
        print(
            f"No {ENV_DIR_NAME} directory here, so nothing is running. "
            "Start a world first with: uv run miney start"
        )
        return 0

    # Without --world and without an answer from pick_world, stopping "the" world would
    # aim at a name nobody started - the user watches nothing happen and reaches for the
    # task manager. Say what is there instead.
    if args.world is None and manage.pick_world(paths) is None and len(list_states(paths)) > 1:
        running = [one for one in list_states(paths)
                   if manage.server_status(one) != "stopped"]
        if not running:
            print("No server is running. The worlds in this project:")
            print(manage.describe_worlds(paths))
            return 0
        print("Several worlds are running. Say which one to stop:")
        print(manage.describe_worlds(paths))
        for one in running:
            print(f"    uv run miney stop --world {one.name}")
        return 1

    manage.stop(
        paths,
        _world_to_act_on(paths, args),
        args.game,
        server=not args.client_only,
        client=not args.server_only,
        report=_report,
    )
    return 0


def _render_version(version: tuple[int, int, int]) -> str:
    """
    A version tuple as a user reads it.

    :param version: ``(major, minor, patch)``.
    :return: The dotted form.
    """
    return ".".join(str(part) for part in version)


def _newer_miney() -> tuple[int, int, int] | None:
    """
    The Miney release on PyPI, when it is newer than the one running.

    :return: The available version, or None when it is not newer, not readable, or
        PyPI could not be reached. Never raises, so no version check can break a
        command.
    """
    installed = pypi.parse_version(__version__)
    available = pypi.latest_version()
    if installed is None or available is None or available <= installed:
        return None
    return available


def _print_miney_version() -> None:
    """
    Print the running Miney version, and the newer one if there is any.

    Same shape as the Luanti lines below it in ``status``: the fact first, the offer to
    do something about it indented underneath.
    """
    print(f"Miney: {__version__}")
    newer = _newer_miney()
    if newer is not None:
        print(
            f"  A newer Miney is available: {_render_version(newer)}. "
            "Get it with: uv run miney upgrade"
        )


def _mod_follow_up() -> str:
    """
    How the Lua mod reaches the worlds after the package was upgraded.

    The upgrade replaced files this very process is running from, so nothing can be
    copied into a world here - the mod that ships with the new package is refreshed by
    the next ``miney start``, which runs the new code. A world whose server is running
    needs a stop first, because :func:`manage._refresh_mod` deliberately leaves a
    running world alone.

    :return: The line to print after a successful upgrade.
    """
    paths = manage.find_environment()
    running = (
        [state.name for state in list_states(paths) if is_pid_alive(state.server_pid)]
        if paths is not None
        else []
    )
    if not running:
        return (
            "The Lua mod for your worlds comes along automatically the next time you "
            "run:\n  uv run miney start"
        )
    worlds = ", ".join(f"'{name}'" for name in running)
    return (
        f"The server for {worlds} is running, so the Lua mod in that world was left "
        "alone.\nRestart it to pick up the new mod:\n"
        "  uv run miney stop\n"
        "  uv run miney start"
    )


def _ask(question: str) -> bool:
    """
    Ask a yes-or-no question, defaulting to yes.

    :param question: The question, without the ``[Y/n]``.
    :return: True if the user agreed. False without a terminal to ask at.
    """
    if not _stdin_is_interactive():
        return False
    try:
        return input(f"{question} [Y/n]: ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


def _upgrade_luanti() -> int:
    """
    Offer to replace this project's Luanti with a newer release.

    Asked separately from the Miney upgrade, and asked second-guessing nothing: there
    are good reasons to stay on a Luanti that works, so a no here leaves it alone
    without further comment. Miney only ever replaces a Luanti it downloaded itself;
    :func:`~miney.env.manage.plan_luanti_upgrade` is what decides that.

    :return: 0 unless the upgrade itself failed.
    """
    paths = manage.find_environment()
    if paths is None:
        return 0

    upgrade_plan = manage.plan_luanti_upgrade(paths)
    installed = (
        _render_version(upgrade_plan.installed) if upgrade_plan.installed else "unknown"
    )
    if upgrade_plan.blocked is not None:
        print(f"\nLuanti: {installed}")
        print(upgrade_plan.blocked)
        return 0
    if upgrade_plan.release is None:
        print(f"\nLuanti: {installed} is the newest version. Nothing to do.")
        return 0

    print(f"\nLuanti: {installed} installed, {upgrade_plan.release.tag} available.")
    print(
        "I can download it and put it in place of the one you have. Your worlds are "
        "not in there and are not touched; the games, mods and settings inside the "
        "Luanti folder are carried over."
    )
    if not _ask("Shall I upgrade Luanti?"):
        print("Leaving Luanti as it is.")
        return 0

    manage.upgrade_luanti(paths, upgrade_plan.release, report=_report)
    return 0


def _upgrade_miney() -> int:
    """
    Offer to replace the installed Miney package with a newer one.

    Only the Python half is upgraded here, and the Lua mod needs no step of its own: it
    ships inside the package, so the next ``miney start`` copies the new one into the
    worlds by itself.

    Nothing is installed without a yes, and the command that does the same thing by
    hand is printed before the question - a learner should find out what Miney is about
    to do, not press a magic key. Without a terminal to ask at, only that command is
    printed, and the same happens where Miney cannot do the upgrade itself at all: on
    Windows without pip, where the running ``miney.exe`` is the file being replaced.

    :return: 0 unless the upgrade was refused or failed.
    """
    installed = pypi.parse_version(__version__)
    available = pypi.latest_version()
    if available is not None and installed is not None and available <= installed:
        print(f"Miney {__version__} is the newest version. Nothing to do.")
        return 0

    plan = upgrade.plan()
    if plan.refusal is not None:
        return _fail(plan.refusal)

    if available is None:
        print(
            f"Miney: {__version__} installed. Could not reach PyPI, so I do not know "
            "whether a newer version exists."
        )
    else:
        print(f"Miney: {__version__} installed, {_render_version(available)} available.")

    if plan.runnable:
        print("\nI can upgrade Miney for you. That is the same as running:")
    else:
        print("\nUpgrade Miney with:")
    print(f"  {plan.shown}")

    if plan.manual is not None:
        print(f"\n{plan.manual}")
        return 0
    if not _stdin_is_interactive():
        print("\nRun that command to upgrade.")
        return 0
    if not _ask("Shall I upgrade Miney?"):
        return 0

    upgrade.run(plan)
    print(f"\n{_mod_follow_up()}")
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    """
    Bring this project up to date: Luanti first, then Miney itself.

    Two questions, not one. There are good reasons to stay on a Luanti that works while
    still wanting the newest Miney, so neither answer decides the other.

    Luanti goes first because after the Miney upgrade this process is running code that
    is no longer installed - a fix to the Luanti download in that very release would not
    be the one that runs. A failed Luanti upgrade does not cancel the Miney one; it is
    reported and the command carries on, because the two have nothing to do with each
    other.

    :param args: Parsed arguments, unused.
    :return: 0 when nothing failed.
    """
    try:
        luanti = _upgrade_luanti()
    except MineyRunError as error:
        print(str(error), file=sys.stderr)
        luanti = 1
    print()
    return _upgrade_miney() or luanti


def cmd_status(args: argparse.Namespace) -> int:
    """
    Report what exists and what is running.

    Everything shown comes from :func:`manage.describe <miney.env.manage.describe>`,
    which is read-only: ``status`` is the one command that must never start, install or
    download anything, and routing it through ``manage`` is what guarantees that.

    :param args: Parsed arguments, unused.
    :return: Process exit code.
    """
    _print_miney_version()
    paths = manage.find_environment()
    if paths is None:
        print(f"No {ENV_DIR_NAME} directory found. Create one with: uv run miney start")
        return 0

    status = manage.describe(paths)
    if status.install is None:
        print(
            "Luanti: not found. Install it from https://www.luanti.org/downloads/ "
            "and run: uv run miney start"
        )
    else:
        version = ".".join(str(part) for part in status.install.version)
        print(f"Luanti: {version} ({status.install.source})")

    if (
        status.install is not None
        and status.upstream is not None
        and status.upstream.version > status.install.version
    ):
        print(f"  A newer Luanti is available: {status.upstream.tag}")

    if not status.worlds:
        print("No worlds yet. Create one with: uv run miney start")
        return 0

    for world in status.worlds:
        label = game_label(world.gameid)
        if world.state is not None:
            print(
                f"  {world.name}: game={label} "
                f"port={world.state.port} server={world.server} client={world.client}"
            )
        else:
            game_part = f" --game {world.gameid}" if world.gameid != DEFAULT_GAME else ""
            print(
                f"  {world.name}: game={label} server={world.server}. "
                f"Start it with: uv run miney start --world {world.name}{game_part}"
            )
    return 0


#: Markers for the three states a check step can be in, in the pretty and the plain
#: variant. The plain one is not a fallback nobody sees: redirecting the command's
#: output on Windows encodes with the locale code page, and a bare print of an emoji
#: raises UnicodeEncodeError there - a check that crashes when piped into a file is
#: worse than one that prints ASCII.
_MARKERS_UNICODE = {check.OK: "✅", check.WARNING: "⚠️ ", check.FAILED: "❌"}
_MARKERS_PLAIN = {check.OK: "[ ok ]", check.WARNING: "[warn]", check.FAILED: "[FAIL]"}


def _markers() -> dict[str, str]:
    """
    The state markers this terminal can actually print.

    :return: The unicode markers when standard output can encode them, plain ASCII
        otherwise.
    """
    try:
        "".join(_MARKERS_UNICODE.values()).encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError, AttributeError):
        return _MARKERS_PLAIN
    return _MARKERS_UNICODE


def _print_report(report: check.CheckReport) -> None:
    """
    Print one line per checked layer.

    :param report: What the checks found.
    """
    markers = _markers()
    width = max(len(step.name) for step in report.steps)
    for step in report.steps:
        print(f"{markers[step.state]} {step.name.ljust(width)}  {step.detail}")
        if step.state != check.OK and step.hint:
            print(f"     {step.hint}")


def _last_resort(paths: manage.EnvPaths) -> str:
    """
    The two ways to start over, for when nothing else worked.

    Ordered by what they cost. Deleting the shared Luanti loses nothing that cannot be
    downloaded again; deleting the environment loses every world the learner built in
    it, so it comes second and says so plainly. Neither is ever offered as a y/n - a
    command that can destroy a week of building has to be typed on purpose.

    :param paths: The environment, for the real paths to name.
    :return: A printable block.
    """
    if sys.platform == "win32":
        remove_luanti = f'Remove-Item -Recurse -Force "{paths.luanti_dir}"'
    else:
        remove_luanti = f'rm -rf "{paths.luanti_dir}"'
    return (
        "\nIf none of that helps, you can start over:\n"
        f"\n  {remove_luanti}\n"
        "      Deletes Luanti and its games. Both are downloaded again on the next\n"
        "      start, and none of your worlds are stored there.\n"
        "\n  uv run miney remove --yes\n"
        "      Deletes this project's .miney directory - including every world you\n"
        "      have built in it. There is no undo.\n"
    )


def _explain_failure(step: check.CheckStep, paths: manage.EnvPaths) -> None:
    """
    Say what is wrong and which command puts it right.

    Printed whenever a fix is not offered, is declined, or did not help - so a learner
    always leaves with the command in front of them rather than only with a refusal.

    :param step: The step that failed.
    :param paths: The environment, for the last-resort paths.
    """
    if step.remedy is not None:
        print(f"\nFix it with:\n  {step.remedy.command}")
    print(_last_resort(paths))


def _offer(step: check.CheckStep) -> bool:
    """
    Describe the repair, show the equivalent command, and ask whether to run it.

    The command is shown before the question on purpose: the point is that the learner
    finds out what Miney is about to do and how they would do it themselves, not that
    they press a magic key.

    :param step: The failing step, which must carry a remedy.
    :return: True if the user agreed.
    """
    remedy = step.remedy
    print(f"\nI can {remedy.what} for you. That is the same as running:")
    print(f"  {remedy.command}")
    try:
        answer = input(f"Shall I {remedy.what}? [Y/n]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def cmd_check(args: argparse.Namespace) -> int:
    """
    Verify that Python can drive Luanti, and offer to fix what stands in the way.

    Diagnosis first, repair only with a yes: every step that Miney could put right is
    described, shown as the command that does the same thing by hand, and then offered.
    Nothing is downloaded, created or started without that yes, which is why this reads
    with :func:`~miney.env.check.run_checks` rather than with ``ensure_world``.

    Each step gets one repair attempt. A step that still fails after its own fix ran
    ends the command with the command to run and the ways to start over, rather than
    asking the same question again.

    :param args: Parsed arguments.
    :return: 0 when nothing failed, 1 otherwise. Warnings do not fail the command.
    """
    paths = manage.find_environment()
    if paths is None:
        print(
            f"No {ENV_DIR_NAME} directory here, so there is nothing to check yet.\n"
            "Set one up with: uv run miney init"
        )
        return 1

    world = _world_to_act_on(paths, args)
    game = manage.read_world_gameid(paths.world_dir(world)) or args.game
    attempted: set[str] = set()

    while True:
        report = check.run_checks(paths, world, game)
        _print_report(report)

        failure = report.failure
        if failure is None:
            print("\nEverything is ready. Your Python scripts can drive this world.")
            return 0

        if (
            failure.remedy is None
            or failure.name in attempted
            or not _stdin_is_interactive()
        ):
            _explain_failure(failure, paths)
            return 1

        if not _offer(failure):
            _explain_failure(failure, paths)
            return 1

        attempted.add(failure.name)
        failure.remedy.apply(_report)
        print()


def cmd_logs(args: argparse.Namespace) -> int:
    """
    Print the tail of a world's server log, optionally following it.

    :param args: Parsed arguments.
    :return: Process exit code.
    """
    paths = manage.find_environment()
    if paths is None:
        print(
            f"No {ENV_DIR_NAME} directory here, so there is no log yet. "
            "Start a world with: uv run miney start"
        )
        return 0
    world = _world_to_act_on(paths, args)
    log = paths.log_file(world)
    if not log.is_file() and not args.follow:
        return _fail(manage.missing_world_message(paths, world, args.game, "has no log yet"))

    for line in read_tail(log, lines=args.lines):
        print(line)
    if args.follow:
        try:
            for line in follow(log):
                print(line, flush=True)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """
    Delete a world, or the whole environment.

    :param args: Parsed arguments.
    :return: Process exit code.
    """
    paths = manage.find_environment()
    if paths is None:
        print(
            f"No {ENV_DIR_NAME} directory here. Nothing to remove. "
            "Create one with: uv run miney init"
        )
        return 0

    target = manage.removal_target(paths, args.world)
    if not args.yes:
        return _fail(
            f"This would delete {target}, including anything built there.\n"
            f"Run it again with --yes if that is what you want."
        )

    manage.remove(paths, args.world, report=_report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """
    The argument parser for the ``miney`` command.

    :return: A parser whose namespace always carries ``world`` and ``game``.
    """
    parser = argparse.ArgumentParser(
        prog="miney", description="Manage the Luanti environment for this project."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(sub: argparse.ArgumentParser, *, game_default: str | None = DEFAULT_GAME) -> None:
        sub.add_argument("--world", help="World name. Defaults to the game id.")
        sub.add_argument(
            "--game",
            default=game_default,
            help=(
                "Game for a new world. VoxeLibre (mineclone2) uses different node "
                "names than the documentation examples."
            ),
        )

    # init and start create worlds, so they leave --game unset by default: with no game
    # named and no world yet, they ask the user which one to use. stop/status/logs only
    # identify an existing world, so their --game keeps defaulting to the documented game.
    init = subparsers.add_parser("init", help="Create or complete the environment.")
    common(init, game_default=None)
    init.set_defaults(func=cmd_init)

    start = subparsers.add_parser("start", help="Start the server and your client.")
    common(start, game_default=None)
    start.add_argument("--port", type=int, default=None, help="UDP port for the server.")
    start.add_argument("--no-client", action="store_true", help="Do not open a client.")
    start.add_argument(
        "-f",
        "--foreground",
        action="store_true",
        help=(
            "Run the server in this terminal instead of detaching it. Your client "
            "still opens, once the server answers. Ctrl+C stops the server."
        ),
    )
    start.set_defaults(func=cmd_start)

    stop = subparsers.add_parser("stop", help="Stop the server and your client.")
    common(stop)
    stop.add_argument("--client-only", action="store_true")
    stop.add_argument("--server-only", action="store_true")
    stop.set_defaults(func=cmd_stop)

    status = subparsers.add_parser("status", help="Show what exists and what is running.")
    common(status)
    status.set_defaults(func=cmd_status)

    check_parser = subparsers.add_parser(
        "check", help="Verify that Python can drive Luanti, and offer to fix what cannot."
    )
    common(check_parser)
    check_parser.set_defaults(func=cmd_check)

    # No --world/--game: the package is upgraded for the whole project, and the Lua mod
    # follows into every world on its own at the next start.
    upgrade_parser = subparsers.add_parser(
        "upgrade", help="Upgrade Miney to the newest version."
    )
    upgrade_parser.set_defaults(func=cmd_upgrade)

    logs = subparsers.add_parser("logs", help="Show the server log.")
    common(logs)
    logs.add_argument("-f", "--follow", action="store_true", help="Keep printing new lines.")
    logs.add_argument("-n", "--lines", type=int, default=200, help="How many lines to show.")
    logs.set_defaults(func=cmd_logs)

    remove = subparsers.add_parser("remove", help="Delete a world or the environment.")
    remove.add_argument("--world", help="Delete only this world.")
    remove.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    remove.set_defaults(func=cmd_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Entry point for the ``miney`` command.

    Nothing below this point is allowed to surface as a raw traceback: every reachable
    exception becomes a clean message on stderr and a non-zero exit code instead,
    because a beginner running this from a terminal has no use for a stack trace.

    :param argv: Arguments, defaulting to ``sys.argv[1:]``.
    :return: Process exit code.
    """
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except MineyRunError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # A BaseException, so the "except Exception" below never saw it - and "miney
        # start" can wait two minutes for a server, which is exactly where Ctrl+C
        # happens.
        print(
            "\nminey: stopped at your request.\n"
            "Whatever was already started keeps running, and a server that was still "
            "coming up may be up by now.\n"
            "  See it:   uv run miney status\n"
            "  Watch it: uv run miney logs -f\n"
            "  Stop it:  uv run miney stop",
            file=sys.stderr,
        )
        return INTERRUPTED_EXIT_CODE
    except Exception as error:
        logger.exception("The miney command failed with an unexpected error.")
        detail = str(error).strip()
        named = f"{type(error).__name__}: {detail}" if detail else type(error).__name__
        print(f"miney: unexpected error: {named}", file=sys.stderr)
        if os.environ.get(DEBUG_ENV_VAR):
            traceback.print_exc()
        else:
            print(
                f"That is a bug in Miney. Run the same command again with "
                f"{DEBUG_ENV_VAR}=1 to get the full traceback, then report it at "
                "https://github.com/miney-py/miney/issues",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
