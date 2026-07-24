"""
Locating the project-local ``.miney`` directory and everything inside it.

Two roots meet here. A project's ``.miney`` directory holds what belongs to that one
project: its worlds, their runtime state and the shared ``luanti.conf``. Luanti itself
and the games it plays live somewhere else entirely - one plain ``Luanti`` directory in
the user's home folder - so that several Miney projects share a single install, nothing
is downloaded twice, and that directory is an ordinary, runnable Luanti a user can open
on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ENV_DIR_NAME = ".miney"

#: Name of the shared Luanti directory in the user's home folder. Visible, not hidden:
#: it is a normal Luanti install, meant to be seen and usable on its own.
LUANTI_DIR_NAME = "Luanti"


def default_luanti_dir() -> Path:
    """
    The shared Luanti install, one per user account.

    A plain ``Luanti`` directory in the home folder rather than a hidden one inside a
    project: it is a normal, runnable Luanti that every Miney project points at, and that
    the user can start by hand. Kept as a function, not a constant, so tests can redirect
    it away from a real home directory.

    :return: The directory a downloaded Luanti and its games live in.
    """
    return Path.home() / LUANTI_DIR_NAME


@dataclass(frozen=True)
class EnvPaths:
    """
    Every path a Miney project uses.

    :param root: The project's ``.miney`` directory itself. Its worlds, their runtime
        state and the shared ``luanti.conf`` all hang off this.
    :param luanti_dir: The shared Luanti install, holding the engine and its games.
        Defaults to :func:`default_luanti_dir` - one per user account, reused by every
        project - and is normally left at that; only tests set it explicitly.
    """

    root: Path
    luanti_dir: Path = field(default_factory=lambda: default_luanti_dir())

    @property
    def games_dir(self) -> Path:
        """Games directory inside the shared Luanti install, where Luanti looks for them."""
        return self.luanti_dir / "games"

    @property
    def worlds_dir(self) -> Path:
        """Parent directory of all worlds."""
        return self.root / "worlds"

    @property
    def run_dir(self) -> Path:
        """Parent directory of per-world runtime state."""
        return self.root / "run"

    @property
    def config_file(self) -> Path:
        """The generated ``luanti.conf`` shared by every world."""
        return self.root / "luanti.conf"

    @property
    def client_pw(self) -> Path:
        """File holding the password for the learner's own client."""
        return self.root / "client.pw"

    @property
    def upstream_cache(self) -> Path:
        """Cached result of the upstream Luanti version lookup."""
        return self.root / "upstream.json"

    def world_dir(self, name: str) -> Path:
        """
        Directory of one world.

        :param name: The world name.
        """
        return self.worlds_dir / name

    def world_run_dir(self, name: str) -> Path:
        """
        Runtime state directory of one world.

        :param name: The world name.
        """
        return self.run_dir / name

    def state_file(self, name: str) -> Path:
        """
        ``state.json`` of one world.

        :param name: The world name.
        """
        return self.world_run_dir(name) / "state.json"

    def log_file(self, name: str) -> Path:
        """
        Server log of one world.

        :param name: The world name.
        """
        return self.world_run_dir(name) / "server.log"


def find_env(start: Path | None = None) -> EnvPaths | None:
    """
    Search for a ``.miney`` directory, starting at a directory and walking upward.

    This mirrors how uv locates ``pyproject.toml``, including the consequence that a
    ``.miney`` in a parent directory is used when the current directory has none.

    :param start: Directory to start at. Defaults to the current working directory.
    :return: The located paths, or None if no ``.miney`` directory was found.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        root = candidate / ENV_DIR_NAME
        if root.is_dir():
            return EnvPaths(root=root)
    return None
