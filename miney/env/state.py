"""
Per-world runtime state: which port a world runs on, and which processes serve it.

Stored as ``run/<world>/state.json`` so that a later script run, or a second terminal,
can find a world that is already running.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import EnvPaths

logger = logging.getLogger(__name__)


def _coerce_pid(value: object) -> int | None:
    """
    Read a recorded process id, tolerating a damaged one.

    :param value: The raw JSON value for ``server_pid`` or ``client_pid``.
    :return: The pid, or None if it is missing or not actually a number. Coercing
        instead of raising keeps a damaged field from invalidating the whole state:
        ``is_pid_alive`` later does ``pid < 1``, which raises ``TypeError`` for a
        string, so a bad pid must become "not running" rather than a crash.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class WorldState:
    """
    What is known about one world between runs.

    :param name: The world name, which is also its directory name.
    :param gameid: The game the world was created with. It cannot be changed afterwards.
    :param port: The UDP port the server listens on.
    :param server_pid: Process id of the server, or None if it was never started.
    :param client_pid: Process id of the learner's client, or None.
    """

    name: str
    gameid: str
    port: int
    server_pid: int | None = None
    client_pid: int | None = None


def save_state(path: Path, state: WorldState) -> None:
    """
    Write a world's state, creating parent directories as needed.

    :param path: Target ``state.json``.
    :param state: The state to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def load_state(path: Path) -> WorldState | None:
    """
    Read a world's state.

    A missing, unreadable or incomplete file yields None rather than an exception: state
    is a cache of what we last did, and a damaged one should make us re-detect, not fail.

    :param path: The ``state.json`` to read.
    :return: The state, or None if it could not be read.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return WorldState(
            name=raw["name"],
            gameid=raw["gameid"],
            port=int(raw["port"]),
            server_pid=_coerce_pid(raw.get("server_pid")),
            client_pid=_coerce_pid(raw.get("client_pid")),
        )
    except (KeyError, TypeError, ValueError):
        logger.debug("Ignoring malformed world state at %s", path)
        return None


def list_states(paths: EnvPaths) -> list[WorldState]:
    """
    Every world that has runtime state, in directory order.

    :param paths: The environment to look in.
    :return: One entry per readable ``state.json``.
    """
    if not paths.run_dir.is_dir():
        return []
    states = []
    for world_run in sorted(paths.run_dir.iterdir()):
        if not world_run.is_dir():
            continue
        state = load_state(world_run / "state.json")
        if state is not None:
            states.append(state)
    return states
