"""
Starting the Luanti server and the learner's client, noticing that they are already
running, and stopping them.

Both processes are detached on purpose: a script that finishes must not tear down the
world the learner is looking at, and the next script run should find them still up.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

from .discover import LuantiInstall
from .paths import EnvPaths

logger = logging.getLogger(__name__)

#: Port used unless another one is asked for.
DEFAULT_PORT = 30000


def server_command(
    install: LuantiInstall, paths: EnvPaths, world: str, port: int
) -> list[str]:
    """
    Build the command that runs a dedicated server.

    ``--server`` runs one from the ordinary client binary, which is required because the
    Windows release contains no separate server executable.

    :param install: The Luanti to launch, providing the command prefix.
    :param paths: The environment.
    :param world: World name.
    :param port: UDP port to listen on.
    :return: The full command.
    """
    return [
        *install.launch,
        "--server",
        "--world",
        str(paths.world_dir(world)),
        "--config",
        str(paths.config_file),
        "--port",
        str(port),
        "--logfile",
        str(paths.log_file(world)),
    ]


def client_command(
    install: LuantiInstall, paths: EnvPaths, port: int, player: str
) -> list[str]:
    """
    Build the command that starts the learner's client, already connected.

    ``--password-file`` is used rather than ``--password`` because an argument is visible
    in the process list to every other user on the machine.

    :param install: The Luanti to launch.
    :param paths: The environment.
    :param port: Port of the server to join.
    :param player: Player name to connect as.
    :return: The full command.
    """
    return [
        *install.launch,
        "--go",
        "--address",
        "127.0.0.1",
        "--port",
        str(port),
        "--name",
        player,
        "--password-file",
        str(paths.client_pw),
    ]


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """
    Whether a UDP port can be bound.

    :param port: Port to test.
    :param host: Interface to test on.
    :return: True if nothing holds the port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(start: int = DEFAULT_PORT, attempts: int = 20) -> int:
    """
    First free port at or above a starting point.

    :param start: Port to start looking at.
    :param attempts: How many consecutive ports to try.
    :return: A free port.
    :raises OSError: If every candidate was taken. The message names the range tried and
        suggests passing --port explicitly.
    """
    for port in range(start, start + attempts):
        if is_port_free(port):
            return port
    raise OSError(
        f"No free port between {start} and {start + attempts - 1}. "
        f"Choose one yourself with: uv run miney start --port <number>"
    )


def is_pid_alive(pid: int | None) -> bool:
    """
    Whether a process id belongs to a running process.

    :param pid: The process id, or None.
    :return: True if the process exists.
    """
    if not pid or pid < 1:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


#: Every name Luanti has used for "where else to look for games". 5.16.1 accepts all
#: three; the oldest is kept because Miney supports back to 5.7, which predates the
#: rename, and three strings cost nothing.
GAME_PATH_VARS = (
    "LUANTI_GAME_PATH",
    "MINETEST_GAME_PATH",
    "MINETEST_SUBGAME_PATH",
)


def game_env(paths: EnvPaths) -> dict[str, str] | None:
    """
    The environment a server needs to find games that Miney installed.

    Verified against Luanti 5.16.1: a server whose ``world.mt`` names a game that does
    not live inside the Luanti installation exits with status 1 and
    ``Game [] could not be found``, unless one of these variables points at the
    directory holding it. That is the normal case on Linux, where Luanti is installed
    system-wide and our games are in ``.miney``.

    :param paths: The environment.
    :return: A complete environment for the child, or None when Miney has installed no
        games and the child should simply inherit ours.
    """
    if not paths.games_dir.is_dir():
        return None
    env = dict(os.environ)
    for name in GAME_PATH_VARS:
        env[name] = str(paths.games_dir)
    return env


def spawn_detached(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> int:
    """
    Start a process that outlives this one.

    :param command: The command to run.
    :param cwd: Working directory for the child.
    :param env: Complete environment for the child, or None to inherit this process's.
        None rather than an empty dict: an empty environment breaks a Luanti server in
        ways no log message explains.
    :return: The child's process id.
    """
    cwd.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    logger.debug("Spawning detached: %s", command)
    return subprocess.Popen(command, **kwargs).pid


def stop_pid(pid: int | None) -> bool:
    """
    Ask a process to stop.

    :param pid: The process id, or None.
    :return: True if a stop was attempted, False if there was nothing to stop.
    """
    if pid is None or not is_pid_alive(pid):
        return False
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False,
                       capture_output=True)
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True
